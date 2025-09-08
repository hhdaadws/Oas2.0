"""
Data models and types for scripted task execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Literal, Any


# --- Image-based specifications ---


@dataclass
class TemplateSpec:
    path_or_bytes: bytes | str
    threshold: Optional[float] = None
    roi: Optional[Tuple[int, int, int, int]] = None  # x,y,w,h on big image


@dataclass
class PixelSpec:
    x: int
    y: int
    rgb: Tuple[int, int, int]
    tolerance: int = 0


# --- Step result ---


@dataclass
class StepResult:
    ok: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# --- Step Op enum (string literals for lightness) ---

OpType = Literal[
    "ensure_ui",
    "tap_template",
    "wait_template",
    "tap",
    "swipe",
    "sleep",
    "branch",
]


__all__ = [
    "TemplateSpec",
    "PixelSpec",
    "StepResult",
    "OpType",
]

