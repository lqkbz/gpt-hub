from pathlib import Path

import pytest

from core.config import parse_config
from core.store import Store
from core.tts import TTS_USAGE, TtsError, TtsService

PRESETS = [
    {"name": "idx", "type": "openai_speech", "base_url": "https://sf/v1/", "api_key": "k",
     "model": "IndexTeam/IndexTTS-2", "voice": "IndexTeam/IndexTTS-2:alex", "extra": {"gain": 1}},
    {"name": "edge", "type": "astrbot", "provider_id": "edge_tts"},
]


class FakeHttp:
    def __init__(self, data=b"AUDIO", error=None):
        self.data, self.error, self.calls = data, error, []

    async def post_bytes(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        if self.error:
            raise self.error
        return self.data


class FakeAstrbot:
    def __init__(self, providers=("edge_tts",), default_ok=True, fail=False):
        self.providers, self.default_ok, self.fail, self.calls = providers, default_ok, fail, []

    async def __call__(self, provider_id, text, umo):
        self.calls.append((provider_id, text, umo))
        if self.fail:
            raise RuntimeError("tts down")
        if provider_id is None:
            return "/default.wav" if self.default_ok else None
        return f"/{provider_id}.wav" if provider_id in self.providers else None


@pytest.fixture
def make(tmp_path):
    def build(http=None, astrbot=None, **raw):
        cfg = parse_config({"tts_presets": PRESETS, **raw})
        store = Store(tmp_path / "h.db")
        svc = TtsService(cfg, store, http or FakeHttp(), astrbot or FakeAstrbot(), tmp_path / "tts")
        return svc, store

    return build


def test_resolve_order(make):
    svc, store = make()
    assert svc.resolve("1") == (None, "AstrBot 默认")
    svc2, store2 = make(tts_default_preset="edge")
    assert (svc2.resolve("1")[0].name, svc2.resolve("1")[1]) == ("edge", "配置默认")
    store2.set_tts_choice("global", "idx")
    assert (svc2.resolve("1")[0].name, svc2.resolve("1")[1]) == ("idx", "全局设置")
    store2.set_tts_choice("group:1", "edge")
    assert (svc2.resolve("1")[0].name, svc2.resolve("1")[1]) == ("edge", "群设置")
    assert svc2.resolve(None)[0].name == "idx"
    assert svc2.resolve("2")[0].name == "idx"


def test_resolve_ignores_deleted_preset(make):
    svc, store = make()
    store.set_tts_choice("group:1", "gone")
    assert svc.resolve("1") == (None, "AstrBot 默认")


async def test_openai_speech(make, tmp_path):
    http = FakeHttp()
    svc, store = make(http=http)
    store.set_tts_choice("global", "idx")
    path = await svc.synth("你好", "1", "umo")
    assert Path(path).read_bytes() == b"AUDIO" and path.endswith(".mp3")
    url, headers, payload, _ = http.calls[0]
    assert url == "https://sf/v1/audio/speech"
    assert headers["Authorization"] == "Bearer k"
    assert payload == {"model": "IndexTeam/IndexTTS-2", "input": "你好", "voice": "IndexTeam/IndexTTS-2:alex",
                       "response_format": "mp3", "speed": 1.0, "gain": 1}


async def test_astrbot_preset(make):
    ab = FakeAstrbot()
    svc, store = make(astrbot=ab, tts_default_preset="edge")
    assert await svc.synth("hi", None, "umo") == "/edge_tts.wav"
    assert ab.calls == [("edge_tts", "hi", "umo")]


async def test_no_preset_uses_astrbot_default(make):
    ab = FakeAstrbot()
    svc, _ = make(astrbot=ab)
    assert await svc.synth("hi", "1", "umo") == "/default.wav"
    assert ab.calls == [(None, "hi", "umo")]


async def test_preset_failure_falls_back(make):
    svc, store = make(http=FakeHttp(error=RuntimeError("HTTP 401")))
    store.set_tts_choice("global", "idx")
    assert await svc.synth("hi", "1", "umo") == "/default.wav"


async def test_empty_audio_falls_back(make):
    svc, store = make(http=FakeHttp(data=b""))
    store.set_tts_choice("global", "idx")
    assert await svc.synth("hi", "1", "umo") == "/default.wav"


async def test_all_fail(make):
    svc, store = make(http=FakeHttp(error=RuntimeError("HTTP 401")), astrbot=FakeAstrbot(default_ok=False))
    store.set_tts_choice("global", "idx")
    with pytest.raises(TtsError, match="idx: HTTP 401"):
        await svc.synth("hi", "1", "umo")


async def test_nothing_configured(make):
    svc, _ = make(astrbot=FakeAstrbot(default_ok=False))
    with pytest.raises(TtsError, match="未配置 TTS"):
        await svc.synth("hi", "1", "umo")


async def test_missing_astrbot_provider(make):
    svc, _ = make(astrbot=FakeAstrbot(providers=(), default_ok=False), tts_default_preset="edge")
    with pytest.raises(TtsError, match="找不到 TTS provider edge_tts"):
        await svc.synth("hi", "1", "umo")


def test_command_status(make):
    svc, store = make()
    out = svc.handle_command([], "1")
    assert out.startswith("当前生效：AstrBot 默认（AstrBot 默认）")
    assert "idx [openai_speech] IndexTeam/IndexTTS-2 / IndexTeam/IndexTTS-2:alex" in out
    assert "edge [astrbot] edge_tts" in out
    assert "k" not in out.split("可用预设")[1].replace("speech", "")  # 不泄露 api_key


def test_command_use_and_global(make):
    svc, store = make()
    assert svc.handle_command(["use", "edge"], "1").startswith("已设置群 1 语音预设：edge")
    assert store.get_tts_choice("group:1") == "edge"
    assert svc.handle_command(["use", "idx", "-g", "2"], None).startswith("已设置群 2")
    assert store.get_tts_choice("group:2") == "idx"
    svc.handle_command(["use", "default"], "1")
    assert store.get_tts_choice("group:1") is None
    assert svc.handle_command(["global", "idx"], None).startswith("已设置全局语音预设：idx")
    assert store.get_tts_choice("global") == "idx"
    svc.handle_command(["global", "default"], "1")
    assert store.get_tts_choice("global") is None


def test_command_errors(make):
    svc, _ = make()
    assert svc.handle_command(["use", "edge"], None) == "私聊需用 -g <群号> 指定群"
    assert "不存在的预设：nope" in svc.handle_command(["use", "nope"], "1")
    assert "不存在的预设" in svc.handle_command(["global", "nope"], "1")
    assert svc.handle_command(["fly"], "1") == TTS_USAGE
    assert svc.handle_command(["use"], "1") == TTS_USAGE


def test_role_preset_priority(make):
    svc, store = make(tts_default_preset="edge")
    assert (svc.resolve("1", role_preset="idx")[0].name, svc.resolve("1", role_preset="idx")[1]) == ("idx", "角色绑定")
    store.set_tts_choice("global", "edge")
    assert svc.resolve("1", role_preset="idx")[0].name == "idx"  # 角色优先于全局
    store.set_tts_choice("group:1", "edge")
    assert svc.resolve("1", role_preset="idx")[1] == "群设置"  # 群设置优先于角色
    assert svc.resolve("2", role_preset="missing")[0].name == "edge"


async def test_synth_with_role_preset(make):
    ab = FakeAstrbot()
    svc, _ = make(astrbot=ab)
    store_path = await svc.synth("hi", "1", "umo", role_preset="edge")
    assert store_path == "/edge_tts.wav"
