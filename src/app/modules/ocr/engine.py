"""OCR 引擎管理：Tesseract 配置 + ddddocr 实例池。

Tesseract (pytesseract)：
  - 天然线程安全（每次调用启动独立子进程），无需实例池或推理锁
  - 通过 TESSERACT_CMD 配置可执行文件路径，留空时自动检测
  - 通过 TESSERACT_LANG 配置识别语言，默认 chi_sim+eng

ddddocr：
  - 用于游戏纯数字识别，准确率高
  - predict() 非线程安全，保留实例池 + 推理锁
"""
from __future__ import annotations

import os
import threading
from typing import List, Tuple

from ...core.config import settings
from ...core.logger import logger


# ── ddddocr 单例（兼容旧代码） ──
_digit_instance = None
_digit_lock = threading.Lock()
# 推理锁：ddddocr classification() 非线程安全
_digit_infer_lock = threading.Lock()

# ── ddddocr 实例池 ──
_digit_pool: List[Tuple[object, threading.Lock]] = []
_digit_pool_lock = threading.Lock()
_digit_pool_index = 0


def configure_tesseract() -> None:
    """配置 Tesseract 可执行文件路径和语言包目录（可选）。

    TESSDATA_PREFIX：Tesseract 查找 .traineddata 文件的目录，
    对应 settings.tesseract_data_dir（默认 E:\\new_oas\\Oas2.0\\ocr_model）。
    tesseract_cmd：留空时自动在 PATH 中查找 tesseract 可执行文件。
    """
    if settings.tesseract_data_dir:
        os.environ["TESSDATA_PREFIX"] = settings.tesseract_data_dir
        logger.info("Tesseract 语言包目录: {}", settings.tesseract_data_dir)
    if not settings.tesseract_cmd:
        return
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        logger.info("Tesseract 可执行文件路径已配置: {}", settings.tesseract_cmd)
    except ImportError as e:
        logger.error("pytesseract 导入失败，请执行: pip install pytesseract — {}", e)
        raise


def get_digit_ocr_engine():
    """获取 ddddocr 数字识别单例。

    使用 ddddocr 替代通用 OCR 数字专用模型，
    对小尺寸游戏数字识别准确率更高。
    """
    global _digit_instance
    if _digit_instance is not None:
        return _digit_instance

    with _digit_lock:
        if _digit_instance is not None:
            return _digit_instance

        logger.info("正在初始化 ddddocr 数字识别引擎...")
        import ddddocr  # noqa: delay import

        _digit_instance = ddddocr.DdddOcr(show_ad=False)
        logger.info("ddddocr 数字识别引擎初始化完成")
        return _digit_instance


def init_digit_pool(size: int = 2) -> None:
    """初始化 ddddocr 数字识别实例池。"""
    global _digit_pool
    with _digit_pool_lock:
        if _digit_pool:
            return

        engine0 = get_digit_ocr_engine()
        _digit_pool.append((engine0, _digit_infer_lock))

        if size <= 1:
            logger.info("ddddocr 实例池已初始化: 1 个实例（单例模式）")
            return

        import ddddocr
        for i in range(1, size):
            logger.info(f"正在创建 ddddocr 实例 #{i + 1}/{size}...")
            instance = ddddocr.DdddOcr(show_ad=False)
            _digit_pool.append((instance, threading.Lock()))

        logger.info(f"ddddocr 实例池已初始化: {size} 个实例")


def acquire_digit_ocr() -> Tuple[object, threading.Lock]:
    """从 ddddocr 池中轮询获取一个 (engine, lock) 对。

    池未初始化时回退到单例 + 全局锁。
    """
    global _digit_pool_index
    if not _digit_pool:
        return get_digit_ocr_engine(), _digit_infer_lock

    with _digit_pool_lock:
        idx = _digit_pool_index % len(_digit_pool)
        _digit_pool_index += 1

    return _digit_pool[idx]
