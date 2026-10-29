"""语音预设：解析生效预设、合成（失败回落 AstrBot 默认 TTS）、/tts 命令。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from .config import HubConfig, TtsPreset
from .store import Store

logger = logging.getLogger("astrbot")

TTS_USAGE = (
    "用法：\n"
    "/tts  查看当前语音预设与可用列表\n"
    "/tts use <预设|default> [-g 群号]  设置本群语音\n"
    "/tts global <预设|default>  设置全局默认语音"
)

# (provider_id 或 None=会话默认, 文本, umo) -> 音频路径；provider 不存在/未配置返回 None
AstrbotTts = Callable[[str | None, str, str], Awaitable[str | None]]


class TtsError(Exception):
    pass


class BytesHttp(Protocol):
    async def post_bytes(self, url: str, headers: dict, payload: dict, timeout: float) -> bytes: ...


class TtsService:
    def __init__(
        self,
        cfg: HubConfig,
        store: Store,
        http: BytesHttp,
        astrbot_tts: AstrbotTts,
        out_dir: Path,
        timeout: float = 60,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.http = http
        self.astrbot_tts = astrbot_tts
        self.out_dir = out_dir
        self.timeout = timeout
        self._presets = {p.name: p for p in cfg.tts_presets}

    def resolve(
        self, group_id: str | None, role_preset: str | None = None
    ) -> tuple[TtsPreset | None, str]:
        candidates = []
        if group_id is not None:
            candidates.append((self.store.get_tts_choice(f"group:{group_id}"), "群设置"))
        candidates.append((role_preset, "角色绑定"))
        candidates.append((self.store.get_tts_choice("global"), "全局设置"))
        candidates.append((self.cfg.tts_default_preset, "配置默认"))
        for name, source in candidates:
            if name and name in self._presets:
                return self._presets[name], source
        return None, "AstrBot 默认"

    async def synth(
        self, text: str, group_id: str | None, umo: str, role_preset: str | None = None
    ) -> str:
        preset, _ = self.resolve(group_id, role_preset)
        errors = []
        if preset is not None:
            try:
                return await self._run(preset, text, umo)
            except Exception as e:  # noqa: BLE001 - 预设失败回落 AstrBot 默认
                logger.warning("gpt_hub 语音预设 %s 失败：%s", preset.name, e)
                errors.append(f"{preset.name}: {e}")
        path = await self.astrbot_tts(None, text, umo)
        if path:
            return path
        if errors:
            raise TtsError("语音合成失败：" + "; ".join(errors))
        raise TtsError("未配置 TTS，请 owner 在 AstrBot WebUI 启用 TTS provider 或配置语音预设")

    async def _run(self, p: TtsPreset, text: str, umo: str) -> str:
        if p.type == "astrbot":
            path = await self.astrbot_tts(p.provider_id, text, umo)
            if not path:
                raise TtsError(f"AstrBot 中找不到 TTS provider {p.provider_id}")
            return path
        payload = {"model": p.model, "input": text}
        if p.voice:
            payload["voice"] = p.voice
        payload.update({"response_format": p.response_format, "speed": p.speed, **p.extra})
        data = await self.http.post_bytes(
            f"{p.base_url.rstrip('/')}/audio/speech",
            {"Authorization": f"Bearer {p.api_key}", "Content-Type": "application/json"},
            payload,
            self.timeout,
        )
        if not data:
            raise TtsError("接口返回空音频")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{uuid.uuid4().hex}.{p.response_format}"
        path.write_bytes(data)
        return str(path)

    # 命令

    def _describe(self, p: TtsPreset) -> str:
        if p.type == "astrbot":
            return f"{p.name} [astrbot] {p.provider_id}"
        return f"{p.name} [openai_speech] {p.model}" + (f" / {p.voice}" if p.voice else "")

    def _status(self, group_id: str | None) -> str:
        preset, source = self.resolve(group_id)
        lines = [f"当前生效：{preset.name if preset else 'AstrBot 默认'}（{source}）", "可用预设："]
        lines += [f"- {self._describe(p)}" for p in self.cfg.tts_presets] or ["（未配置，在插件配置 tts_presets 中添加）"]
        return "\n".join(lines)

    def handle_command(self, args: list[str], current_group: str | None) -> str:
        group = current_group
        if "-g" in args:
            i = args.index("-g")
            if i + 1 >= len(args):
                return TTS_USAGE
            group, args = args[i + 1], args[:i] + args[i + 2 :]
        if not args:
            return self._status(group)
        if len(args) != 2 or args[0] not in ("use", "global"):
            return TTS_USAGE
        sub, name = args
        if name != "default" and name not in self._presets:
            return f"不存在的预设：{name}\n" + self._status(group)
        value = None if name == "default" else name
        if sub == "global":
            self.store.set_tts_choice("global", value)
            return f"已设置全局语音预设：{name}\n" + self._status(group)
        if group is None:
            return "私聊需用 -g <群号> 指定群"
        self.store.set_tts_choice(f"group:{group}", value)
        return f"已设置群 {group} 语音预设：{name}\n" + self._status(group)
