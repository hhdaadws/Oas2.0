from __future__ import annotations

import asyncio
from typing import Optional

from ..emu.adapter import EmulatorAdapter
from ..vision import DEFAULT_THRESHOLD
from .registry import UIRegistry
from .detector import UIDetector
from .graph import UIGraph, apply_edge
from .types import UIDetectResult, UIManagerProtocol


class UIManager(UIManagerProtocol):
    def __init__(
        self,
        adapter: EmulatorAdapter,
        *,
        capture_method: str = "adb",
        registry: Optional[UIRegistry] = None,
        graph: Optional[UIGraph] = None,
        default_threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.adapter = adapter
        self.capture_method = capture_method
        self.registry = registry or UIRegistry()
        self.graph = graph or UIGraph()
        self.detector = UIDetector(self.registry, default_threshold=default_threshold)

    def detect_ui(self, image: bytes | None = None) -> UIDetectResult:
        if image is None:
            image = self.adapter.capture(self.capture_method)
        return self.detector.detect(image)

    async def ensure_ui(
        self,
        target: str,
        *,
        max_steps: int = 8,
        step_timeout: float = 3.0,
        threshold: float | None = None,
    ) -> bool:
        # quick check
        cur = self.detect_ui()
        if cur.ui == target:
            return True

        steps = 0
        while steps < max_steps:
            steps += 1
            # plan path
            if cur.ui == "UNKNOWN":
                # try a small wait then re-capture
                await asyncio.sleep(0.5)
                cur = self.detect_ui()
                if cur.ui == target:
                    return True
            path = self.graph.find_path(cur.ui, target, max_steps=max_steps)
            if not path:
                # Cannot plan a path
                await asyncio.sleep(0.5)
                cur = self.detect_ui()
                if cur.ui == target:
                    return True
                continue
            # execute one edge then re-check
            await apply_edge(self.adapter, path[0])
            await asyncio.sleep(step_timeout)
            cur = self.detect_ui()
            if cur.ui == target:
                return True
        return False

    def navigate(self, source: str, target: str) -> bool:
        path = self.graph.find_path(source, target)
        return bool(path)


__all__ = ["UIManager"]

