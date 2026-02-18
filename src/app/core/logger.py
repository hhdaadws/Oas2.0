"""
日志配置模块
"""
import atexit
import inspect
import logging
import os
import sys
import threading
from pathlib import Path
from loguru import logger
from .config import settings

_LOG_INIT_LOCK = threading.RLock()
_LOGGER_INITIALIZED = False
_ATEXIT_REGISTERED = False
_ACCOUNT_SINK_IDS: dict[str, int] = {}

_APP_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)
_CONSOLE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)
_ACCOUNT_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
_STD_LOGGER_NAMES = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
    "starlette",
    "asyncio",
)


def _is_stream_writable(stream: object) -> bool:
    if stream is None:
        return False
    if getattr(stream, "closed", False):
        return False
    return callable(getattr(stream, "write", None))


def _resolve_console_sink():
    candidates = (
        getattr(sys, "stdout", None),
        getattr(sys, "stderr", None),
        getattr(sys, "__stdout__", None),
        getattr(sys, "__stderr__", None),
    )
    seen = set()
    for stream in candidates:
        if stream is None:
            continue
        stream_id = id(stream)
        if stream_id in seen:
            continue
        seen.add(stream_id)
        if _is_stream_writable(stream):
            return stream
    return None


class InterceptHandler(logging.Handler):
    """将标准 logging 日志桥接到 Loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("loguru"):
            return

        try:
            level = logger.level(record.levelname).name
        except (ValueError, TypeError):
            level = record.levelno

        frame = inspect.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.bind(std_logger=record.name).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


def _normalize_file_format() -> str:
    log_file_format = (settings.log_file_format or "").strip().lower()
    if log_file_format in {"text", "json"}:
        return log_file_format
    return "text"


def _resolve_rotation() -> str:
    rotation = (settings.log_rotation or "").strip()
    return rotation or "00:00"


def _resolve_stdlib_level(level_name: str) -> int:
    return getattr(logging, (level_name or "INFO").upper(), logging.INFO)


def _is_access_record(record: dict) -> bool:
    return record["extra"].get("std_logger") == "uvicorn.access"


def _is_non_access_record(record: dict) -> bool:
    return not _is_access_record(record)


def _resolve_log_dir() -> Path:
    log_dir = Path(settings.log_path).expanduser()
    if not log_dir.is_absolute():
        log_dir = (Path.cwd() / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _resolve_access_log_path(log_dir: Path) -> Path:
    custom_path = (settings.log_access_path or "").strip()
    if not custom_path:
        return log_dir / "access_{time:YYYY-MM-DD}.log"

    access_log_path = Path(custom_path).expanduser()
    if not access_log_path.is_absolute():
        access_log_path = (Path.cwd() / access_log_path).resolve()
    access_log_path.parent.mkdir(parents=True, exist_ok=True)
    return access_log_path


def _register_atexit_flush() -> None:
    global _ATEXIT_REGISTERED
    if _ATEXIT_REGISTERED:
        return

    def _flush_log_queue() -> None:
        try:
            complete_result = logger.complete()
            if inspect.isawaitable(complete_result):
                iterator = complete_result.__await__()
                while True:
                    try:
                        next(iterator)
                    except StopIteration:
                        break
        except Exception:
            pass

    atexit.register(_flush_log_queue)
    _ATEXIT_REGISTERED = True


def configure_stdlib_logging_bridge() -> None:
    """将标准 logging（含 uvicorn）统一转发到 Loguru。"""
    intercept_handler = InterceptHandler()
    root_logger = logging.getLogger()
    root_logger.handlers = [intercept_handler]
    root_logger.setLevel(_resolve_stdlib_level(settings.log_level))

    for logger_name in _STD_LOGGER_NAMES:
        std_logger = logging.getLogger(logger_name)
        std_logger.handlers = [intercept_handler]
        std_logger.setLevel(logging.NOTSET)
        std_logger.propagate = False


def setup_logger(force: bool = False):
    """配置日志系统"""
    global _LOGGER_INITIALIZED

    with _LOG_INIT_LOCK:
        if _LOGGER_INITIALIZED and not force:
            return logger

    # 强制标准输出使用 UTF-8，避免 Windows 控制台乱码
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        # 移除默认处理器
        logger.remove()
        _ACCOUNT_SINK_IDS.clear()

        log_dir = _resolve_log_dir()
        rotation = _resolve_rotation()
        serialize = _normalize_file_format() == "json"
        enqueue = bool(settings.log_enqueue_enabled)
        common_sink_kwargs = {
            "rotation": rotation,
            "encoding": "utf-8",
            "enqueue": enqueue,
            "backtrace": False,
            "diagnose": False,
            "serialize": serialize,
        }

        console_sink_missing = False
        if settings.log_console_enabled:
            console_sink = _resolve_console_sink()
            if console_sink is not None:
                logger.add(
                    console_sink,
                    level=settings.log_level,
                    format=_CONSOLE_LOG_FORMAT,
                    enqueue=enqueue,
                    backtrace=False,
                    diagnose=False,
                )
            else:
                console_sink_missing = True

        # 文件输出 - 全局日志（排除 access）
        logger.add(
            log_dir / "app_{time:YYYY-MM-DD}.log",
            level=settings.log_level,
            format=_APP_LOG_FORMAT,
            retention=f"{settings.log_retention_days} days",
            filter=_is_non_access_record,
            **common_sink_kwargs,
        )

        # 错误日志单独记录（排除 access）
        logger.add(
            log_dir / "error_{time:YYYY-MM-DD}.log",
            level="ERROR",
            format=_APP_LOG_FORMAT,
            retention=f"{settings.log_retention_days * 2} days",
            filter=_is_non_access_record,
            **common_sink_kwargs,
        )

        if settings.log_access_enabled:
            logger.add(
                _resolve_access_log_path(log_dir),
                level=settings.log_level,
                format=_APP_LOG_FORMAT,
                retention=f"{settings.log_retention_days} days",
                filter=_is_access_record,
                **common_sink_kwargs,
            )

        if console_sink_missing:
            logger.warning(
                "未检测到可用控制台输出流，已自动跳过控制台日志输出"
            )

        configure_stdlib_logging_bridge()
        _register_atexit_flush()
        _LOGGER_INITIALIZED = True
        return logger


def get_account_logger(account_id: str):
    """获取账号专用日志器"""
    with _LOG_INIT_LOCK:
        sink_id = _ACCOUNT_SINK_IDS.get(account_id)
        if sink_id is None:
            account_log_dir = _resolve_log_dir() / "accounts"
            account_log_dir.mkdir(parents=True, exist_ok=True)
            sink_id = logger.add(
                account_log_dir / f"account_{account_id}_{{time:YYYY-MM-DD}}.log",
                level=settings.log_level,
                format=_ACCOUNT_LOG_FORMAT,
                rotation=_resolve_rotation(),
                retention=f"{settings.log_retention_days} days",
                encoding="utf-8",
                enqueue=bool(settings.log_enqueue_enabled),
                backtrace=False,
                diagnose=False,
                serialize=_normalize_file_format() == "json",
                filter=lambda record, aid=account_id: (
                    record["extra"].get("account_id") == aid
                ),
            )
            _ACCOUNT_SINK_IDS[account_id] = sink_id

    return logger.bind(account_id=account_id)


# 初始化日志系统
logger = setup_logger()
