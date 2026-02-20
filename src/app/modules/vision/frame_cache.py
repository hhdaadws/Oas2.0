from __future__ import annotations

import time
import zlib

import cv2
import numpy as np

from .utils import ImageLike, load_image


def compute_frame_signature(
    image: ImageLike,
    *,
    width: int = 64,
    height: int = 36,
) -> np.ndarray:
    """计算截图缩略签名（量化灰度图），用于快速同帧判定。"""
    loaded = load_image(image)
    gray = loaded if loaded.ndim == 2 else cv2.cvtColor(loaded, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
    # 轻量去噪 + 量化：降低细微动态（粒子/闪烁/压缩噪点）对指纹的影响
    # 以便在“视觉上基本不变”的场景提升缓存命中率。
    denoised = cv2.GaussianBlur(small, (3, 3), 0)
    return (denoised // 8).astype("uint8")


def fingerprint_from_signature(signature: np.ndarray) -> int:
    """根据缩略签名计算 CRC32 指纹。"""
    return zlib.crc32(memoryview(signature).tobytes()) & 0xFFFFFFFF


def compute_frame_fingerprint(
    image: ImageLike,
    *,
    width: int = 64,
    height: int = 36,
) -> int:
    """计算截图指纹，用于判定画面是否变化。"""
    signature = compute_frame_signature(image, width=width, height=height)
    return fingerprint_from_signature(signature)


def signatures_similar(
    lhs: np.ndarray,
    rhs: np.ndarray,
    *,
    mean_abs_threshold: float = 0.8,
) -> bool:
    """判断两个签名是否近似同帧。"""
    if lhs.shape != rhs.shape:
        return False
    diff = cv2.absdiff(lhs, rhs)
    return float(diff.mean()) <= float(mean_abs_threshold)


def is_cache_fresh(timestamp: float, ttl_ms: int, *, now: float | None = None) -> bool:
    """判断缓存时间戳是否仍在有效期内。"""
    if ttl_ms <= 0:
        return False
    current = time.monotonic() if now is None else now
    return (current - timestamp) * 1000.0 <= float(ttl_ms)
