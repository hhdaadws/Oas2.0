"""
YAML 任务配置加载器

运行时加载、校验、缓存 YAML 配置文件。
支持热重载：通过文件修改时间检测变更，自动重新加载。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ...core.logger import logger


@dataclass
class _CacheEntry:
    config: Dict[str, Any]
    mtime: float


class YamlTaskLoader:
    """YAML 任务配置加载器（单例使用）"""

    def __init__(self, base_dir: str = "assets/tasks"):
        self._base_dir = Path(base_dir)
        self._cache: Dict[str, _CacheEntry] = {}
        self._log = logger.bind(module="YamlTaskLoader")

    def load(self, task_name: str) -> Optional[Dict[str, Any]]:
        """加载指定任务的 YAML 配置。

        支持热重载：文件修改后自动重新加载。

        Args:
            task_name: 任务名（如 "climb_tower"），对应文件 {base_dir}/{task_name}.yaml

        Returns:
            解析后的 dict，文件不存在或解析失败返回 None
        """
        file_path = self._base_dir / f"{task_name}.yaml"

        if not file_path.exists():
            self._log.warning(f"YAML 配置文件不存在: {file_path}")
            return None

        current_mtime = os.path.getmtime(file_path)
        cached = self._cache.get(task_name)

        # 缓存命中且文件未修改
        if cached and cached.mtime == current_mtime:
            return cached.config

        # 加载并缓存
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                self._log.error(f"YAML 配置格式错误（非 dict）: {file_path}")
                return None

            errors = self._validate(config)
            if errors:
                for err in errors:
                    self._log.error(f"YAML 校验失败 [{task_name}]: {err}")
                return None

            self._cache[task_name] = _CacheEntry(
                config=config,
                mtime=current_mtime,
            )
            self._log.info(f"YAML 配置已加载: {file_path}")
            return config

        except yaml.YAMLError as e:
            self._log.error(f"YAML 解析失败: {file_path}: {e}")
            return None
        except Exception as e:
            self._log.error(f"加载 YAML 配置异常: {file_path}: {e}")
            return None

    def is_enabled(self, task_name: str) -> bool:
        """检查任务的全局开关是否开启。"""
        config = self.load(task_name)
        if config is None:
            return False
        return config.get("enabled", False) is True

    @staticmethod
    def _validate(config: dict) -> List[str]:
        """基础结构校验。"""
        errors: List[str] = []

        # 顶层必须字段
        if "enabled" not in config:
            errors.append("缺少顶层 'enabled' 字段")

        # navigation 校验
        nav = config.get("navigation")
        if nav is None:
            errors.append("缺少 'navigation' 配置")
        elif not isinstance(nav.get("steps"), list):
            errors.append("navigation.steps 必须是列表")

        # ticket 校验
        ticket = config.get("ticket")
        if ticket is None:
            errors.append("缺少 'ticket' 配置")
        elif not isinstance(ticket.get("roi"), list) or len(ticket.get("roi", [])) != 4:
            errors.append("ticket.roi 必须是长度为 4 的列表 [x, y, w, h]")

        # battle 校验
        battle = config.get("battle")
        if battle is None:
            errors.append("缺少 'battle' 配置")
        else:
            if not battle.get("challenge_template"):
                errors.append("battle.challenge_template 不能为空")

        # rent 校验（可选区块，存在时校验内部字段）
        rent = config.get("rent")
        if rent is not None:
            for key in ("enter_template", "shikigami_template", "borrow_button", "exit_template"):
                if not rent.get(key):
                    errors.append(f"rent.{key} 不能为空")

        # lock 校验（可选区块，存在时校验内部字段）
        lock = config.get("lock")
        if lock is not None:
            tp = lock.get("toggle_pos")
            if not isinstance(tp, list) or len(tp) != 2:
                errors.append("lock.toggle_pos 必须是长度为 2 的列表 [x, y]")
            dr = lock.get("detect_roi")
            if not isinstance(dr, list) or len(dr) != 4:
                errors.append("lock.detect_roi 必须是长度为 4 的列表 [x, y, w, h]")

        # first_battle_lineup 校验（可选区块）
        fbl = config.get("first_battle_lineup")
        if fbl is not None:
            if not fbl.get("shangzhen_template"):
                errors.append("first_battle_lineup.shangzhen_template 不能为空")
            for coord_key in ("config_btn", "lineup_pos_1", "lineup_pos_2"):
                val = fbl.get(coord_key)
                if not isinstance(val, list) or len(val) != 2:
                    errors.append(
                        f"first_battle_lineup.{coord_key} 必须是长度为 2 的列表 [x, y]"
                    )

        # return_navigation 校验（可选区块）
        ret_nav = config.get("return_navigation")
        if ret_nav is not None:
            if not isinstance(ret_nav.get("steps"), list):
                errors.append("return_navigation.steps 必须是列表")

        return errors


# 全局单例
yaml_task_loader = YamlTaskLoader()

__all__ = ["YamlTaskLoader", "yaml_task_loader"]
