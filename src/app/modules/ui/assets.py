"""
游戏资产定义：哪个资产在哪个界面、哪个 ROI 区域可通过 OCR 读取。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Tuple


class AssetType(str, Enum):
    """游戏资产类型"""
    STAMINA = "stamina"        # 体力
    GOUYU = "gouyu"            # 勾玉
    LANPIAO = "lanpiao"        # 蓝票
    GOLD = "gold"              # 金币


@dataclass
class AssetDef:
    """资产定义"""
    asset_type: AssetType
    screen: str                           # 需要导航到的 UI 界面 ID
    roi: Tuple[int, int, int, int]        # OCR 识别区域 (x, y, w, h)
    parser: Callable[[str], Optional[int]]
    db_field: str                          # GameAccount 对应字段名
    label: str                             # 显示名称
    wait_template: Optional[str] = None   # OCR 前等待此模板出现，确认界面就绪


def parse_number(text: str) -> Optional[int]:
    """从 OCR 文本中解析整数。

    处理常见 OCR 误识别：去除空格/逗号，修正 O→0、l→1 等。
    """
    cleaned = text.strip()
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


# 资产注册表
ASSET_REGISTRY: Dict[AssetType, AssetDef] = {
    AssetType.STAMINA: AssetDef(
        asset_type=AssetType.STAMINA,
        screen="TINGYUAN",
        roi=(533, 15, 66, 24),
        parser=parse_number,
        db_field="stamina",
        label="体力",
        wait_template="assets/ui/templates/shangdian_1.png",
    ),
    AssetType.GOUYU: AssetDef(
        asset_type=AssetType.GOUYU,
        screen="TINGYUAN",
        roi=(0, 0, 0, 0),  # TODO: 确定勾玉显示 ROI
        parser=parse_number,
        db_field="gouyu",
        label="勾玉",
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
        roi=(0, 0, 0, 0),  # TODO: 确定金币显示 ROI
        parser=parse_number,
        db_field="gold",
        label="金币",
    ),
}


def get_asset_def(asset_type: AssetType) -> Optional[AssetDef]:
    """获取资产定义。"""
    return ASSET_REGISTRY.get(asset_type)
