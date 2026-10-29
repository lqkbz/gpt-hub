"""角色判定、聊天路由与功能许可。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from .config import HubConfig
from .ratelimit import SlidingWindow
from .store import Store


@dataclass(frozen=True)
class MsgCtx:
    sender_id: str
    group_id: str | None  # None 表示私聊


@dataclass(frozen=True)
class ChatRoute:
    allowed: bool
    provider_id: str | None = None
    model: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class FeatureCheck:
    allowed: bool
    reason: str = ""


class Policy:
    def __init__(self, cfg: HubConfig, store: Store, clock: Callable[[], float] = time.time) -> None:
        self.cfg = cfg
        self.store = store
        self.clock = clock
        self._tz = ZoneInfo(cfg.timezone)
        self._user_window = SlidingWindow(cfg.chat_user_per_minute, 60.0)

    def is_owner(self, sender_id: str) -> bool:
        return str(sender_id) in self.cfg.owner_ids

    def today(self) -> str:
        return datetime.fromtimestamp(self.clock(), self._tz).strftime("%Y-%m-%d")

    def effective_chat(self, group_id: str | None) -> tuple[str | None, str]:
        """非 owner 在该会话下生效的 (模型, effort)；模型 None 表示 provider 默认。"""
        model = self.cfg.group_default_model or None
        effort = self.cfg.group_default_effort
        if group_id is not None:
            p = self.store.get_policy(group_id)
            model = p.model or model
            effort = p.effort or effort
        return model, effort

    def _route(self, model: str | None, effort: str) -> ChatRoute:
        return ChatRoute(True, self.cfg.effort_providers.get(effort), model)

    def route_chat(self, ctx: MsgCtx) -> ChatRoute:
        if self.is_owner(ctx.sender_id):
            return self._route(self.cfg.owner_model or None, self.cfg.owner_effort)

        now = self.clock()
        if ctx.group_id is None:
            if not self.cfg.private_chat_enabled:
                return ChatRoute(False, reason="private_disabled")
            if not self._user_window.hit(f"p:{ctx.sender_id}", now):
                return ChatRoute(False, reason="user_rate")
            return self._route(*self.effective_chat(None))

        if not self.store.get_policy(ctx.group_id).chat_enabled:
            return ChatRoute(False, reason="chat_off")
        if not self._user_window.hit(f"{ctx.group_id}:{ctx.sender_id}", now):
            return ChatRoute(False, reason="user_rate")
        if self.store.incr_counter(f"chat:{ctx.group_id}", self.today()) > self.cfg.chat_group_per_day:
            return ChatRoute(False, reason="group_daily")
        return self._route(*self.effective_chat(ctx.group_id))

    @staticmethod
    def _feature_key(ctx: MsgCtx, feature: str) -> str:
        return f"feat:{feature}:{ctx.group_id}:{ctx.sender_id}"

    def check_feature(self, ctx: MsgCtx, feature: str) -> FeatureCheck:
        if self.is_owner(ctx.sender_id):
            return FeatureCheck(True)
        if ctx.group_id is None:
            return FeatureCheck(False, "该功能仅 owner 可用")
        quota = self.store.get_policy(ctx.group_id).features.get(feature)
        if quota is None:
            return FeatureCheck(False, f"本群未开放 {feature}")
        if self.store.get_counter(self._feature_key(ctx, feature), self.today()) >= quota:
            return FeatureCheck(False, f"今日 {feature} 次数已用完（{quota}）")
        return FeatureCheck(True)

    def feature_remaining(self, ctx: MsgCtx, feature: str) -> int | None:
        """群成员今日剩余次数；owner、私聊或未开放返回 None。"""
        if self.is_owner(ctx.sender_id) or ctx.group_id is None:
            return None
        quota = self.store.get_policy(ctx.group_id).features.get(feature)
        if quota is None:
            return None
        used = self.store.get_counter(self._feature_key(ctx, feature), self.today())
        return max(quota - used, 0)

    def consume_feature(self, ctx: MsgCtx, feature: str) -> None:
        if self.is_owner(ctx.sender_id):
            return
        self.store.incr_counter(self._feature_key(ctx, feature), self.today())
