import pytest

from core.config import parse_config
from core.policy import ChatRoute, FeatureCheck, MsgCtx, Policy
from core.store import GroupPolicy, Store

# 2026-10-29 12:00 Asia/Shanghai
NOON = 1_793_246_400.0


class Clock:
    def __init__(self, t=NOON):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    def build(**raw):
        base = {
            "owner_ids": "8",
            "effort_providers": {"low": "p_low", "high": "p_high"},
            "chat_user_per_minute": 2,
            "chat_group_per_day": 3,
        }
        base.update(raw)
        store = Store(tmp_path / "h.db")
        clock = Clock()
        return Policy(parse_config(base), store, clock), store, clock

    return build


def test_today_uses_timezone(env):
    p, _, clock = env()
    assert p.today() == "2026-10-29"
    clock.t = NOON + 12 * 3600  # 次日 00:00 上海
    assert p.today() == "2026-10-30"


def test_owner_route(env):
    p, _, _ = env(owner_model="gpt-big")
    assert p.route_chat(MsgCtx("8", "100")) == ChatRoute(True, "p_high", "gpt-big")
    p2, _, _ = env()
    assert p2.route_chat(MsgCtx("8", None)) == ChatRoute(True, "p_high", None)


def test_owner_not_rate_limited(env):
    p, _, _ = env()
    for _ in range(10):
        assert p.route_chat(MsgCtx("8", "100")).allowed


def test_group_defaults_and_override(env):
    p, store, _ = env(group_default_model="gpt-mini")
    assert p.route_chat(MsgCtx("1", "100")) == ChatRoute(True, "p_low", "gpt-mini")
    store.save_policy(GroupPolicy("100", model="gpt-mid", effort="high"))
    assert p.route_chat(MsgCtx("2", "100")) == ChatRoute(True, "p_high", "gpt-mid")
    assert p.effective_chat("100") == ("gpt-mid", "high")


def test_unmapped_effort_gives_no_provider(env):
    p, store, _ = env()
    store.save_policy(GroupPolicy("100", effort="medium"))
    assert p.route_chat(MsgCtx("1", "100")) == ChatRoute(True, None, None)


def test_chat_off(env):
    p, store, _ = env()
    store.save_policy(GroupPolicy("100", chat_enabled=False))
    assert p.route_chat(MsgCtx("1", "100")) == ChatRoute(False, reason="chat_off")


def test_user_rate(env):
    p, _, clock = env()
    assert p.route_chat(MsgCtx("1", "100")).allowed
    assert p.route_chat(MsgCtx("1", "100")).allowed
    assert p.route_chat(MsgCtx("1", "100")).reason == "user_rate"
    clock.t += 61
    assert p.route_chat(MsgCtx("1", "100")).allowed


def test_group_daily(env):
    p, _, _ = env()
    for uid in ("1", "2", "3"):
        assert p.route_chat(MsgCtx(uid, "100")).allowed
    assert p.route_chat(MsgCtx("4", "100")).reason == "group_daily"
    assert p.route_chat(MsgCtx("4", "200")).allowed


def test_private(env):
    p, _, _ = env()
    assert p.route_chat(MsgCtx("1", None)) == ChatRoute(True, "p_low", None)
    p2, _, _ = env(private_chat_enabled=False)
    assert p2.route_chat(MsgCtx("1", None)).reason == "private_disabled"


def test_feature_checks(env):
    p, store, clock = env()
    assert p.check_feature(MsgCtx("8", "100"), "draw") == FeatureCheck(True)
    assert p.check_feature(MsgCtx("8", None), "research").allowed
    assert p.check_feature(MsgCtx("1", None), "draw") == FeatureCheck(False, "该功能仅 owner 可用")
    assert p.check_feature(MsgCtx("1", "100"), "draw") == FeatureCheck(False, "本群未开放 draw")
    store.save_policy(GroupPolicy("100", features={"draw": 2}))
    ctx = MsgCtx("1", "100")
    for _ in range(2):
        assert p.check_feature(ctx, "draw").allowed
        p.consume_feature(ctx, "draw")
    assert p.check_feature(ctx, "draw") == FeatureCheck(False, "今日 draw 次数已用完（2）")
    assert p.check_feature(MsgCtx("2", "100"), "draw").allowed
    clock.t += 86400
    assert p.check_feature(ctx, "draw").allowed


def test_owner_consume_is_noop(env):
    p, store, _ = env()
    p.consume_feature(MsgCtx("8", "100"), "draw")
    assert store.get_counter("feat:draw:100:8", p.today()) == 0
