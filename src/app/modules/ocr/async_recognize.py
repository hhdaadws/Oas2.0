"""异步 OCR 识别包装器。

将同步 OCR 推理 offload 到计算线程池，避免阻塞事件循环。
Tesseract (pytesseract) 天然线程安全（每次调用独立子进程），无需推理锁。
ddddocr 仍需推理锁，逻辑不变。
"""
from __future__ import annotations

import functools
from typing import List, Optional, Tuple

from ...core.thread_pool import run_in_compute
from ..vision.utils import ImageLike
from .types import OcrBox, OcrResult

Roi = Tuple[int, int, int, int]


def _sync_ocr(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> OcrResult:
    """在计算线程池中调用的同步 OCR。

    pytesseract 天然线程安全，无需推理锁。
    """
    import cv2
    import pytesseract

    from ...core.config import settings
    from ..vision.utils import load_image

    img = load_image(image)

    offset_x, offset_y = 0, 0
    if roi:
        x, y, w, h = roi
        img = img[y: y + h, x: x + w]
        offset_x, offset_y = x, y

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
        if not text or conf == -1:
            continue
        confidence = conf / 100.0
        if confidence < min_confidence:
            continue
        x1 = int(data["left"][i]) + offset_x
        y1 = int(data["top"][i]) + offset_y
        x2 = x1 + int(data["width"][i])
        y2 = y1 + int(data["height"][i])
        boxes.append(OcrBox(
            text=text,
            confidence=confidence,
            box=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        ))

    return OcrResult(boxes=boxes)


def _sync_ocr_digits_with_lock(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
) -> OcrResult:
    """带推理锁的同步数字 OCR（在线程池中调用）。"""
    from .engine import acquire_digit_ocr
    from ..vision.utils import load_image
    import cv2

    engine, lock = acquire_digit_ocr()
    img = load_image(image)

    if roi:
        x, y, w, h = roi
        img = img[y: y + h, x: x + w]

    _, buf = cv2.imencode(".png", img)

    with lock:
        text = engine.classification(buf.tobytes())

    boxes: List[OcrBox] = []
    if text:
        boxes.append(OcrBox(text=text, confidence=1.0, box=[]))

    return OcrResult(boxes=boxes)


async def async_ocr(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> OcrResult:
    """异步版本的 ocr()，在计算线程池中执行。"""
    return await run_in_compute(
        functools.partial(
            _sync_ocr, image,
            roi=roi, min_confidence=min_confidence,
        )
    )


async def async_ocr_digits(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
) -> OcrResult:
    """异步版本的 ocr_digits()，在计算线程池中执行。"""
    return await run_in_compute(
        functools.partial(_sync_ocr_digits_with_lock, image, roi=roi)
    )


async def async_find_text(
    image: ImageLike,
    keyword: str,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> Optional[OcrBox]:
    """异步版本的 find_text()。"""
    result = await async_ocr(image, roi=roi, min_confidence=min_confidence)
    return result.find(keyword)


async def async_ocr_text(
    image: ImageLike,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> str:
    """异步版本的 ocr_text()。"""
    result = await async_ocr(image, roi=roi, min_confidence=min_confidence)
    return result.text


async def async_find_all_text(
    image: ImageLike,
    keyword: str,
    *,
    roi: Optional[Roi] = None,
    min_confidence: float = 0.6,
) -> List[OcrBox]:
    """异步版本的 find_all_text()。"""
    result = await async_ocr(image, roi=roi, min_confidence=min_confidence)
    return result.find_all(keyword)


__all__ = [
    "async_ocr",
    "async_ocr_digits",
    "async_find_text",
    "async_ocr_text",
    "async_find_all_text",
]
