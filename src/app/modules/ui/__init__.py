from .types import UIDetectResult, UIManagerProtocol
from .registry import UIRegistry, UIDef, TemplateDef, PixelDef, registry
from .detector import UIDetector
from .graph import UIGraph, Edge, Action
from . import screens as _screens  # noqa: F401  触发界面注册
from .manager import UIManager
from .popups import PopupDef, PopupRegistry, DismissAction, DismissType, popup_registry
from .popup_handler import PopupHandler
from .default_popups import register_default_popups

# 注册默认弹窗
register_default_popups()

__all__ = [
    "UIDetectResult",
    "UIManagerProtocol",
    "UIRegistry",
    "UIDef",
    "TemplateDef",
    "PixelDef",
    "registry",
    "UIDetector",
    "UIGraph",
    "Edge",
    "Action",
    "UIManager",
    "PopupDef",
    "PopupRegistry",
    "DismissAction",
    "DismissType",
    "popup_registry",
    "PopupHandler",
]

