"""
Vision utilities: image loading/decoding and pixel helpers.
"""
from __future__ import annotations

import math
import random
from typing import Tuple, Union
import os
import numpy as np
import cv2  # type: ignore


ImageLike = Union[str, bytes, np.ndarray]

_IMAGE_PATH_CACHE: dict[str, np.ndarray] = {}


def load_image(img: ImageLike) -> np.ndarray:
    """Load an image into a BGR numpy array.

    - str: treated as a file path and loaded via cv2.imread
    - bytes: decoded via cv2.imdecode
    - np.ndarray: returned as-is (assumed BGR or single-channel)
    """
    if isinstance(img, np.ndarray):
        return img
    if isinstance(img, (bytes, bytearray)):
        arr = np.frombuffer(img, dtype=np.uint8)
        mat = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if mat is None:
            raise ValueError("Failed to decode image bytes")
        return mat
    if isinstance(img, str):
        if not os.path.isfile(img):
            raise FileNotFoundError(f"Image file not found: {img}")
        if img in _IMAGE_PATH_CACHE:
            return _IMAGE_PATH_CACHE[img]
        mat = cv2.imread(img, cv2.IMREAD_COLOR)
        if mat is None:
            raise ValueError(f"Failed to load image from path: {img}")
        _IMAGE_PATH_CACHE[img] = mat
        return mat
    raise TypeError(f"Unsupported image type: {type(img)}")


def to_gray(img: np.ndarray) -> np.ndarray:
    """Convert BGR image to grayscale (no-op if already single-channel)."""
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def pixel_at(img: ImageLike, x: int, y: int) -> Tuple[int, int, int]:
    """Return pixel color at (x, y) as BGR tuple.

    Raises IndexError if out of bounds.
    """
    mat = load_image(img)
    h, w = mat.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        raise IndexError(f"Pixel ({x},{y}) is out of bounds for image {w}x{h}")
    if mat.ndim == 2:
        v = int(mat[y, x])
        return (v, v, v)
    b, g, r = mat[y, x]
    return int(b), int(g), int(r)


def pixel_match(
    img: ImageLike,
    x: int,
    y: int,
    color: Tuple[int, int, int],
    *,
    tolerance: int = 0,
    color_space: str = "rgb",
) -> dict:
    """Check if pixel at (x, y) matches expected color within tolerance.

    Args:
        img: image source (path/bytes/np.ndarray)
        x, y: pixel coordinate relative to image top-left
        color: expected color as (R,G,B) if color_space='rgb', or (B,G,R) if 'bgr'
        tolerance: per-channel absolute tolerance (0 for exact match)
        color_space: 'rgb' (default) or 'bgr' for the expected color tuple

    Returns:
        dict with keys: ok, actual_bgr, expected_bgr, diff, distance
    """
    exp = tuple(int(c) for c in color)
    if color_space.lower() == "rgb":
        exp_bgr = (exp[2], exp[1], exp[0])
    elif color_space.lower() == "bgr":
        exp_bgr = exp  # already BGR
    else:
        raise ValueError("color_space must be 'rgb' or 'bgr'")

    b, g, r = pixel_at(img, x, y)
    diff = (abs(b - exp_bgr[0]), abs(g - exp_bgr[1]), abs(r - exp_bgr[2]))
    ok = all(d <= tolerance for d in diff)
    distance = int(max(diff))
    return {
        "ok": ok,
        "actual_bgr": (b, g, r),
        "expected_bgr": exp_bgr,
        "diff": diff,
        "distance": distance,
        "x": x,
        "y": y,
    }


__all__ = [
    "ImageLike",
    "load_image",
    "to_gray",
    "pixel_at",
    "pixel_match",
    "random_point_in_circle",
]


def random_point_in_circle(cx: int, cy: int, radius: int) -> Tuple[int, int]:
    """在以 (cx, cy) 为圆心、radius 为半径的圆内生成均匀分布的随机点。"""
    angle = random.uniform(0, 2 * math.pi)
    r = radius * math.sqrt(random.random())
    x = max(0, int(cx + r * math.cos(angle)))
    y = max(0, int(cy + r * math.sin(angle)))
    return (x, y)

