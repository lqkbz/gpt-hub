import json
from dataclasses import fields
from pathlib import Path

from core.config import HubConfig, parse_config

SCHEMA = Path(__file__).resolve().parents[1] / "plugins" / "astrbot_plugin_gpt_hub" / "_conf_schema.json"


def load():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_schema_keys_match_config():
    assert set(load()) == {f.name for f in fields(HubConfig)}


def test_schema_defaults_equal_config_defaults():
    defaults = {k: v["default"] for k, v in load().items()}
    assert parse_config(defaults) == HubConfig()


def test_schema_types_supported():
    allowed = {"int", "float", "bool", "string", "text", "list", "object"}
    assert {v["type"] for v in load().values()} <= allowed
