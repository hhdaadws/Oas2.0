"""
数据库基础配置
"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ..core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# 创建数据库引擎
# SQLite 多 Worker 并发优化:
#   - check_same_thread=False: 允许跨线程使用（ThreadPool offload 必需）
#   - timeout=30: busy_timeout 30秒，避免多 Worker 写入时 "database is locked"
#   - pool_size=20 + max_overflow=10: 10 模拟器 Worker 各自需要独立连接
#   - StaticPool 不适用于多线程，使用 QueuePool（默认）
if _is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_size=20,
        max_overflow=10,
    )
else:
    engine = create_engine(settings.database_url)


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """对每个新 SQLite 连接启用 WAL 模式和优化参数。"""
    cursor = dbapi_conn.cursor()
    # WAL 模式：允许并发读+单写，极大减少 "database is locked"
    cursor.execute("PRAGMA journal_mode=WAL")
    # synchronous=NORMAL: WAL 模式下安全且更快（默认 FULL 在 WAL 下不必要）
    cursor.execute("PRAGMA synchronous=NORMAL")
    # busy_timeout 30秒（与 connect_args.timeout 互为补充）
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


if _is_sqlite:
    event.listen(engine, "connect", _set_sqlite_pragma)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()