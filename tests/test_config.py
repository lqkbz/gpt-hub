import pytest

from core.config import ConfigError, DrawBackendConf, parse_config


def test_defaults():
    cfg = parse_config({})
    assert cfg.owner_ids == frozenset()
    assert cfg.private_chat_enabled is True
    assert cfg.owner_effort == "high"
    assert cfg.group_default_effort == "low"
    assert cfg.effort_providers == {}
    assert cfg.draw_backends == ()
    assert cfg.research_extra_args == ("-c", 'web_search="live"')
    assert cfg.timezone == "Asia/Shanghai"


def test_owner_ids_comma_string_and_list():
    assert parse_config({"owner_ids": " 1, 2 ,,3"}).owner_ids == frozenset({"1", "2", "3"})
    assert parse_config({"owner_ids": [1, "2"]}).owner_ids == frozenset({"1", "2"})


def test_effort_providers_json_string():
    cfg = parse_config({"effort_providers": '{"low": "codex_low", "high": "codex_high"}'})
    assert cfg.effort_providers == {"low": "codex_low", "high": "codex_high"}


def test_effort_providers_dict_and_empty():
    assert parse_config({"effort_providers": {"low": "a"}}).effort_providers == {"low": "a"}
    assert parse_config({"effort_providers": ""}).effort_providers == {}


def test_invalid_json_raises():
    with pytest.raises(ConfigError):
        parse_config({"effort_providers": "{bad"})


def test_draw_backends():
    cfg = parse_config(
        {
            "draw_backends": '[{"name": "sub", "type": "codex_cli"},'
            ' {"name": "sf", "type": "openai_images", "base_url": "https://x/v1",'
            ' "api_key": "k", "model": "m"}]'
        }
    )
    assert cfg.draw_backends == (
        DrawBackendConf(name="sub", type="codex_cli"),
        DrawBackendConf(name="sf", type="openai_images", base_url="https://x/v1", api_key="k", model="m"),
    )


@pytest.mark.parametrize(
    "item", [{"type": "codex_cli"}, {"name": "x"}, {"name": "x", "type": "nope"}]
)
def test_draw_backend_invalid(item):
    with pytest.raises(ConfigError):
        parse_config({"draw_backends": [item]})


def test_extra_args_shlex():
    cfg = parse_config({"research_extra_args": "-c 'web_search=\"cached\"' --enable x"})
    assert cfg.research_extra_args == ("-c", 'web_search="cached"', "--enable", "x")
    assert parse_config({"research_extra_args": ["a", "b"]}).research_extra_args == ("a", "b")


@pytest.mark.parametrize(
    "key",
    ["chat_user_per_minute", "chat_group_per_day", "default_feature_quota",
     "draw_timeout", "research_timeout", "research_concurrency"],
)
def test_int_minimum(key):
    with pytest.raises(ConfigError):
        parse_config({key: 0})


def test_int_from_string():
    assert parse_config({"chat_user_per_minute": "10"}).chat_user_per_minute == 10


def test_bad_timezone():
    with pytest.raises(ConfigError):
        parse_config({"timezone": "Mars/Base"})
