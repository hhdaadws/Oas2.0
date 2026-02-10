"""核心 OCR 识别函数。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..vision.utils import ImageLike, load_image
from .engine import get_ocr_engine
from .types import OcrBox, OcrResult

# ROI 类型：(x, y, w, h)，与 TemplateDef.roi 格式一致
Roi = Tuple[int, int, int, int]


def ocr(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> OcrResult:
    """对图像执行 OCR 识别。

    Args:
        image: 图像来源（路径 / bytes / np.ndarray）
        roi: 可选区域 (x, y, w, h)，仅识别该区域内的文字
        min_confidence: 最低置信度阈值，低于此值的结果将被过滤

    Returns:
        OcrResult，包含所有识别结果（坐标为大图坐标）
    """
    engine = get_ocr_engine()
    img = load_image(image)

    # ROI 裁剪
    offset_x, offset_y = 0, 0
    if roi:
        x, y, w, h = roi
        img = img[y : y + h, x : x + w]
        offset_x, offset_y = x, y

    # PaddleOCR 3.x: predict() 接受 BGR ndarray，返回 OCRResult 列表
    results = engine.predict(img)

    boxes: List[OcrBox] = []
    if results:
        result = results[0]
        rec_texts = result["rec_texts"]
        rec_scores = result["rec_scores"]
        rec_polys = result["rec_polys"]
        for text, confidence, poly in zip(rec_texts, rec_scores, rec_polys):
            if confidence < min_confidence:
                continue
            # 坐标偏移还原为大图坐标
            adjusted_box = [
                (int(p[0] + offset_x), int(p[1] + offset_y))
                for p in poly
            ]
            boxes.append(OcrBox(
                text=text,
                confidence=float(confidence),
                box=adjusted_box,
            ))

    return OcrResult(boxes=boxes)


def ocr_text(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> str:
    """OCR 识别并返回纯文本（便捷函数）。"""
    return ocr(image, roi=roi, min_confidence=min_confidence).text


def find_text(
    image: ImageLike,
    keyword: str,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> Optional[OcrBox]:
    """在图像中查找包含关键词的第一个文本区域。

    Returns:
        OcrBox 或 None
    """
    return ocr(image, roi=roi, min_confidence=min_confidence).find(keyword)


def find_all_text(
    image: ImageLike,
    keyword: str,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> List[OcrBox]:
    """在图像中查找所有包含关键词的文本区域。"""
    return ocr(image, roi=roi, min_confidence=min_confidence).find_all(keyword)
