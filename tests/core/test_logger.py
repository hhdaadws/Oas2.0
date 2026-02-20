import inspect
import logging
import sys
from uuid import uuid4

import pytest


def _flush_loguru(logger_module) -> None:
    complete_result = logger_module.logger.complete()
    if inspect.isawaitable(complete_result):
        iterator = complete_result.__await__()
        while True:
            try:
                next(iterator)
            except StopIteration:
                break


def _latest_log_file(log_dir, pattern):
    files = sorted(log_dir.glob(pattern))
    assert files, f"missing log file pattern: {pattern}"
    return files[-1]


@pytest.fixture()
def configured_logger(tmp_path):
    from app.core.config import settings
    import app.core.logger as logger_module

    original = {
        "log_level": settings.log_level,
        "log_path": settings.log_path,
        "log_retention_days": settings.log_retention_days,
        "log_console_enabled": settings.log_console_enabled,
        "log_enqueue_enabled": settings.log_enqueue_enabled,
        "log_file_format": settings.log_file_format,
        "log_access_enabled": settings.log_access_enabled,
        "log_access_path": settings.log_access_path,
        "log_rotation": settings.log_rotation,
    }

    settings.log_level = "INFO"
    settings.log_path = str(tmp_path)
    settings.log_retention_days = 3
    settings.log_console_enabled = False
    settings.log_enqueue_enabled = False
    settings.log_file_format = "text"
    settings.log_access_enabled = True
    settings.log_access_path = ""
    settings.log_rotation = "00:00"
    logger_module.setup_logger(force=True)

    try:
        yield logger_module, tmp_path
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
        logger_module.setup_logger(force=True)


def test_file_output_written(configured_logger):
    logger_module, log_dir = configured_logger
    message = f"file-output-{uuid4()}"

    logger_module.logger.info(message)
    _flush_loguru(logger_module)

    app_log_path = _latest_log_file(log_dir, "app_*.log")
    content = app_log_path.read_text(encoding="utf-8")
    assert message in content


def test_stdlib_uvicorn_error_bridged(configured_logger):
    logger_module, log_dir = configured_logger
    message = f"uvicorn-error-{uuid4()}"

    logging.getLogger("uvicorn.error").info(message)
    _flush_loguru(logger_module)

    app_log_path = _latest_log_file(log_dir, "app_*.log")
    content = app_log_path.read_text(encoding="utf-8")
    assert message in content


def test_access_log_split_from_app_log(configured_logger):
    logger_module, log_dir = configured_logger
    message = f"uvicorn-access-{uuid4()}"

    logging.getLogger("uvicorn.access").info(message)
    _flush_loguru(logger_module)

    access_log_path = _latest_log_file(log_dir, "access_*.log")
    access_content = access_log_path.read_text(encoding="utf-8")
    assert message in access_content

    app_log_paths = sorted(log_dir.glob("app_*.log"))
    app_content = "".join(path.read_text(encoding="utf-8") for path in app_log_paths)
    assert message not in app_content


def test_setup_logger_idempotent_when_forced_twice(configured_logger):
    logger_module, log_dir = configured_logger
    message = f"idempotent-{uuid4()}"

    logger_module.setup_logger(force=True)
    logger_module.setup_logger(force=True)
    logger_module.logger.info(message)
    _flush_loguru(logger_module)

    app_log_path = _latest_log_file(log_dir, "app_*.log")
    content = app_log_path.read_text(encoding="utf-8")
    assert content.count(message) == 1


def test_get_account_logger_reuses_sink(configured_logger):
    logger_module, log_dir = configured_logger
    message = f"account-log-{uuid4()}"

    logger_module.get_account_logger("1")
    account_logger = logger_module.get_account_logger("1")
    account_logger.info(message)
    _flush_loguru(logger_module)

    account_log_path = _latest_log_file(log_dir / "accounts", "account_1_*.log")
    content = account_log_path.read_text(encoding="utf-8")
    assert content.count(message) == 1


def test_console_sink_degrades_when_std_streams_missing(tmp_path, monkeypatch):
    from app.core.config import settings
    import app.core.logger as logger_module

    original = {
        "log_level": settings.log_level,
        "log_path": settings.log_path,
        "log_retention_days": settings.log_retention_days,
        "log_console_enabled": settings.log_console_enabled,
        "log_enqueue_enabled": settings.log_enqueue_enabled,
        "log_file_format": settings.log_file_format,
        "log_access_enabled": settings.log_access_enabled,
        "log_access_path": settings.log_access_path,
        "log_rotation": settings.log_rotation,
    }

    monkeypatch.setattr(sys, "stdout", None, raising=False)
    monkeypatch.setattr(sys, "stderr", None, raising=False)
    monkeypatch.setattr(sys, "__stdout__", None, raising=False)
    monkeypatch.setattr(sys, "__stderr__", None, raising=False)

    settings.log_level = "INFO"
    settings.log_path = str(tmp_path)
    settings.log_retention_days = 3
    settings.log_console_enabled = True
    settings.log_enqueue_enabled = False
    settings.log_file_format = "text"
    settings.log_access_enabled = False
    settings.log_access_path = ""
    settings.log_rotation = "00:00"

    try:
        logger_module.setup_logger(force=True)
        message = f"windowed-log-{uuid4()}"
        logger_module.logger.info(message)
        _flush_loguru(logger_module)

        app_log_path = _latest_log_file(tmp_path, "app_*.log")
        content = app_log_path.read_text(encoding="utf-8")
        assert message in content
        assert "未检测到可用控制台输出流" in content
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
        logger_module.setup_logger(force=True)
