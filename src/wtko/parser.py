from __future__ import annotations

import html
import re
import unicodedata
from typing import Any


_TAG_PATTERN = re.compile(r"<[^>]+>")
_COLOR_PATTERN = re.compile(r"@[A-Za-z0-9_]+")
_SPACE_PATTERN = re.compile(r"\s+")


def extract_hud_items(
    payload: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return [], []

    events = payload.get("events", [])
    damage = payload.get("damage", [])

    if not isinstance(events, list):
        events = []
    if not isinstance(damage, list):
        damage = []

    return (
        [item for item in events if isinstance(item, dict)],
        [item for item in damage if isinstance(item, dict)],
    )


def item_id(item: dict[str, Any]) -> int:
    try:
        return int(item.get("id", 0))
    except (TypeError, ValueError):
        return 0


def normalize_hud_text(value: str) -> str:
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKC", text)
    text = _TAG_PATTERN.sub(" ", text)
    text = _COLOR_PATTERN.sub(" ", text)
    text = "".join(
        ch for ch in text
        if ch in "\t\n\r" or unicodedata.category(ch) not in {"Cf", "Cc"}
    )
    text = text.replace("\xa0", " ")
    return _SPACE_PATTERN.sub(" ", text).strip()


def classify_own_kill(
    item: dict[str, Any],
    player_name: str,
    kill_keywords: tuple[str, ...] | list[str],
) -> tuple[bool, str, str]:
    message = normalize_hud_text(str(item.get("msg", "")))
    sender = normalize_hud_text(str(item.get("sender", "")))
    player = normalize_hud_text(player_name)

    message_folded = message.casefold()
    sender_folded = sender.casefold()
    player_folded = player.casefold()

    keywords = [
        normalize_hud_text(kw).casefold()
        for kw in kill_keywords
        if normalize_hud_text(kw)
    ]
    matched = [kw for kw in keywords if kw in message_folded]

    if not message:
        return False, "消息为空", message
    if not matched:
        return False, "没有命中击杀关键词", message
    if not player_folded:
        return False, "没有设置玩家昵称", message

    if player_folded in sender_folded:
        return True, f"sender 字段匹配：{sender}", message

    player_pos = message_folded.find(player_folded)
    if player_pos < 0:
        return False, "消息中没有找到玩家昵称", message

    kw_positions = [
        message_folded.find(kw) for kw in matched
        if message_folded.find(kw) >= 0
    ]
    if player_pos < min(kw_positions):
        return True, "昵称位于击杀关键词之前", message

    return False, "昵称位于关键词之后，可能是本人被击毁", message


def is_own_kill(
    message: str,
    player_name: str,
    kill_keywords: tuple[str, ...] | list[str],
) -> bool:
    matched, _reason, _normalized = classify_own_kill(
        {"msg": message, "sender": ""},
        player_name,
        kill_keywords,
    )
    return matched
