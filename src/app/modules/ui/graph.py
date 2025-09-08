from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import asyncio


@dataclass
class Action:
    type: str  # 'tap'|'swipe'|'sleep'|'tap_anchor'
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


async def apply_edge(adapter, edge: Edge) -> None:
    # Execute actions sequentially; minimal implementation
    for act in edge.actions:
        t = act.type
        if t == "tap":
            x, y = act.args
            adapter.tap(int(x), int(y))
        elif t == "swipe":
            x1, y1, x2, y2, dur = act.args
            adapter.swipe(int(x1), int(y1), int(x2), int(y2), int(dur))
        elif t == "sleep":
            ms = act.args[0]
            await asyncio.sleep(ms / 1000.0)
        # 'tap_anchor' reserved; requires detector to expose anchors


__all__ = ["Action", "Edge", "UIGraph", "apply_edge"]

