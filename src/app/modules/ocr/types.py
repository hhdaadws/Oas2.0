"""OCR 识别结果数据结构。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class OcrBox:
    """单个 OCR 识别结果。"""

    text: str
    confidence: float
    # 边界框四点坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    # 坐标始终为原始大图坐标（ROI 偏移已还原）
    box: List[Tuple[int, int]]

    @property
    def center(self) -> Tuple[int, int]:
        """边界框中心点，可直接用于 adb.tap()。"""
        xs = [p[0] for p in self.box]
        ys = [p[1] for p in self.box]
        return (sum(xs) // len(xs), sum(ys) // len(ys))


@dataclass
class OcrResult:
    """OCR 识别结果集合。"""

    boxes: List[OcrBox]

    @property
    def text(self) -> str:
        """所有识别文本拼接（空格分隔）。"""
        return " ".join(b.text for b in self.boxes)

    def find(self, keyword: str) -> Optional[OcrBox]:
        """查找包含指定关键词的第一个结果。"""
        for b in self.boxes:
            if keyword in b.text:
                return b
        return None

    def find_all(self, keyword: str) -> List[OcrBox]:
        """查找所有包含指定关键词的结果。"""
        return [b for b in self.boxes if keyword in b.text]
