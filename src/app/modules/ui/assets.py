"""
游戏资产定义：哪个资产在哪个界面、哪个 ROI 区域可通过 OCR 读取。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union


class AssetType(str, Enum):
    """游戏资产类型"""
    STAMINA = "stamina"        # 体力
    GOUYU = "gouyu"            # 勾玉
    LANPIAO = "lanpiao"        # 蓝票
    GOLD = "gold"              # 金币
    GONGXUN = "gongxun"        # 功勋
    XUNZHANG = "xunzhang"      # 勋章
    TUPO_TICKET = "tupo_ticket"  # 突破票


@dataclass
class AssetDef:
    """资产定义"""
    asset_type: AssetType
    screen: str                           # 需要导航到的 UI 界面 ID
    roi: Tuple[int, int, int, int]        # OCR 识别区域 (x, y, w, h)
    parser: Callable[[str], Optional[int]]
    db_field: str                          # GameAccount 对应字段名
    label: str                             # 显示名称
    pre_tap: Optional[Tuple[int, int]] = None  # 等待模板前先点击此坐标（如展开菜单）
    wait_template: Optional[Union[str, List[str]]] = None  # OCR 前等待此模板出现，确认界面就绪
    digit_only: bool = False                   # True 时使用数字专用 OCR 引擎（仅 0-9）


def parse_number(text: str) -> Optional[int]:
    """从 OCR 文本中解析整数。

    支持中文单位（亿、万）：如 ``2.99亿`` → 299000000，``1.9万`` → 19000。
    处理常见 OCR 误识别：去除空格/逗号，修正 O→0、l→1 等。
    """
    cleaned = text.strip()

    # 0. 修正常见中文单位 OCR 误识别
    cleaned = cleaned.replace("方", "万")   # "万" 常被误识别为 "方"
    cleaned = cleaned.replace("忆", "亿")   # "亿" 可能被误识别为 "忆"

    # 1. 尝试匹配中文单位格式：数字(可含小数点) + 亿/万
    cn_match = re.search(r"(\d+\.?\d*)\s*(亿|万)", cleaned)
    if cn_match:
        num_str = cn_match.group(1)
        unit = cn_match.group(2)
        multiplier = 100_000_000 if unit == "亿" else 10_000
        try:
            return int(float(num_str) * multiplier)
        except (ValueError, OverflowError):
            pass

    # 2. 纯数字提取（原有逻辑）
    cleaned = cleaned.replace(",", "").replace(".", "").replace(" ", "")
    cleaned = cleaned.replace("O", "0").replace("o", "0")
    cleaned = cleaned.replace("l", "1").replace("I", "1")
    match = re.search(r"\d+", cleaned)
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None


def _discover_shangdian_paths() -> List[str]:
    """自动发现 assets/ui/templates/shangdian_*.png 模板路径列表。"""
    templates_dir = Path("assets/ui/templates")
    paths = sorted(p.as_posix() for p in templates_dir.glob("shangdian_*.png"))
    return paths or ["assets/ui/templates/shangdian_1.png"]  # 兜底


_SHANGDIAN_WAIT_TEMPLATES = _discover_shangdian_paths()


# 资产注册表
ASSET_REGISTRY: Dict[AssetType, AssetDef] = {
    AssetType.STAMINA: AssetDef(
        asset_type=AssetType.STAMINA,
        screen="TINGYUAN",
        roi=(667, 15, 68, 24),
        parser=parse_number,
        db_field="stamina",
        label="体力",
        pre_tap=(921, 490),
        wait_template=_SHANGDIAN_WAIT_TEMPLATES,
        digit_only=True,
    ),
    AssetType.GOUYU: AssetDef(
        asset_type=AssetType.GOUYU,
        screen="TINGYUAN",
        roi=(533, 15, 66, 24),
        parser=parse_number,
        db_field="gouyu",
        label="勾玉",
        pre_tap=(921, 490),
        wait_template=_SHANGDIAN_WAIT_TEMPLATES,
    ),
    AssetType.LANPIAO: AssetDef(
        asset_type=AssetType.LANPIAO,
        screen="TINGYUAN",
        roi=(0, 0, 0, 0),  # TODO: 确定蓝票显示 ROI
        parser=parse_number,
        db_field="lanpiao",
        label="蓝票",
    ),
    AssetType.GOLD: AssetDef(
        asset_type=AssetType.GOLD,
        screen="TINGYUAN",
        roi=(400, 15, 64, 24),
        parser=parse_number,
        db_field="gold",
        label="金币",
        pre_tap=(921, 490),
        wait_template=_SHANGDIAN_WAIT_TEMPLATES,
    ),
    AssetType.GONGXUN: AssetDef(
        asset_type=AssetType.GONGXUN,
        screen="LIAO_SHANGDIAN",
        roi=(709, 15, 84, 24),
        parser=parse_number,
        db_field="gongxun",
        label="功勋",
        digit_only=True,
    ),
    AssetType.XUNZHANG: AssetDef(
        asset_type=AssetType.XUNZHANG,
        screen="SHANGDIAN",
        roi=(441, 15, 70, 42),
        parser=parse_number,
        db_field="xunzhang",
        label="勋章",
        digit_only=True,
    ),
    AssetType.TUPO_TICKET: AssetDef(
        asset_type=AssetType.TUPO_TICKET,
        screen="JIEJIE_TUPO",
        roi=(855, 13, 30, 18),
        parser=parse_number,
        db_field="tupo_ticket",
        label="突破票",
        digit_only=True,
    ),
}


def get_asset_def(asset_type: AssetType) -> Optional[AssetDef]:
    """获取资产定义。"""
    return ASSET_REGISTRY.get(asset_type)
