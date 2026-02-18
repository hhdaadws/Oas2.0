# -*- coding: utf-8 -*-
"""数据库模块"""
from .base import Base, engine, SessionLocal, get_db
from .models import (
    GameAccount, AccountRestConfig, Task, CoopPool,
    Emulator, Log, Worker, TaskRun, RestPlan, SystemConfig,
    CoopAccount, CoopWindow
)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)
    _migrate_login_id_unique_constraint()
    _migrate_system_config_columns()
    _migrate_lineup_config_column()
    _migrate_shikigami_config_column()
    _migrate_explore_progress_column()
    _migrate_remark_column()
    _migrate_asset_columns()
    _ensure_coop_schema()
    _migrate_pull_settings_columns()
    _migrate_default_fail_delays_column()
    _migrate_global_task_switches_column()
    _migrate_fanhe_level_column()
    _migrate_jiuhu_level_column()
    _migrate_liao_level_column()
    _fix_fanhe_jiuhu_level_zero()
    _migrate_rest_config_enabled_column()
    _ensure_performance_indexes()
    _migrate_save_fail_screenshot_column()
    _migrate_cross_emulator_cache_enabled_column()
    _migrate_default_task_enabled_column()
    _migrate_drop_zone_column()
    _migrate_global_rest_columns()
    _migrate_duiyi_jingcai_answers_column()
    _migrate_duiyi_reward_coord_column()


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
            for name in ("nemu_folder", "activity_name", "python_path", "capture_method"):
                if name not in cols:
                    missing.add(name)

            for name in missing:
                if name == "nemu_folder":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN nemu_folder VARCHAR(500)")
                elif name == "activity_name":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN activity_name VARCHAR(200) DEFAULT '.MainActivity'")
                elif name == "python_path":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN python_path VARCHAR(1000)")
                elif name == "capture_method":
                    conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN capture_method VARCHAR(20) DEFAULT 'adb'")
    except Exception as e:
        try:
            from ..core.logger import logger

            logger.error(f"system_config 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_lineup_config_column():
    """确保 game_accounts 表包含 lineup_config 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'lineup_config' in cols:
                return
            conn.exec_driver_sql("ALTER TABLE game_accounts ADD COLUMN lineup_config JSON DEFAULT '{}'")
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"lineup_config 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_shikigami_config_column():
    """确保 game_accounts 表包含 shikigami_config 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'shikigami_config' in cols:
                return
            conn.exec_driver_sql("ALTER TABLE game_accounts ADD COLUMN shikigami_config JSON DEFAULT '{}'")
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"shikigami_config 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_explore_progress_column():
    """确保 game_accounts 表包含 explore_progress 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'explore_progress' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE game_accounts ADD COLUMN explore_progress JSON DEFAULT '{}'"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"explore_progress 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_remark_column():
    """确保 game_accounts 表包含 remark 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'remark' in cols:
                return
            conn.exec_driver_sql("ALTER TABLE game_accounts ADD COLUMN remark VARCHAR(500) DEFAULT ''")
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"remark 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_asset_columns():
    """确保 game_accounts 表包含 gouyu、lanpiao、gold、gongxun 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols:
                return
            for col_name in ("gouyu", "lanpiao", "gold", "gongxun", "xunzhang", "tupo_ticket"):
                if col_name not in cols:
                    conn.exec_driver_sql(
                        f"ALTER TABLE game_accounts ADD COLUMN {col_name} INTEGER DEFAULT 0"
                    )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"资产列迁移失败: {e}")
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


def _migrate_pull_settings_columns():
    """确保 system_config 表包含 pull_post_mode 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols:
                return
            if 'pull_post_mode' not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE system_config ADD COLUMN pull_post_mode VARCHAR(20) DEFAULT 'none'"
                )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"pull_settings 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_default_fail_delays_column():
    """确保 system_config 表包含 default_fail_delays 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'default_fail_delays' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN default_fail_delays JSON"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"default_fail_delays 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_global_task_switches_column():
    """确保 system_config 表包含 global_task_switches 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'global_task_switches' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN global_task_switches JSON"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"global_task_switches 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_save_fail_screenshot_column():
    """确保 system_config 表包含 save_fail_screenshot 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'save_fail_screenshot' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN save_fail_screenshot BOOLEAN DEFAULT 0"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"save_fail_screenshot 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_cross_emulator_cache_enabled_column():
    """确保 system_config 表包含 cross_emulator_cache_enabled 列。"""
    try:
        from ..core.logger import logger

        with engine.begin() as conn:
            cols = [
                r[1]
                for r in conn.exec_driver_sql(
                    "PRAGMA table_info('system_config')"
                ).fetchall()
            ]
            if not cols or "cross_emulator_cache_enabled" in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN cross_emulator_cache_enabled BOOLEAN DEFAULT 0"
            )
            logger.info("已为 system_config 表新增 cross_emulator_cache_enabled 列")
    except Exception as e:
        try:
            from ..core.logger import logger

            logger.error(f"cross_emulator_cache_enabled 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_fanhe_level_column():
    """确保 game_accounts 表包含 fanhe_level 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'fanhe_level' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE game_accounts ADD COLUMN fanhe_level INTEGER DEFAULT 1"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"fanhe_level 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_jiuhu_level_column():
    """确保 game_accounts 表包含 jiuhu_level 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'jiuhu_level' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE game_accounts ADD COLUMN jiuhu_level INTEGER DEFAULT 1"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"jiuhu_level 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_liao_level_column():
    """确保 game_accounts 表包含 liao_level 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if not cols or 'liao_level' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE game_accounts ADD COLUMN liao_level INTEGER DEFAULT 0"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"liao_level 列迁移失败: {e}")
        except Exception:
            pass


