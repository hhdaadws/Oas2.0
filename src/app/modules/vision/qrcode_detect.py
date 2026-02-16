"""二维码检测工具 - 基于 OpenCV QRCodeDetector"""
from __future__ import annotations

from typing import Union

import cv2
import numpy as np


def detect_qrcode(image: Union[np.ndarray, bytes]) -> bool:
    """检测图像中是否存在二维码。

    Args:
        image: BGR numpy 数组或 PNG bytes

    Returns:
        True 表示检测到二维码，False 表示未检测到。
    """
    if isinstance(image, bytes):
        arr = np.frombuffer(image, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return False

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    detector = cv2.QRCodeDetector()
    retval, points = detector.detect(gray)
    return bool(retval and points is not None)
