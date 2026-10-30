"""酒馆角色卡（chara_card_v2 / v1 JSON）→ 角色卡；统一为成年设定，拒绝未成年角色。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .store import Role

ADULT_NOTE = "【设定说明】所有角色均为成年人（20 岁以上）；文中的学校、同学均指大学。"

# 年龄写法：age: 18 / Age：18 / 年龄：18岁
_AGE_RE = re.compile(r"(age|年龄)(\s*[:：]\s*)(\d{1,3})", re.I)
_NSFW_RE = re.compile(r"nsfw|sexual|erotic|色情|性欲|做爱", re.I)

_SECTIONS = (
    ("description", ""),
    ("personality", "【性格】"),
    ("scenario", "【场景】"),
    ("system_prompt", "【额外规则】"),
    ("post_history_instructions", "【回复要求】"),
)


class CardError(ValueError):
    pass


@dataclass
class CardImport:
    role: Role
    notes: list[str] = field(default_factory=list)


def _fill(text: str, char: str, user: str) -> str:
    return text.replace("{{char}}", char).replace("{{user}}", user).replace("<USER>", user).replace("<BOT>", char)


def _normalize_age(text: str, notes: list[str]) -> str:
    def repl(m: re.Match) -> str:
        age = int(m.group(3))
        if age < 18:
            raise CardError(f"角色卡写明年龄 {age} 岁，未成年角色不能导入")
        if age < 20:
            notes.append(f"年龄 {age} 已改为 20")
            return f"{m.group(1)}{m.group(2)}20"
        return m.group(0)

    return _AGE_RE.sub(repl, text)


def card_to_role(card: dict, name: str) -> CardImport:
    data = card.get("data", card) if isinstance(card, dict) else {}
    notes: list[str] = []
    parts = []
    for key, header in _SECTIONS:
        text = str(data.get(key) or "").strip()
        if text:
            parts.append(f"{header}\n{text}" if header else text)
    if not parts:
        raise CardError("角色卡没有人设内容")

    prompt = _normalize_age(_fill("\n\n".join(parts), name, "用户"), notes)
    if not _AGE_RE.search(prompt):
        notes.append("角色卡未写明年龄，已注明为成年人")
    prompt += "\n\n" + ADULT_NOTE

    examples = _fill(str(data.get("mes_example") or ""), name, "用户")
    examples = re.sub(r"<START>\s*", "", examples).strip()
    greeting = _normalize_age(_fill(str(data.get("first_mes") or "").strip(), name, "你"), notes)

    tags = [str(t).lower() for t in data.get("tags") or []]
    raw = " ".join(str(data.get(k) or "") for k, _ in _SECTIONS) + " " + greeting
    nsfw = "nsfw" in tags or bool(_NSFW_RE.search(raw))
    if nsfw:
        notes.append("检测为成人角色：仅限私聊使用")

    role = Role(name=name, prompt=prompt, greeting=greeting, examples=examples, nsfw=nsfw)
    return CardImport(role, notes)
