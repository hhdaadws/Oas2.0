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
    tag: Optional[str] = None  # 用于界面识别的主模板名称，其余模板仅用于锚点提取
    # 预索引缓存（__post_init__ 自动建立）
    _tag_templates: List[TemplateDef] = field(default_factory=list, repr=False, init=False)
    _anchor_templates: List[TemplateDef] = field(default_factory=list, repr=False, init=False)

    @property
    def _tag_template(self) -> Optional[TemplateDef]:
        """向后兼容：返回首个 tag 模板或 None。"""
        return self._tag_templates[0] if self._tag_templates else None

    def __post_init__(self) -> None:
        self._index_templates()

    def _index_templates(self) -> None:
        """建立 tag / anchor 模板索引，避免每次检测时线性查找。
        tag 匹配规则：tpl.name 精确等于 self.tag，或以 self.tag + '_' 为前缀。
        """
        self._tag_templates = []
        self._anchor_templates = []
        for tpl in self.templates:
            if self.tag and (tpl.name == self.tag or tpl.name.startswith(self.tag + "_")):
                self._tag_templates.append(tpl)
            else:
                self._anchor_templates.append(tpl)


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

