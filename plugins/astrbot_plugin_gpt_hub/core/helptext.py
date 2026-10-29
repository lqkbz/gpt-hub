"""/help：按会话与身份生成中文功能说明。"""

from __future__ import annotations

from .policy import MsgCtx, Policy

_FEATURES = {
    "draw": ["/draw <描述>  AI 画图"],
    "research": [
        "/research <主题>  深度研究，完成后发报告",
        "/research status  查看研究进度",
        "/research cancel <任务号>  取消研究",
    ],
    "voice": ["/say <文本>  文字转语音", "/voice on|off  本会话 AI 回复改为语音"],
}

_ADMIN = [
    "【群管理】私聊时加 -g <群号>",
    "/mode  查看群策略",
    "/mode on <draw|research|voice> [每日次数]  开放功能",
    "/mode off <功能>  关闭功能",
    "/mode model <模型|default>  设群聊天模型",
    "/mode effort <low|medium|high|xhigh|default>  设群推理强度",
    "/mode chat on|off  群聊天开关",
    "/voice on|off -g <群号>  指定群之后的回复全部转语音",
    "",
    "【角色扮演】",
    "/role  当前角色与列表",
    "/role gen <名称> <描述>  AI 生成角色卡",
    "/role set <名称> <人设>  手写人设",
    "/role secret <名称> <文本|gen>  隐藏设定（gen 让 AI 重新生成）",
    "/role voice <名称> <预设|none>  绑定语音",
    "/role show <名称>  查看角色卡",
    "/role use <名称|none|default> [-g 群号]  切换角色（自动开新对话）",
    "/role global <名称|none>  全局默认角色",
    "/role del <名称>  删除角色",
    "",
    "【语音预设】",
    "/tts  当前预设与列表",
    "/tts use <预设|default> [-g 群号]  设群语音",
    "/tts global <预设|default>  设全局语音",
    "",
    "【订阅】",
    "/usage  查看订阅剩余额度",
    "/effort [强度]  调当前会话推理强度",
]

_COMMON = ["【通用】", "/reset  清空当前对话记忆", "/new  开始新对话", "/help  显示本说明"]


def build_help(policy: Policy, ctx: MsgCtx, role_name: str | None) -> str:
    owner = policy.is_owner(ctx.sender_id)
    lines = ["📖 功能说明", ""]

    lines.append("【聊天】")
    if ctx.group_id is None:
        lines.append("直接发消息和我聊天")
    elif not owner and not policy.store.get_policy(ctx.group_id).chat_enabled:
        lines.append("本群聊天已关闭")
    else:
        lines.append("在群里 @我 即可聊天")
    if not owner:
        model, effort = policy.effective_chat(ctx.group_id)
        lines.append(f"模型：{model or '默认'}，推理强度：{effort}")
    if role_name:
        lines.append(f"当前角色：{role_name}")
    lines.append("")

    lines.append("【可用功能】")
    shown = False
    for feature, cmds in _FEATURES.items():
        if owner:
            lines += cmds
            shown = True
            continue
        remaining = policy.feature_remaining(ctx, feature)
        if remaining is None:
            continue
        quota = policy.store.get_policy(ctx.group_id).features[feature]
        lines += [f"{cmds[0]}（今日剩余 {remaining}/{quota}）", *cmds[1:]]
        shown = True
    if owner:
        lines.append("（你不限次数）")
    elif not shown:
        lines.append("本群暂未开放其他功能")
    lines.append("")

    lines += _COMMON
    if owner and ctx.group_id is None:
        lines += ["", *_ADMIN]
    return "\n".join(lines)
