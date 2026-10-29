import pytest

from core.commands import MODE_USAGE, handle_mode
from core.config import parse_config
from core.policy import Policy
from core.store import GroupPolicy, Store


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "h.db")
    cfg = parse_config(
        {
            "owner_ids": "8",
            "effort_providers": {"low": "p_low", "medium": "p_med", "high": "p_high"},
            "group_default_model": "gpt-mini",
            "default_feature_quota": 5,
        }
    )
    policy = Policy(cfg, store)

    def run(text, group="100"):
        return handle_mode(text.split(), current_group=group, policy=policy, store=store)

    return run, store


def test_view_default(env):
    run, _ = env
    out = run("")
    assert "群 100" in out
    assert "gpt-mini（默认）" in out
    assert "low（默认）" in out and "p_low" in out
    assert "聊天：开" in out
    assert "功能：无" in out


def test_g_flag_overrides_group(env):
    run, store = env
    run("on draw -g 200")
    assert store.get_policy("200").features == {"draw": 5}
    assert store.get_policy("100").features == {}


def test_private_requires_g(env):
    run, _ = env
    assert run("", group=None) == "私聊需用 -g <群号> 指定群"
    assert "群 300" in run("-g 300", group=None)


def test_on_off(env):
    run, store = env
    out = run("on research 2")
    assert out.startswith("已更新")
    assert "research（每人每天 2 次）" in out
    run("on voice")
    assert store.get_policy("100").features == {"research": 2, "voice": 5}
    run("off research")
    assert store.get_policy("100").features == {"voice": 5}


@pytest.mark.parametrize("text", ["on fly", "on draw 0", "on draw x", "off", "on"])
def test_on_invalid(env, text):
    run, _ = env
    assert run(text) == MODE_USAGE


def test_model(env):
    run, store = env
    assert "gpt-big" in run("model gpt-big")
    assert store.get_policy("100").model == "gpt-big"
    run("model default")
    assert store.get_policy("100").model is None


def test_effort(env):
    run, store = env
    out = run("effort high")
    assert store.get_policy("100").effort == "high"
    assert "p_high" in out
    bad = run("effort xhigh")
    assert "可选：high, low, medium" in bad
    assert store.get_policy("100").effort == "high"
    run("effort default")
    assert store.get_policy("100").effort is None


def test_chat_toggle(env):
    run, store = env
    run("chat off")
    assert store.get_policy("100").chat_enabled is False
    assert "聊天：关" in run("")
    run("chat on")
    assert store.get_policy("100").chat_enabled is True


@pytest.mark.parametrize("text", ["fly", "chat maybe", "model", "-g"])
def test_unknown(env, text):
    run, _ = env
    assert run(text) == MODE_USAGE


def test_preserves_other_fields(env):
    run, store = env
    store.save_policy(GroupPolicy("100", model="m", features={"draw": 1}))
    run("effort medium")
    p = store.get_policy("100")
    assert (p.model, p.effort, p.features) == ("m", "medium", {"draw": 1})


@pytest.mark.parametrize(
    "args,expected",
    [
        (["on"], ("on", None)),
        (["off"], ("off", None)),
        ([], ("status", None)),
        (["on", "-g", "123"], ("on", "123")),
        (["-g", "123", "off"], ("off", "123")),
        (["-g", "123"], ("status", "123")),
        (["maybe"], None),
        (["on", "-g"], None),
        (["on", "off"], None),
    ],
)
def test_parse_voice_args(args, expected):
    from core.commands import parse_voice_args

    assert parse_voice_args(args) == expected
