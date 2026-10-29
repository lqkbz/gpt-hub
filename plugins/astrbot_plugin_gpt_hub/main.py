"""AstrBot 胶水：注册命令与钩子，业务逻辑在 core/。"""

from __future__ import annotations

import os
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

from .core.commands import handle_mode
from .core.config import ConfigError, parse_config
from .core.draw import AiohttpClient, BackendError, DrawService, build_backends
from .core.policy import MsgCtx, Policy
from .core.research import ResearchService
from .core.store import Store

PLUGIN_NAME = "astrbot_plugin_gpt_hub"
MODEL_EXTRA = "gpt_hub_model"


def _msg_ctx(event: AstrMessageEvent) -> MsgCtx:
    gid = event.get_group_id()
    return MsgCtx(str(event.get_sender_id()), str(gid) if gid else None)


def _args(event: AstrMessageEvent) -> list[str]:
    """去掉命令词后的参数。"""
    return event.message_str.strip().split()[1:]


def _short(e: Exception) -> str:
    return str(e)[:200] or type(e).__name__


@register(PLUGIN_NAME, "lqkbz", "ChatGPT 订阅 QQ 机器人：模式/权限/生图/研究/语音", "0.1.0")
class GptHub(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config_error: str | None = None
        try:
            self.cfg = parse_config(config)
        except ConfigError as e:
            self.config_error = str(e)
            logger.error("gpt_hub 配置错误，插件已禁用：%s", e)
            return
        data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        codex_home = Path(
            self.cfg.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        )
        self.store = Store(data_dir / "gpt_hub.db")
        self.policy = Policy(self.cfg, self.store)
        self.draw = DrawService(
            build_backends(self.cfg, AiohttpClient(), codex_home), data_dir / "draw"
        )
        self.research = ResearchService(self.cfg, self.store, data_dir / "research", self._notify)

    async def initialize(self) -> None:
        if not self.config_error:
            await self.research.start()

    async def terminate(self) -> None:
        if not self.config_error:
            await self.research.stop()
            self.store.close()

    async def _notify(self, umo: str, text: str, file_path: str | None) -> None:
        chain = MessageChain().message(text)
        if file_path:
            p = Path(file_path)
            chain.chain.append(Comp.File(name=f"{p.parent.name}.md", file=str(p)))
        await self.context.send_message(umo, chain)

    # 聊天路由

    @filter.on_waiting_llm_request()
    async def route_chat(self, event: AstrMessageEvent) -> None:
        if self.config_error:
            return
        route = self.policy.route_chat(_msg_ctx(event))
        if not route.allowed:
            logger.info("gpt_hub 拦截聊天 sender=%s reason=%s", event.get_sender_id(), route.reason)
            event.stop_event()
            return
        if route.provider_id:
            event.set_extra("selected_provider", route.provider_id)
        if route.model:
            event.set_extra("selected_model", route.model)
            event.set_extra(MODEL_EXTRA, route.model)

    @filter.on_llm_request()
    async def apply_model(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        model = event.get_extra(MODEL_EXTRA)
        if model:
            req.model = model

    # 管理

    @filter.command("mode")
    async def mode(self, event: AstrMessageEvent):
        if self.config_error:
            yield event.plain_result(f"配置错误：{self.config_error}")
            return
        ctx = _msg_ctx(event)
        if not self.policy.is_owner(ctx.sender_id):
            return
        yield event.plain_result(
            handle_mode(_args(event), current_group=ctx.group_id, policy=self.policy, store=self.store)
        )

    # 功能

    def _gate(self, event: AstrMessageEvent, feature: str) -> str | None:
        """返回拒绝原因；None 表示放行。"""
        if self.config_error:
            return f"配置错误：{self.config_error}"
        check = self.policy.check_feature(_msg_ctx(event), feature)
        return None if check.allowed else check.reason

    @filter.command("draw")
    async def draw_cmd(self, event: AstrMessageEvent):
        if reason := self._gate(event, "draw"):
            yield event.plain_result(reason)
            return
        prompt = " ".join(_args(event))
        if not prompt:
            yield event.plain_result("用法：/draw <描述>")
            return
        await event.send(MessageChain().message("生成中…"))
        try:
            r = await self.draw.draw(prompt)
        except BackendError as e:
            yield event.plain_result(f"生图失败：{e}")
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("gpt_hub /draw 异常")
            yield event.plain_result(f"出错了：{_short(e)}")
            return
        self.policy.consume_feature(_msg_ctx(event), "draw")
        img = Comp.Image.fromFileSystem(r.path) if r.path else Comp.Image.fromURL(r.url)
        yield event.chain_result([img])

    @filter.command("research")
    async def research_cmd(self, event: AstrMessageEvent):
        if reason := self._gate(event, "research"):
            yield event.plain_result(reason)
            return
        args = _args(event)
        ctx = _msg_ctx(event)
        umo = event.unified_msg_origin
        if not args:
            yield event.plain_result(
                "用法：/research <主题>｜/research status [任务号]｜/research cancel <任务号>"
            )
            return
        if args[0] == "status":
            job_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
            yield event.plain_result(self.research.status_text(umo, job_id))
            return
        if args[0] == "cancel":
            if len(args) < 2 or not args[1].isdigit():
                yield event.plain_result("用法：/research cancel <任务号>")
                return
            yield event.plain_result(
                self.research.cancel(int(args[1]), ctx.sender_id, self.policy.is_owner(ctx.sender_id))
            )
            return
        job = self.research.submit(umo, ctx.sender_id, " ".join(args))
        self.policy.consume_feature(ctx, "research")
        yield event.plain_result(f"已提交研究 #{job.id}，完成后会发到这里")

    async def _tts(self, event: AstrMessageEvent, text: str) -> str | None:
        tts = self.context.get_using_tts_provider(event.unified_msg_origin)
        if tts is None:
            return None
        return await tts.get_audio(text)

    @filter.command("say")
    async def say_cmd(self, event: AstrMessageEvent):
        if reason := self._gate(event, "voice"):
            yield event.plain_result(reason)
            return
        text = " ".join(_args(event))
        if not text:
            yield event.plain_result("用法：/say <文本>")
            return
        if len(text) > self.cfg.tts_max_chars:
            yield event.plain_result(f"文本过长（上限 {self.cfg.tts_max_chars} 字）")
            return
        try:
            path = await self._tts(event, text)
        except Exception as e:  # noqa: BLE001
            logger.exception("gpt_hub /say 异常")
            yield event.plain_result(f"语音合成失败：{_short(e)}")
            return
        if path is None:
            yield event.plain_result("未配置 TTS，请 owner 在 AstrBot WebUI 中启用 TTS provider")
            return
        self.policy.consume_feature(_msg_ctx(event), "voice")
        yield event.chain_result([Comp.Record(file=path)])

    @filter.command("voice")
    async def voice_cmd(self, event: AstrMessageEvent):
        if reason := self._gate(event, "voice"):
            yield event.plain_result(reason)
            return
        args = _args(event)
        if len(args) != 1 or args[0] not in ("on", "off"):
            yield event.plain_result("用法：/voice on|off")
            return
        on = args[0] == "on"
        self.store.set_voice(event.unified_msg_origin, on)
        if on:
            self.policy.consume_feature(_msg_ctx(event), "voice")
        yield event.plain_result("本会话 AI 回复将转为语音" if on else "已关闭语音回复")

    @filter.on_decorating_result()
    async def voice_reply(self, event: AstrMessageEvent) -> None:
        if self.config_error:
            return
        result = event.get_result()
        if result is None or not result.is_llm_result():
            return
        if not self.store.is_voice(event.unified_msg_origin):
            return
        chain = result.chain
        if not chain or not all(isinstance(c, Comp.Plain) for c in chain):
            return
        text = "".join(c.text for c in chain).strip()
        if not text or len(text) > self.cfg.tts_max_chars:
            return
        try:
            path = await self._tts(event, text)
        except Exception:  # noqa: BLE001 - 失败则保留文本回复
            logger.exception("gpt_hub 语音回复合成失败")
            return
        if path:
            result.chain = [Comp.Record(file=path)]
