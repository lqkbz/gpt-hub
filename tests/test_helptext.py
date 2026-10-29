import pytest

from core.config import parse_config
from core.helptext import build_help
from core.policy import MsgCtx, Policy
from core.store import GroupPolicy, Store


@pytest.fixture
def policy(tmp_path):
    store = Store(tmp_path / "h.db")
    cfg = parse_config({"owner_ids": "8", "effort_providers": {"low": "p"}, "group_default_model": "gpt-6-luna"})
    return Policy(cfg, store), store


def test_member_default_group(policy):
    p, _ = policy
    out = build_help(p, MsgCtx("1", "100"), role_name=None)
    assert "@我" in out and "gpt-6-luna" in out and "low" in out
    assert "本群暂未开放其他功能" in out
    assert "/reset" in out
    assert "/mode" not in out and "/role" not in out and "AstrBot" not in out


def test_member_with_features_and_remaining(policy):
    p, store = policy
    store.save_policy(GroupPolicy("100", features={"draw": 3, "voice": 2}))
    ctx = MsgCtx("1", "100")
    p.consume_feature(ctx, "draw")
    out = build_help(p, ctx, role_name="海龟汤")
    assert "/draw" in out and "今日剩余 2/3" in out
    assert "/say" in out and "/voice" in out and "今日剩余 2/2" in out
    assert "/research" not in out
    assert "当前角色：海龟汤" in out


def test_member_chat_off(policy):
    p, store = policy
    store.save_policy(GroupPolicy("100", chat_enabled=False))
    assert "本群聊天已关闭" in build_help(p, MsgCtx("1", "100"), role_name=None)


def test_owner_in_group_hides_admin(policy):
    p, _ = policy
    out = build_help(p, MsgCtx("8", "100"), role_name=None)
    assert "/draw" in out and "/research" in out and "不限次数" in out
    assert "/mode" not in out and "私聊我发送 /help" in out


def test_owner_private_full(policy):
    p, _ = policy
    out = build_help(p, MsgCtx("8", None), role_name=None)
    for cmd in ("/draw", "/research", "/say", "/voice", "/mode", "/role", "/tts", "/usage", "/effort"):
        assert cmd in out, cmd


def test_stranger_private(policy):
    p, _ = policy
    out = build_help(p, MsgCtx("1", None), role_name=None)
    assert "直接发消息" in out and "/draw" not in out and "/mode" not in out
