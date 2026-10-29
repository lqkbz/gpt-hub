"""滑动窗口限流。"""

from __future__ import annotations

from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, now: float) -> bool:
        """允许则记录本次并返回 True。"""
        q = self._hits[key]
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
