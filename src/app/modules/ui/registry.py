from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TemplateDef:
    name: str
    path: str
    roi: Optional[Tuple[int, int, int, int]] = None  # x,y,w,h
    threshold: Optional[float] = None


@dataclass
class PixelDef:
    x: int
    y: int
    rgb: Tuple[int, int, int]
    tolerance: int = 0


@dataclass
class UIDef:
    id: str
    templates: List[TemplateDef] = field(default_factory=list)
    pixels: List[PixelDef] = field(default_factory=list)
    threshold: Optional[float] = None


class UIRegistry:
    def __init__(self) -> None:
        self._uis: Dict[str, UIDef] = {}

    def register(self, ui: UIDef) -> None:
        self._uis[ui.id] = ui

    def get(self, ui_id: str) -> Optional[UIDef]:
        return self._uis.get(ui_id)

    def all(self) -> List[UIDef]:
        return list(self._uis.values())

    def ids(self) -> List[str]:
        return list(self._uis.keys())


# Global default registry
registry = UIRegistry()

__all__ = [
    "TemplateDef",
    "PixelDef",
    "UIDef",
    "UIRegistry",
    "registry",
]