def _fix_fanhe_jiuhu_level_zero():
    """将已有数据中 fanhe_level/jiuhu_level 为 0 的记录修正为 1（起始等级）。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE game_accounts SET fanhe_level = 1 WHERE fanhe_level = 0"
            )
            conn.exec_driver_sql(
                "UPDATE game_accounts SET jiuhu_level = 1 WHERE jiuhu_level = 0"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"修复 fanhe/jiuhu level 失败: {e}")
        except Exception:
            pass


def _migrate_rest_config_enabled_column():
    """确保 account_rest_configs 表包含 enabled 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('account_rest_configs')").fetchall()]
            if not cols or 'enabled' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE account_rest_configs ADD COLUMN enabled INTEGER DEFAULT 1"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"rest_config enabled 列迁移失败: {e}")
        except Exception:
            pass


def _ensure_performance_indexes():
    """Ensure high-frequency query indexes exist for legacy databases."""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            statements = [
                "CREATE INDEX IF NOT EXISTS ix_task_runs_started_at ON task_runs (started_at);",
                "CREATE INDEX IF NOT EXISTS ix_task_runs_status ON task_runs (status);",
                "CREATE INDEX IF NOT EXISTS ix_game_accounts_status ON game_accounts (status);",
                "CREATE INDEX IF NOT EXISTS ix_game_accounts_progress ON game_accounts (progress);",
                "CREATE INDEX IF NOT EXISTS ix_game_accounts_status_progress ON game_accounts (status, progress);",
            ]
            for statement in statements:
                conn.exec_driver_sql(statement)
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"failed to ensure performance indexes: {e}")
        except Exception:
            pass


def _migrate_default_task_enabled_column():
    """确保 system_config 表包含 default_task_enabled 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'default_task_enabled' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN default_task_enabled JSON"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"default_task_enabled 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_drop_zone_column():
    """删除 game_accounts 表中多余的 zone 列（如存在）。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('game_accounts')").fetchall()]
            if 'zone' not in cols:
                return
            conn.exec_driver_sql("ALTER TABLE game_accounts DROP COLUMN zone")
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"删除 zone 列失败: {e}")
        except Exception:
            pass


def _migrate_global_rest_columns():
    """确保 system_config 表包含 global_rest_enabled 和 default_rest_config 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols:
                return
            if 'global_rest_enabled' not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE system_config ADD COLUMN global_rest_enabled BOOLEAN DEFAULT 1"
                )
            if 'default_rest_config' not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE system_config ADD COLUMN default_rest_config JSON"
                )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"global_rest 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_duiyi_jingcai_answers_column():
    """确保 system_config 表包含 duiyi_jingcai_answers 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'duiyi_jingcai_answers' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN duiyi_jingcai_answers JSON"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"duiyi_jingcai_answers 列迁移失败: {e}")
        except Exception:
            pass


def _migrate_duiyi_reward_coord_column():
    """确保 system_config 表包含 duiyi_reward_coord 列。"""
    try:
        if engine.url.get_backend_name() != 'sqlite':
            return
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info('system_config')").fetchall()]
            if not cols or 'duiyi_reward_coord' in cols:
                return
            conn.exec_driver_sql(
                "ALTER TABLE system_config ADD COLUMN duiyi_reward_coord JSON"
            )
    except Exception as e:
        try:
            from ..core.logger import logger
            logger.error(f"duiyi_reward_coord 列迁移失败: {e}")
        except Exception:
            pass


__all__ = [
    "Base", "engine", "SessionLocal", "get_db", "init_db",
    "GameAccount", "AccountRestConfig", "Task", "CoopPool",
    "Emulator", "Log", "Worker", "TaskRun", "RestPlan", "SystemConfig",
    "CoopAccount", "CoopWindow"
]
