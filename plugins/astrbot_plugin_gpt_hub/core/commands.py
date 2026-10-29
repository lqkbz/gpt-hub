"""/mode 管理命令：解析、执行、渲染群策略。"""

from __future__ import annotations

from .config import FEATURES
from .policy import Policy
from .store import GroupPolicy, Store

MODE_USAGE = (
    "用法（-g <群号> 可指定群）：\n"
    "/mode  查看本群策略\n"
    "/mode on <draw|research|voice> [每日次数]\n"
    "/mode off <功能>\n"
    "/mode model <模型名|default>\n"
    "/mode effort <强度|default>\n"
    "/mode chat <on|off>"
)


def render_policy(p: GroupPolicy, policy: Policy) -> str:
    model, effort = policy.effective_chat(p.group_id)
    model_text = model or "provider 默认"
    if p.model is None:
        model_text += "（默认）"
    effort_text = effort + ("（默认）" if p.effort is None else "")
    provider = policy.cfg.effort_providers.get(effort) or "会话默认 provider"
    if p.features:
        feats = "、".join(f"{k}（每人每天 {v} 次）" for k, v in sorted(p.features.items()))
    else:
        feats = "无"
    return (
        f"群 {p.group_id}\n"
        f"聊天：{'开' if p.chat_enabled else '关'}\n"
        f"模型：{model_text}\n"
        f"推理强度：{effort_text} → {provider}\n"
        f"功能：{feats}"
    )


def _pop_group_flag(args: list[str]) -> tuple[list[str], str | None, bool]:
    """取出 -g <群号>；返回 (剩余参数, 群号, 是否合法)。"""
    if "-g" not in args:
        return args, None, True
    i = args.index("-g")
    if i + 1 >= len(args):
        return args, None, False
    return args[:i] + args[i + 2 :], args[i + 1], True


def _apply(p: GroupPolicy, args: list[str], policy: Policy) -> str | None:
    """修改 p；返回错误提示，成功返回 None。"""
    sub, rest = args[0], args[1:]
    if sub == "on" and rest and rest[0] in FEATURES and len(rest) <= 2:
        quota = policy.cfg.default_feature_quota
        if len(rest) == 2:
            if not rest[1].isdigit() or int(rest[1]) < 1:
                return MODE_USAGE
            quota = int(rest[1])
        p.features[rest[0]] = quota
    elif sub == "off" and len(rest) == 1 and rest[0] in FEATURES:
        p.features.pop(rest[0], None)
    elif sub == "model" and len(rest) == 1:
        p.model = None if rest[0] == "default" else rest[0]
    elif sub == "effort" and len(rest) == 1:
        if rest[0] == "default":
            p.effort = None
        elif rest[0] in policy.cfg.effort_providers:
            p.effort = rest[0]
        else:
            choices = ", ".join(sorted(policy.cfg.effort_providers)) or "（未配置 effort_providers）"
            return f"不支持的推理强度：{rest[0]}；可选：{choices}"
    elif sub == "chat" and len(rest) == 1 and rest[0] in ("on", "off"):
        p.chat_enabled = rest[0] == "on"
    else:
        return MODE_USAGE
    return None


def handle_mode(args: list[str], *, current_group: str | None, policy: Policy, store: Store) -> str:
    args, flag_group, ok = _pop_group_flag(args)
    if not ok:
        return MODE_USAGE
    group = flag_group or current_group
    if group is None:
        return "私聊需用 -g <群号> 指定群"
    p = store.get_policy(group)
    if not args:
        return render_policy(p, policy)
    err = _apply(p, args, policy)
    if err:
        return err
    store.save_policy(p)
    return "已更新：\n" + render_policy(p, policy)


def parse_voice_args(args: list[str]) -> tuple[str, str | None] | None:
    """/voice 参数 → (on|off|status, 群号或 None)；非法返回 None。"""
    args, group, ok = _pop_group_flag(args)
    if not ok or len(args) > 1:
        return None
    if not args:
        return "status", group
    return (args[0], group) if args[0] in ("on", "off") else None
