import asyncio
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_account_logs_endpoint.db"

_real_create_engine = sqlalchemy.create_engine


def _patched_create_engine(*args, **kwargs):
    try:
        return _real_create_engine(*args, **kwargs)
    except TypeError as exc:
        if "Invalid argument(s) 'pool_size','max_overflow'" not in str(exc):
            raise
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        return _real_create_engine(*args, **kwargs)


sqlalchemy.create_engine = _patched_create_engine

if "loguru" not in sys.modules:
    class _DummyLogger:
        def bind(self, **kwargs):
            return self

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    sys.modules["loguru"] = types.SimpleNamespace(logger=_DummyLogger())

if "app.modules.web" not in sys.modules:
    root_dir = Path(__file__).resolve().parents[3]
    web_pkg = types.ModuleType("app.modules.web")
    web_pkg.__path__ = [str(root_dir / "src" / "app" / "modules" / "web")]
    sys.modules["app.modules.web"] = web_pkg

from app.db.base import Base
from app.db.models import GameAccount, Log
from app.modules.web.routers.accounts import get_account_logs


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_accounts_and_logs(db):
    account_a = GameAccount(login_id="acc_a")
    account_b = GameAccount(login_id="acc_b")
    db.add_all([account_a, account_b])
    db.commit()
    db.refresh(account_a)
    db.refresh(account_b)

    base_ts = datetime(2026, 2, 1, 12, 0, 0)
    db.add_all(
        [
            Log(
                account_id=account_a.id,
                type="task",
                level="INFO",
                message="a-info",
                ts=base_ts,
            ),
            Log(
                account_id=account_a.id,
                type="task",
                level="WARNING",
                message="a-warning",
                ts=base_ts + timedelta(minutes=1),
            ),
            Log(
                account_id=account_a.id,
                type="task",
                level="ERROR",
                message="a-error",
                ts=base_ts + timedelta(minutes=2),
            ),
            Log(
                account_id=account_b.id,
                type="task",
                level="INFO",
                message="b-info",
                ts=base_ts + timedelta(minutes=3),
            ),
        ]
    )
    db.commit()
    return account_a.id, account_b.id


def test_get_account_logs_filters_by_account_and_desc_order(db_session):
    account_a_id, _ = _seed_accounts_and_logs(db_session)

    result = asyncio.run(
        get_account_logs(
            account_id=account_a_id,
            limit=30,
            offset=0,
            level=None,
            db=db_session,
        )
    )

    assert result["total"] == 3
    assert [row["message"] for row in result["logs"]] == [
        "a-error",
        "a-warning",
        "a-info",
    ]
    assert all(row["account_id"] == account_a_id for row in result["logs"])


def test_get_account_logs_level_filter_and_pagination(db_session):
    account_a_id, _ = _seed_accounts_and_logs(db_session)

    level_filtered = asyncio.run(
        get_account_logs(
            account_id=account_a_id,
            limit=30,
            offset=0,
            level="warning",
            db=db_session,
        )
    )
    assert level_filtered["total"] == 1
    assert [row["message"] for row in level_filtered["logs"]] == ["a-warning"]

    paged = asyncio.run(
        get_account_logs(
            account_id=account_a_id,
            limit=1,
            offset=1,
            level=None,
            db=db_session,
        )
    )
    assert paged["total"] == 3
    assert [row["message"] for row in paged["logs"]] == ["a-warning"]


def test_get_account_logs_returns_404_when_account_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            get_account_logs(
                account_id=999999,
                limit=30,
                offset=0,
                level=None,
                db=db_session,
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "账号不存在"
