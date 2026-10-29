import json

import pytest

from core.roles import ROLE_USAGE, RoleService, build_role_block
from core.store import Role, Store


class FakeGen:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def __call__(self, system, prompt):
        self.calls.append((system, prompt))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


CARD = {"prompt": "你是海龟汤主持人", "examples": "玩家：是人吗？\n主持：是。", "greeting": "来喝汤吧", "secret": "汤面…汤底…"}


@pytest.fixture
def env(tmp_path):
    def build(reply=None):
        store = Store(tmp_path / "h.db")
        gen = FakeGen(reply if reply is not None else "```json\n" + json.dumps(CARD, ensure_ascii=False) + "\n```")
        return RoleService(store, gen), store, gen

    return build


async def run(svc, text, group="100", sender="8"):
    return await svc.handle(text, current_group=group, sender_id=sender)


def test_resolve(env):
    svc, store, _ = env()
    store.save_role(Role("a", "A"))
    store.save_role(Role("b", "B"))
    assert svc.resolve("100", "1") is None
    store.set_role_choice("global", "a")
    assert svc.resolve("100", "1").name == "a"
    assert svc.resolve(None, "1") is None  # 全局默认不作用于私聊
    store.set_role_choice("group:100", "b")
    assert svc.resolve("100", "1").name == "b"
    store.set_role_choice("group:100", "")
    assert svc.resolve("100", "1") is None  # 显式不用角色
    store.set_role_choice("private:1", "b")
    assert svc.resolve(None, "1").name == "b"
    store.set_role_choice("group:200", "gone")
    assert svc.resolve("200", "1").name == "a"  # 角色被删时回落全局


def test_build_role_block():
    block = build_role_block(Role("猫娘", "温柔的猫娘", examples="喵~", secret="其实是狐狸"))
    assert block.startswith("# 角色扮演")
    assert "「猫娘」" in block and "温柔的猫娘" in block and "喵~" in block and "其实是狐狸" in block
    assert "昵称" in block and "露骨" in block
    plain = build_role_block(Role("x", "p"))
    assert "示例对话" not in plain and "隐藏设定" not in plain


async def test_status_and_list(env):
    svc, store, _ = env()
    assert "暂无角色" in (await run(svc, "")).text
    store.save_role(Role("a", "A人设", tts_preset="晓晓"))
    store.set_role_choice("group:100", "a")
    out = (await run(svc, "")).text
    assert out.startswith("当前角色：a（群设置）") and "- a（语音：晓晓）" in out


async def test_set_keeps_newlines_and_other_fields(env):
    svc, store, _ = env()
    store.save_role(Role("a", "旧", greeting="嗨"))
    act = await run(svc, "set a 第一行\n第二行")
    assert act.text.startswith("已保存角色 a")
    assert store.get_role("a") == Role("a", "第一行\n第二行", greeting="嗨")


async def test_greet_secret_voice(env):
    svc, store, _ = env()
    assert (await run(svc, "greet nope 嗨")).text == "角色不存在：nope"
    store.save_role(Role("a", "A"))
    await run(svc, "greet a 大家好")
    await run(svc, "secret a 汤底是X")
    await run(svc, "voice a 晓晓")
    assert store.get_role("a") == Role("a", "A", greeting="大家好", secret="汤底是X", tts_preset="晓晓")
    await run(svc, "voice a none")
    assert store.get_role("a").tts_preset == ""


async def test_gen(env):
    svc, store, gen = env()
    act = await run(svc, "gen 海龟汤 海龟汤主持人，题目要烧脑", group=None)
    assert store.get_role("海龟汤") == Role("海龟汤", CARD["prompt"], CARD["greeting"], CARD["examples"], CARD["secret"])
    system, prompt = gen.calls[0]
    assert "JSON" in system and "成年" in system
    assert "海龟汤主持人，题目要烧脑" in prompt
    assert act.text.startswith("已生成角色 海龟汤") and CARD["secret"] in act.text  # 私聊显示隐藏设定


async def test_gen_in_group_hides_secret(env):
    svc, _, _ = env()
    act = await run(svc, "gen 海龟汤 主持人", group="100")
    assert CARD["secret"] not in act.text and "隐藏设定已保存" in act.text


@pytest.mark.parametrize("reply", ["不是JSON", '{"greeting": "x"}', RuntimeError("down")])
async def test_gen_failure(env, reply):
    svc, store, _ = env(reply)
    act = await run(svc, "gen a 描述")
    assert act.text.startswith("生成失败") and store.get_role("a") is None


async def test_secret_gen(env):
    svc, store, gen = env("新汤面…新汤底…")
    store.save_role(Role("海龟汤", "主持人", secret="旧题"))
    act = await run(svc, "secret 海龟汤 gen", group=None)
    assert store.get_role("海龟汤").secret == "新汤面…新汤底…"
    assert "旧题" in gen.calls[0][1] and "主持人" in gen.calls[0][1]
    assert "新汤底" in act.text
    group_act = await run(svc, "secret 海龟汤 gen", group="100")
    assert "新汤底" not in group_act.text


async def test_show(env):
    svc, store, _ = env()
    store.save_role(Role("a", "A人设", greeting="嗨", secret="秘"))
    assert "秘" in (await run(svc, "show a", group=None)).text
    shown = (await run(svc, "show a", group="100")).text
    assert "A人设" in shown and "秘" not in shown
    assert (await run(svc, "show x")).text == "角色不存在：x"


async def test_use(env):
    svc, store, _ = env()
    store.save_role(Role("a", "A", greeting="大家好"))
    act = await run(svc, "use a")
    assert (act.switch_scope, act.greeting) == ("group:100", "大家好")
    assert store.get_role_choice("group:100") == "a"
    act = await run(svc, "use a -g 200", group=None)
    assert act.switch_scope == "group:200" and store.get_role_choice("group:200") == "a"
    act = await run(svc, "use a", group=None, sender="8")
    assert act.switch_scope == "private:8"
    act = await run(svc, "use none")
    assert store.get_role_choice("group:100") == "" and act.switch_scope == "group:100" and act.greeting == ""
    await run(svc, "use default")
    assert store.get_role_choice("group:100") is None
    bad = await run(svc, "use nope")
    assert bad.text == "角色不存在：nope" and bad.switch_scope is None


async def test_global_and_del(env):
    svc, store, _ = env()
    store.save_role(Role("a", "A"))
    act = await run(svc, "global a")
    assert store.get_role_choice("global") == "a" and act.switch_scope is None
    await run(svc, "global none")
    assert store.get_role_choice("global") is None
    store.set_role_choice("group:1", "a")
    assert (await run(svc, "del a")).text == "已删除角色 a"
    assert store.get_role("a") is None and store.get_role_choice("group:1") is None
    assert (await run(svc, "del a")).text == "角色不存在：a"


@pytest.mark.parametrize("text", ["fly", "set a", "gen a", "use", "greet a", "voice a", "-g"])
async def test_usage(env, text):
    svc, _, _ = env()
    assert (await run(svc, text)).text == ROLE_USAGE
