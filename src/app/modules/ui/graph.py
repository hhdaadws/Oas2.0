from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import asyncio


@dataclass
class Action:
    type: str  # 'tap'|'swipe'|'sleep'|'tap_anchor'|'re_detect'
    args: Tuple = ()


@dataclass
class Edge:
    src: str
    dst: str
    actions: List[Action] = field(default_factory=list)


class UIGraph:
    def __init__(self) -> None:
        self._adj: Dict[str, List[Edge]] = {}

    def add_edge(self, edge: Edge) -> None:
        self._adj.setdefault(edge.src, []).append(edge)

    def edges_from(self, ui: str) -> List[Edge]:
        return self._adj.get(ui, [])

    def find_path(self, source: str, target: str, max_steps: int = 8) -> Optional[List[Edge]]:
        # Simple BFS by edges count
        from collections import deque

        q = deque([(source, [])])
        visited = set([source])
        while q:
            node, path = q.popleft()
            if len(path) > max_steps:
                continue
            for e in self.edges_from(node):
                if e.dst == target:
                    return path + [e]
                if e.dst not in visited:
                    visited.add(e.dst)
                    q.append((e.dst, path + [e]))
        return None


async def apply_edge(adapter, edge: Edge, detect_result: Any | None = None, detect_fn=None) -> None:
    # Execute actions sequentially; minimal implementation
    for act in edge.actions:
        t = act.type
        if t == "tap":
            x, y = act.args
            adapter.tap(int(x), int(y))
        elif t == "tap_anchor":
            # args: (anchor_prefix,)
            #    or (anchor_prefix, fallback_x, fallback_y)
            #    or (anchor_prefix, fallback_x, fallback_y, max_retries)
            if not act.args:
                continue
            anchor_prefix = str(act.args[0]).lower()
            fallback_x = int(act.args[1]) if len(act.args) >= 3 else None
            fallback_y = int(act.args[2]) if len(act.args) >= 3 else None
            max_retries = int(act.args[3]) if len(act.args) >= 4 else 0
            retry_delay = int(act.args[4]) / 1000.0 if len(act.args) >= 5 else 1.5

            for attempt in range(max_retries + 1):
                anchors = {}
                if detect_result and isinstance(getattr(detect_result, "debug", None), dict):
                    anchors = detect_result.debug.get("anchors") or {}

                chosen = None
                if isinstance(anchors, dict):
                    for key, value in anchors.items():
                        if str(key).lower().startswith(anchor_prefix):
                            chosen = value
                            break

                if chosen and isinstance(chosen, dict):
                    adapter.tap(int(chosen.get("x", 0)), int(chosen.get("y", 0)))
                    break
                elif attempt < max_retries and fallback_x is not None and fallback_y is not None:
                    # 锚点未找到，点击 fallback 坐标后重新检测
                    adapter.tap(fallback_x, fallback_y)
                    await asyncio.sleep(retry_delay)
                    if detect_fn is not None:
                        detect_result = detect_fn()
                elif fallback_x is not None and fallback_y is not None:
                    adapter.tap(fallback_x, fallback_y)
        elif t == "swipe":
            x1, y1, x2, y2, dur = act.args
            adapter.swipe(int(x1), int(y1), int(x2), int(y2), int(dur))
        elif t == "sleep":
            ms = act.args[0]
            await asyncio.sleep(ms / 1000.0)
        elif t == "re_detect":
            # 重新截图检测，更新 detect_result 以获取最新锚点坐标
            if detect_fn is not None:
                detect_result = detect_fn()
        # 'tap_anchor' reserved; requires detector to expose anchors


__all__ = ["Action", "Edge", "UIGraph", "apply_edge"]

