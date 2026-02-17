"""
UI types and a minimal protocol for UIManager used by executors.

This is a typing-only contract; concrete implementation is provided elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Any, Coroutine


@dataclass
class UIDetectResult:
    ui: str
    score: float
    debug: Optional[dict[str, Any]] = None


class UIManagerProtocol(Protocol):
    async def detect_ui(self, image: bytes | None = None) -> UIDetectResult:
        """Detect current UI. If image is None, capture internally."""
        ...

    async def ensure_ui(
        self,
        target: str,
        *,
        max_steps: int = 8,
        step_timeout: float = 3.0,
        threshold: float | None = None,
    ) -> bool:
        """Ensure the app is on target UI. Navigate if needed.

        Returns True when target UI is reached.
        """
        ...


__all__ = ["UIDetectResult", "UIManagerProtocol"]

