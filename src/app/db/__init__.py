# -*- coding: utf-8 -*-
"""数据库模块"""
from .base import Base, engine, SessionLocal, get_db
from .models import (
    Email, GameAccount, AccountRestConfig, Task, CoopPool,
    Emulator, Log, Worker, TaskRun, RestPlan, SystemConfig,
    CoopAccount, CoopWindow
)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)
    _migrate_login_id_unique_constraint()
    _migrate_system_config_columns()
    _ensure_coop_schema()


def _migrate_login_id_unique_constraint():
    """确保 game_accounts.login_id 仅在 login_id <> '-1' 时唯一。

    对旧库（login_id 全局唯一）执行一次性迁移：
    - 重建 game_accounts 表，移除列级唯一约束
    - 创建部分唯一索引：WHERE login_id <> '-1'
    """
    try:
        from sqlalchemy import inspect

        with engine.begin() as conn:
            if engine.url.get_backend_name() != 'sqlite':
                # 非SQLite暂不自动迁移
                return

            # 读取当前表DDL
            row = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='game_accounts'"
            ).fetchone()
            if not row or not row[0]:
                return

            create_sql = row[0]

            # 检查是否包含对 login_id 的 UNIQUE 约束（列级或表级）
            need_rebuild = 'UNIQUE' in create_sql and 'login_id' in create_sql

            if need_rebuild:
                # 获取列列表，保持原顺序
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]

                # 重建表：去掉 login_id 的 UNIQUE 约束（支持表级 UNIQUE(login_id) 及列内 UNIQUE）
                import re

                new_sql = create_sql
                # 移除表级 UNIQUE(login_id) 约束（含可选引号与前后逗号位置）
                new_sql = re.sub(r",\s*UNIQUE\s*\(\s*\"?login_id\"?\s*\)\s*", ", ", new_sql, flags=re.IGNORECASE)
                new_sql = re.sub(r"UNIQUE\s*\(\s*\"?login_id\"?\s*\)\s*,\s*", "", new_sql, flags=re.IGNORECASE)
                new_sql = re.sub(r"UNIQUE\s*\(\s*\"?login_id\"?\s*\)\s*", "", new_sql, flags=re.IGNORECASE)

                # 移除列定义中的 UNIQUE 关键字（以及可选的 ON CONFLICT 子句），保留其他约束
                def _strip_inline_unique(match):
                    prefix = match.group(1)
                    return prefix

                new_sql = re.sub(
                    r"(?i)(\b\"?login_id\"?\s+[^,]*?)\bUNIQUE\b(?:\s+ON\s+CONFLICT\s+\w+)?",
                    _strip_inline_unique,
                    new_sql,
                )

                # 关闭外键约束，开始迁移
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF;")
                conn.exec_driver_sql("ALTER TABLE game_accounts RENAME TO game_accounts_backup;")
                conn.exec_driver_sql(new_sql)
                col_list = ", ".join([f'"{c}"' for c in cols])
                conn.exec_driver_sql(
                    f"INSERT INTO game_accounts ({col_list}) SELECT {col_list} FROM game_accounts_backup;"
                )
                conn.exec_driver_sql("DROP TABLE game_accounts_backup;")
                conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

            # 删除可能存在的旧的全局唯一索引（覆盖所有 login_id 的唯一索引）
            for name, sql in conn.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='game_accounts' AND sql IS NOT NULL"
            ).fetchall():
                try:
                    s = sql.upper()
                    if "UNIQUE" in s and "(LOGIN_ID)" in s and "WHERE" not in s:
                        conn.exec_driver_sql(f'DROP INDEX IF EXISTS "{name}";')
                except Exception:
                    pass

            # 创建部分唯一索引（如不存在）
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_game_accounts_login_id_nonminus1 "
                "ON game_accounts (login_id) WHERE login_id <> '-1';"
            )
    except Exception as e:
        # 迁移失败不应阻断应用启动，仅记录日志
        try:
            from ..core.logger import logger

            logger.error(f"login_id 索引迁移失败: {e}")
        except Exception:
            pass


def _migrate_system_config_columns():
    """确保 system_config 表包含最新字段（SQLite 仅支持 ADD COLUMN 方式）。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            # 如果表不存在，create_all 已创建，这里主要处理旧表缺失的列
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols:
                return
            missing = set()
            for name in ("nemu_folder", "activity_name", "python_path"):
                if name not in cols:
                    missing.add(name)

            for name in missing:
                if name == "nemu_folder":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN nemu_folder VARCHAR(500)")
                elif name == "activity_name":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN activity_name VARCHAR(200) DEFAULT '.MainActivity'")
                elif name == "python_path":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN python_path VARCHAR(1000)")
    except Exception as e:
        try:
            from ..core.logger import logger

            logger.error(f"system_config 列迁移失败: {e}")
        except Exception:
            pass


def _ensure_coop_schema():
    """确保勾协相关表（coop_accounts/coop_windows）存在，且 coop_pools 为新结构。

    - 若发现旧结构（account_id/linked_account_id），直接重建为新结构（owner_account_id/coop_account_id）。
    - 不迁移旧数据（按产品决策）。
    """
    try:
        if engine.url.get_backend_name() != 'sqlite':
            # 简化：当前仅对SQLite做自动修复；其他DB假定由迁移工具处理
            return
        with engine.begin() as conn:
            # 确保新表存在
            Base.metadata.create_all(bind=engine)

            # 检查 coop_pools 结构
            row = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='coop_pools'"
            ).fetchone()
            if not row:
                return  # 表不存在，由 create_all 创建

            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('coop_pools')").fetchall()]
            if ('account_id' in cols) or ('linked_account_id' in cols):
                # 旧结构，直接重建
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF;")
                conn.exec_driver_sql("ALTER TABLE coop_pools RENAME TO coop_pools_backup;")
                # 使用 ORM 根据模型创建新表
                Base.metadata.create_all(bind=engine)
                # 放弃旧数据，删除备份表
                conn.exec_driver_sql("DROP TABLE coop_pools_backup;")
                conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

            # 确保 coop_accounts 增加 expire_date 列（如缺失）
            cols_acc = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('coop_accounts')").fetchall()]
            if 'expire_date' not in cols_acc:
                conn.exec_driver_sql("ALTER TABLE coop_accounts ADD COLUMN expire_date TEXT;")
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"勾协表结构校验/重建失败: {e}")
        except Exception:
            pass


__all__ = [
    "Base", "engine", "SessionLocal", "get_db", "init_db",
    "Email", "GameAccount", "AccountRestConfig", "Task", "CoopPool",
    "Emulator", "Log", "Worker", "TaskRun", "RestPlan", "SystemConfig",
    "CoopAccount", "CoopWindow"
]
