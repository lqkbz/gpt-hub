"""插件配置解析与校验。"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FEATURES = ("draw", "research", "voice")
DRAW_BACKEND_TYPES = ("openai_images", "codex_cli")
TTS_PRESET_TYPES = ("openai_speech", "astrbot")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DrawBackendConf:
    name: str
    type: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "1024x1024"


@dataclass(frozen=True)
class TtsPreset:
    name: str
    type: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    voice: str = ""
    response_format: str = "mp3"
    speed: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)
    provider_id: str = ""


@dataclass(frozen=True)
class HubConfig:
    owner_ids: frozenset[str] = frozenset()
    private_chat_enabled: bool = True
    owner_model: str = ""
    owner_effort: str = "high"
    group_default_model: str = ""
    group_default_effort: str = "low"
    effort_providers: dict[str, str] = field(default_factory=dict)
    chat_user_per_minute: int = 6
    chat_group_per_day: int = 300
    default_feature_quota: int = 5
    timezone: str = "Asia/Shanghai"
    draw_backends: tuple[DrawBackendConf, ...] = ()
    draw_timeout: int = 180
    codex_bin: str = "codex"
    codex_home: str = ""
    research_model: str = ""
    research_effort: str = "high"
    research_extra_args: tuple[str, ...] = ("-c", 'web_search="live"')
    research_timeout: int = 1800
    research_concurrency: int = 1
    research_summary_chars: int = 600
    tts_max_chars: int = 300
    tts_presets: tuple[TtsPreset, ...] = ()
    tts_default_preset: str = ""


_POSITIVE_INTS = (
    "chat_user_per_minute",
    "chat_group_per_day",
    "default_feature_quota",
    "draw_timeout",
    "research_timeout",
    "research_concurrency",
    "research_summary_chars",
    "tts_max_chars",
)
_STRINGS = (
    "owner_model",
    "owner_effort",
    "group_default_model",
    "group_default_effort",
    "timezone",
    "codex_bin",
    "codex_home",
    "research_model",
    "research_effort",
    "tts_default_preset",
)


def _load_json(key: str, value: Any, expected: type) -> Any:
    if isinstance(value, str):
        if not value.strip():
            return expected()
        try:
            value = json.loads(value)
        except json.JSONDecodeError as e:
            raise ConfigError(f"{key} 不是合法 JSON：{e}") from e
    if not isinstance(value, expected):
        raise ConfigError(f"{key} 应为 {expected.__name__}")
    return value


def _parse_owner_ids(value: Any) -> frozenset[str]:
    items = value.split(",") if isinstance(value, str) else list(value)
    return frozenset(s for s in (str(i).strip() for i in items) if s)


def _parse_draw_backends(value: Any) -> tuple[DrawBackendConf, ...]:
    out = []
    for item in _load_json("draw_backends", value, list):
        if not isinstance(item, dict) or not item.get("name") or not item.get("type"):
            raise ConfigError("draw_backends 每项需要 name 和 type")
        if item["type"] not in DRAW_BACKEND_TYPES:
            raise ConfigError(f"未知生图后端类型：{item['type']}")
        known = {k: str(v) for k, v in item.items() if k in DrawBackendConf.__dataclass_fields__}
        out.append(DrawBackendConf(**known))
    return tuple(out)


def _parse_tts_presets(value: Any) -> tuple[TtsPreset, ...]:
    out: list[TtsPreset] = []
    for item in _load_json("tts_presets", value, list):
        if not isinstance(item, dict) or not item.get("name") or not item.get("type"):
            raise ConfigError("tts_presets 每项需要 name 和 type")
        if item["type"] not in TTS_PRESET_TYPES:
            raise ConfigError(f"未知语音预设类型：{item['type']}")
        if item["type"] == "astrbot" and not item.get("provider_id"):
            raise ConfigError(f"语音预设 {item['name']} 缺少 provider_id")
        if item["type"] == "openai_speech" and not (item.get("base_url") and item.get("model")):
            raise ConfigError(f"语音预设 {item['name']} 缺少 base_url 或 model")
        kw: dict[str, Any] = {
            k: str(v) for k, v in item.items()
            if k in TtsPreset.__dataclass_fields__ and k not in ("speed", "extra")
        }  # fmt: skip
        try:
            kw["speed"] = float(item.get("speed", 1.0))
        except (TypeError, ValueError) as e:
            raise ConfigError(f"语音预设 {item['name']} 的 speed 应为数字") from e
        extra = item.get("extra", {})
        if not isinstance(extra, dict):
            raise ConfigError(f"语音预设 {item['name']} 的 extra 应为对象")
        kw["extra"] = extra
        out.append(TtsPreset(**kw))
    names = [p.name for p in out]
    if len(set(names)) != len(names):
        raise ConfigError("tts_presets 名称重复")
    return tuple(out)


def parse_config(raw: Mapping[str, Any]) -> HubConfig:
    kw: dict[str, Any] = {}
    if "owner_ids" in raw:
        kw["owner_ids"] = _parse_owner_ids(raw["owner_ids"])
    if "private_chat_enabled" in raw:
        kw["private_chat_enabled"] = bool(raw["private_chat_enabled"])
    for key in _STRINGS:
        if key in raw and raw[key] is not None:
            kw[key] = str(raw[key]).strip()
    for key in _POSITIVE_INTS:
        if key in raw:
            try:
                n = int(raw[key])
            except (TypeError, ValueError) as e:
                raise ConfigError(f"{key} 应为整数") from e
            if n < 1:
                raise ConfigError(f"{key} 必须 ≥ 1")
            kw[key] = n
    if "effort_providers" in raw:
        mapping = _load_json("effort_providers", raw["effort_providers"], dict)
        kw["effort_providers"] = {str(k): str(v) for k, v in mapping.items()}
    if "draw_backends" in raw:
        kw["draw_backends"] = _parse_draw_backends(raw["draw_backends"])
    if "research_extra_args" in raw:
        v = raw["research_extra_args"]
        kw["research_extra_args"] = tuple(shlex.split(v) if isinstance(v, str) else map(str, v))

    if "tts_presets" in raw:
        kw["tts_presets"] = _parse_tts_presets(raw["tts_presets"])

    cfg = HubConfig(**kw)
    if cfg.tts_default_preset and cfg.tts_default_preset not in {p.name for p in cfg.tts_presets}:
        raise ConfigError(f"tts_default_preset 不存在：{cfg.tts_default_preset}")
    try:
        ZoneInfo(cfg.timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"非法时区：{cfg.timezone}") from e
    return cfg
