"""PaddleOCR 引擎管理（懒加载 + 线程安全 + 实例池支持并行推理）。"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Tuple

from ...core.config import settings
from ...core.logger import logger

# ── 在导入 PaddleOCR 之前设置环境变量，防止自动下载模型 ──
_ocr_dir = str(Path(settings.ocr_model_dir).resolve())
os.environ.setdefault('PADDLEX_HOME', _ocr_dir)
os.environ.setdefault('PPOCR_HOME', _ocr_dir)
os.environ.setdefault('HUB_HOME', _ocr_dir)
os.environ.setdefault('PADDLE_HOME', _ocr_dir)
os.environ.setdefault('PADDLEX_DOWNLOAD', '0')
os.environ.setdefault('USE_PADDLEX', '0')
os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

# ── 单例（兼容旧代码） ──
_ocr_instance = None
_ocr_lock = threading.Lock()
# 推理锁：PaddleOCR predict() 非线程安全，多线程并发调用需串行化
_ocr_infer_lock = threading.Lock()

_digit_instance = None
_digit_lock = threading.Lock()
# 推理锁：ddddocr classification() 非线程安全
_digit_infer_lock = threading.Lock()

# ── 实例池 ──
_ocr_pool: List[Tuple[object, threading.Lock]] = []
_ocr_pool_lock = threading.Lock()
_ocr_pool_index = 0

_digit_pool: List[Tuple[object, threading.Lock]] = []
_digit_pool_lock = threading.Lock()
_digit_pool_index = 0


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
        try:
            from paddleocr import PaddleOCR  # noqa: delay import
        except ImportError as e:
            logger.error(f"PaddleOCR 导入失败，请检查依赖: {e}")
            raise

        try:
            _ocr_instance = PaddleOCR(
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                lang=settings.paddle_ocr_lang,
                device="cpu",
                # mkldnn 加速：PaddlePaddle 3.0.0 (conda timeocr) 无 PIR+oneDNN bug
                enable_mkldnn=True,
            )
        except Exception as e:
            # PaddleOCR 3.x 依赖 paddlex 进行 pipeline 创建
            try:
                import paddlex  # noqa
            except ImportError:
                logger.error(
                    "paddlex 未安装，PaddleOCR 3.x 需要此依赖，"
                    "请执行: pip install paddlex"
                )
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise
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


# ── 实例池管理 ──

def init_ocr_pool(size: int = 2) -> None:
    """初始化 OCR 实例池（应用启动时调用）。

    创建 N 个独立的 PaddleOCR 实例，每个带独立推理锁，
    支持真正的 N 路并行推理。首个实例复用单例。
    """
    global _ocr_pool
    with _ocr_pool_lock:
        if _ocr_pool:
            return

        # 第一个实例复用单例
        engine0 = get_ocr_engine()
        _ocr_pool.append((engine0, _ocr_infer_lock))

        if size <= 1:
            logger.info("OCR 实例池已初始化: 1 个实例（单例模式）")
            return

        from paddleocr import PaddleOCR
        for i in range(1, size):
            logger.info(f"正在创建 OCR 实例 #{i + 1}/{size}...")
            instance = PaddleOCR(
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                lang=settings.paddle_ocr_lang,
                device="cpu",
                enable_mkldnn=True,
            )
            _ocr_pool.append((instance, threading.Lock()))

        logger.info(f"OCR 实例池已初始化: {size} 个实例")


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


def acquire_ocr() -> Tuple[object, threading.Lock]:
    """从 OCR 池中轮询获取一个 (engine, lock) 对。

    池未初始化时回退到单例 + 全局锁。
    """
    global _ocr_pool_index
    if not _ocr_pool:
        return get_ocr_engine(), _ocr_infer_lock

    with _ocr_pool_lock:
        idx = _ocr_pool_index % len(_ocr_pool)
        _ocr_pool_index += 1

    return _ocr_pool[idx]


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
