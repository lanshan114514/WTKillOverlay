from __future__ import annotations

import random
from typing import Sequence

from .models import RandomPoolItem


def eligible_items(
    items: Sequence[RandomPoolItem],
    combo: int,
) -> list[RandomPoolItem]:
    """当前连杀数下能参与抽取的条目。

    先按 min_combo 过滤；全都不到门槛时退回整个可用池，
    否则连杀数低的时候会出现"池子非空但抽不到东西"的死角。
    """
    usable = [item for item in items if item.is_usable()]
    if not usable:
        return []

    reached = [item for item in usable if combo >= max(0, item.min_combo)]
    return reached or usable


def weighted_pick(
    candidates: Sequence[RandomPoolItem],
    rng: random.Random | None = None,
) -> RandomPoolItem | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    generator = rng or random
    total = sum(max(0.0, item.weight) for item in candidates)
    if total <= 0:
        return generator.choice(list(candidates))

    threshold = generator.uniform(0.0, total)
    accumulated = 0.0
    for item in candidates:
        accumulated += max(0.0, item.weight)
        if threshold <= accumulated:
            return item
    return candidates[-1]


def pick_item(
    items: Sequence[RandomPoolItem],
    combo: int,
    last_identity: str = "",
    avoid_repeat: bool = True,
    rng: random.Random | None = None,
) -> RandomPoolItem | None:
    """按当前连杀数抽一条。抽不到返回 None。"""
    candidates = eligible_items(items, combo)
    if not candidates:
        return None

    if avoid_repeat and last_identity and len(candidates) > 1:
        filtered = [item for item in candidates if item.identity() != last_identity]
        if filtered:
            candidates = filtered

    return weighted_pick(candidates, rng)
