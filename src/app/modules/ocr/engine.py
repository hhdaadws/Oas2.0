"""PaddleOCR 引擎单例管理（懒加载 + 线程安全）。"""
from __future__ import annotations

import os
import threading

from ...core.config import settings
from ...core.logger import logger

# ── 在导入 PaddleOCR 之前设置环境变量，防止自动下载模型 ──
os.environ.setdefault('PADDLEX_HOME', settings.ocr_model_dir)
os.environ.setdefault('PPOCR_HOME', settings.ocr_model_dir)
os.environ.setdefault('HUB_HOME', settings.ocr_model_dir)
os.environ.setdefault('PADDLE_HOME', settings.ocr_model_dir)
os.environ.setdefault('PADDLEX_DOWNLOAD', '0')
os.environ.setdefault('USE_PADDLEX', '0')

_ocr_instance = None
_ocr_lock = threading.Lock()

_digit_instance = None
_digit_lock = threading.Lock()


def get_ocr_engine():
    """获取 PaddleOCR 单例。

    首次调用时初始化引擎（约 3-5 秒），后续调用直接返回缓存实例。
    线程安全（双检锁）。
    使用本地模型目录，不从网络下载。
    """
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance

    with _ocr_lock:
        if _ocr_instance is not None:
            return _ocr_instance

        logger.info(
            "正在初始化 PaddleOCR (lang={})...",
            settings.paddle_ocr_lang,
        )
        from paddleocr import PaddleOCR  # noqa: delay import

        _ocr_instance = PaddleOCR(
            use_textline_orientation=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            lang=settings.paddle_ocr_lang,
            device="cpu",
            # mkldnn 加速：PaddlePaddle 3.0.0 (conda timeocr) 无 PIR+oneDNN bug
            enable_mkldnn=True,
        )
        logger.info("PaddleOCR 初始化完成（本地模型）")
        return _ocr_instance


def get_digit_ocr_engine():
    """获取 ddddocr 数字识别单例。

    使用 ddddocr 替代 PaddleOCR 数字专用模型，
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
