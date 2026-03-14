"""核心 OCR 识别函数。"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2

from ..vision.utils import ImageLike, load_image
from .engine import acquire_digit_ocr
from .types import OcrBox, OcrResult

# ROI 类型：(x, y, w, h)，与 TemplateDef.roi 格式一致
Roi = Tuple[int, int, int, int]


def ocr(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> OcrResult:
    """对图像执行 OCR 识别（使用 Tesseract）。

    Args:
        image: 图像来源（路径 / bytes / np.ndarray）
        roi: 可选区域 (x, y, w, h)，仅识别该区域内的文字
        min_confidence: 最低置信度阈值（0.0–1.0），低于此值的结果将被过滤

    Returns:
        OcrResult，包含所有识别结果（坐标为大图坐标）
    """
    import pytesseract
    from ...core.config import settings

    img = load_image(image)

    # ROI 裁剪
    offset_x, offset_y = 0, 0
    if roi:
        x, y, w, h = roi
        img = img[y: y + h, x: x + w]
        offset_x, offset_y = x, y

    # Tesseract 需要 RGB（OpenCV 默认 BGR）
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    data = pytesseract.image_to_data(
        img_rgb,
        lang=settings.tesseract_lang,
        output_type=pytesseract.Output.DICT,
    )

    boxes: List[OcrBox] = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        # conf == -1 表示该行无有效置信度（非文字区域），text 为空也跳过
        if not text or conf == -1:
            continue
        confidence = conf / 100.0
        if confidence < min_confidence:
            continue

        x1 = int(data["left"][i]) + offset_x
        y1 = int(data["top"][i]) + offset_y
        x2 = x1 + int(data["width"][i])
        y2 = y1 + int(data["height"][i])
        box = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        boxes.append(OcrBox(text=text, confidence=confidence, box=box))

    return OcrResult(boxes=boxes)


def ocr_digits(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
) -> OcrResult:
    """对图像执行纯数字 OCR 识别（使用 ddddocr 引擎）。

    适用于体力、功勋、勋章等已知为纯数字的 ROI 区域。
    ddddocr 直接对整图分类，无需文本检测阶段，对小尺寸数字识别准确。

    Args:
        image: 图像来源（路径 / bytes / np.ndarray）
        roi: 可选区域 (x, y, w, h)，仅识别该区域内的文字

    Returns:
        OcrResult，包含识别结果
    """
    engine, lock = acquire_digit_ocr()
    img = load_image(image)

    if roi:
        x, y, w, h = roi
        img = img[y: y + h, x: x + w]

    # ddddocr 接受 PNG bytes
    _, buf = cv2.imencode(".png", img)
    with lock:
        text = engine.classification(buf.tobytes())

    boxes: List[OcrBox] = []
    if text:
        boxes.append(OcrBox(text=text, confidence=1.0, box=[]))

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
