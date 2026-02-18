from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Optional, Sequence, Union

from loguru import logger

from ..emu.adapter import EmulatorAdapter
from ..emu.async_adapter import AsyncEmulatorAdapter
from ..vision import DEFAULT_THRESHOLD
from ..vision.template import match_template
from .registry import UIRegistry, registry as _global_registry
from .detector import UIDetector
from .graph import UIGraph, apply_edge
from .default_graph import build_default_graph
from .types import UIDetectResult, UIManagerProtocol

if TYPE_CHECKING:
    from .popup_handler import PopupHandler


ENTER_TAP_X = 487
ENTER_TAP_Y = 447

EXIT_TEMPLATE = "assets/ui/templates/exit.png"
BACK_TEMPLATE = "assets/ui/templates/back.png"
EXIT_DARK_TEMPLATE = "assets/ui/templates/exit_dark.png"
ACCEPT_TEMPLATE = "assets/ui/templates/accept.png"
ACCEPT_1_TEMPLATE = "assets/ui/templates/accept_1.png"
SHIXIAO_TEMPLATES = [
    "assets/ui/templates/shixiao.png",
    "assets/ui/templates/shixiao_1.png",
]
CANGBAOGE_TEMPLATE = "assets/ui/templates/cangbaoge.png"


class AccountExpiredException(Exception):
    """账号登录数据已失效（检测到 shixiao 界面）"""
    pass


class CangbaogeListedException(Exception):
    """账号已上架藏宝阁"""
    pass


class UIManager(UIManagerProtocol):
    def __init__(
        self,
        adapter: Union[EmulatorAdapter, AsyncEmulatorAdapter],
        *,
        capture_method: str = "adb",
        registry: Optional[UIRegistry] = None,
        graph: Optional[UIGraph] = None,
        default_threshold: float = DEFAULT_THRESHOLD,
        popup_handler: Optional["PopupHandler"] = None,
    ) -> None:
        self.adapter = adapter
        self.capture_method = capture_method
        self.registry = registry or _global_registry
        self.graph = graph or build_default_graph()
        self.detector = UIDetector(self.registry, default_threshold=default_threshold)
        self._popup_handler = popup_handler
        self._last_ui: str | None = None  # 上下文感知：记住上一次检测到的 UI

    @property
    def _is_async(self) -> bool:
        return isinstance(self.adapter, AsyncEmulatorAdapter)

    # ── 异步适配辅助方法（兼容同步/异步 adapter）──

    async def _capture(self):
        """截图并直接返回 BGR ndarray。"""
        if self._is_async:
            return await self.adapter.capture_ndarray(self.capture_method)
        return self.adapter.capture_ndarray(self.capture_method)

    async def _tap(self, x: int, y: int) -> None:
        if self._is_async:
            await self.adapter.tap(x, y)
        else:
            self.adapter.tap(x, y)

    async def _start_app(self, mode: str = "adb_monkey") -> None:
        if self._is_async:
            await self.adapter.start_app(mode=mode)
        else:
            self.adapter.start_app(mode)

    async def _stop_app(self) -> None:
        if self._is_async:
            await self.adapter.stop_app()
        else:
            self.adapter.stop_app()

    async def _is_app_running(self) -> bool:
        addr = self.adapter.cfg.adb_addr
        pkg = self.adapter.cfg.pkg_name
        if self._is_async:
            from ...core.thread_pool import run_in_io
            return await run_in_io(self.adapter.adb.is_app_running, addr, pkg)
        return self.adapter.adb.is_app_running(addr, pkg)

    async def _adb_tap(self, x: int, y: int) -> None:
        """通过 adb 直接 tap（绕过 adapter.tap 的场景）。"""
        addr = self.adapter.cfg.adb_addr
        if self._is_async:
            from ...core.thread_pool import run_in_io
            await run_in_io(self.adapter.adb.tap, addr, x, y)
        else:
            self.adapter.adb.tap(addr, x, y)

    @property
    def popup_handler(self) -> "PopupHandler":
        """获取弹窗处理器，懒初始化"""
        if self._popup_handler is None:
            from .popup_handler import PopupHandler
            self._popup_handler = PopupHandler(
                self.adapter,
                capture_method=self.capture_method,
            )
        return self._popup_handler

    # ── 上下文感知 ──

    def _build_hints(self, target: str | None = None) -> list[str]:
        """基于上下文构建优先检测列表。"""
        hints: list[str] = []
        if self._last_ui:
            hints.append(self._last_ui)
            # 添加相邻 UI（通过 graph 可达的目的地）
            for edge in self.graph.edges_from(self._last_ui):
                if edge.dst not in hints:
                    hints.append(edge.dst)
        if target and target not in hints:
            hints.insert(1 if hints else 0, target)
        return hints

    async def detect_ui(
        self,
        image: bytes | None = None,
        *,
        hints: Sequence[str] | None = None,
        anchors: bool = True,
    ) -> UIDetectResult:
        if image is None:
            image = await self._capture()
        # 使用传入的 hints 或自动构建
        effective_hints = hints if hints is not None else self._build_hints()
        result = await self.detector.async_detect(
            image, hints=effective_hints, anchors=anchors,
        )
        # 更新上下文
        if result.ui != "UNKNOWN":
            self._last_ui = result.ui
        return result

    async def _try_click_exit_or_back(self, image: bytes) -> bool:
        """尝试在截图中匹配 exit/back 按钮并点击。

        用于 ENTER→庭院 过渡期间，处理可能出现的中间界面。

        Returns:
            True 表示找到并点击了按钮，False 表示未找到。
        """
        for label, tpl_path in [("exit", EXIT_TEMPLATE), ("back", BACK_TEMPLATE)]:
            m = match_template(image, tpl_path)
            if m is not None:
                cx, cy = m.random_point()
                logger.info("_try_click_exit_or_back: 检测到 {} 按钮 score={:.3f}，点击 ({}, {})", label, m.score, cx, cy)
                await self._tap(cx, cy)
                return True
        # 检查 exit_dark（ENTER→庭院过渡期间可能出现的中间界面）
        m = match_template(image, EXIT_DARK_TEMPLATE)
        if m is not None:
            cx = random.randint(424, 533)
            cy = random.randint(439, 461)
            logger.info("_try_click_exit_or_back: 检测到 exit_dark score={:.3f}，点击 ({}, {})", m.score, cx, cy)
            await self._tap(cx, cy)
            return True
        return False

    def _check_shixiao_on_enter(self, image: bytes) -> None:
        """当 UIDetector 报告 ENTER 时，额外检查截图是否实际为失效界面。

        若检测到 shixiao 模板匹配，抛出 AccountExpiredException。
        """
        for tpl_path in SHIXIAO_TEMPLATES:
            try:
                m = match_template(image, tpl_path)
            except Exception:
                continue
            if m is not None:
                logger.warning(
                    "_check_shixiao_on_enter: 在 ENTER 界面检测到 shixiao 模板 {} score={:.3f}",
                    tpl_path, m.score,
                )
                raise AccountExpiredException("检测到账号失效界面（ENTER 界面二次校验）")

    def _check_cangbaoge(self, image: bytes) -> None:
        """检查截图是否为藏宝阁界面，若匹配则抛出 CangbaogeListedException。"""
        try:
            m = match_template(image, CANGBAOGE_TEMPLATE)
        except Exception:
            return
        if m is not None:
            logger.warning(
                "_check_cangbaoge: 检测到藏宝阁界面 score={:.3f}", m.score,
            )
            raise CangbaogeListedException("检测到账号已上架藏宝阁")

    def warmup(self) -> None:
        """预加载所有模板到缓存。"""
        self.detector.warmup()

    async def ensure_ui(
        self,
        target: str,
        *,
        max_steps: int = 8,
        step_timeout: float = 2.0,
        threshold: float | None = None,
    ) -> bool:
        # quick check（截图复用 + hints）
        image = await self._capture()
        dismissed = await self.popup_handler.check_and_dismiss(image=image)
        if dismissed > 0:
            cur = await self.detect_ui(hints=[target])
        else:
            cur = await self.detect_ui(image=image, hints=[target])
        if cur.ui == target:
            return True

        steps = 0
        while steps < max_steps:
            steps += 1

            # 截图复用：一次截图同时用于弹窗检查和 UI 检测
            image = await self._capture()

            # 弹窗检查（复用截图）
            dismissed = await self.popup_handler.check_and_dismiss(image=image)
            if dismissed > 0:
                # 弹窗关闭后画面变了，需要重新截图检测
                cur = await self.detect_ui(hints=[target])
                if cur.ui == target:
                    return True
                continue

            # 无弹窗，复用同一张截图做 UI 检测
            cur = await self.detect_ui(image=image, hints=[target])
            if cur.ui == target:
                return True

            # plan path
            if cur.ui == "UNKNOWN":
                await asyncio.sleep(0.5)
                cur = await self.detect_ui(hints=[target])
                if cur.ui == target:
                    return True
                continue

            path = self.graph.find_path(cur.ui, target, max_steps=max_steps)
            if not path:
                # Cannot plan a path
                await asyncio.sleep(0.5)
                cur = await self.detect_ui(hints=[target])
                if cur.ui == target:
                    return True
                continue

            # execute one edge then poll for UI change
            old_ui = cur.ui
            await apply_edge(self.adapter, path[0], cur, detect_fn=self.detect_ui)

            # 导航轮询优化：无锚点快速检测 + 只关注 target 和 old_ui
            poll_interval = 0.3
            waited = 0.0
            poll_hints = [target, old_ui]
            while waited < step_timeout:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                cur = await self.detect_ui(hints=poll_hints, anchors=False)
                if cur.ui != old_ui:
                    break

            # UI 变化后需要锚点时，做一次完整检测
            if cur.ui != "UNKNOWN" and cur.ui != old_ui:
                cur = await self.detect_ui(hints=[cur.ui, target])

            if cur.ui == target:
                return True
        return False

    async def launch_game(
        self,
        mode: str = "adb_monkey",
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> bool:
        """启动游戏并等待进入庭院界面。

        流程：启动 app → 轮询检测 → 遇到 ENTER 界面则点击进入按钮 → 检测到 TINGYUAN 返回 True。

        Args:
            mode: 启动方式，透传给 adapter.start_app()
            timeout: 最大等待秒数
            poll_interval: 每次轮询间隔秒数

        Returns:
            True 表示成功进入庭院，False 表示超时未进入。
        """
        logger.info("launch_game: 启动游戏 (mode={})", mode)
        await self._start_app(mode)

        launch_hints = ["TINGYUAN", "ENTER", "SHIXIAO"]

        elapsed = 0.0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # 截图复用：一次截图同时用于弹窗检查和 UI 检测
            image = await self._capture()

            # 藏宝阁检测（ENTER→庭院过渡中最先检查）
            self._check_cangbaoge(image)

            # 弹窗检查（复用截图）
            dismissed = await self.popup_handler.check_and_dismiss(image=image)
            if dismissed > 0:
                continue

            # 启动阶段检测 accept 弹窗（用户协议等），出现则点击
            accept_match = match_template(image, ACCEPT_TEMPLATE)
            if accept_match is not None:
                cx, cy = accept_match.random_point()
                logger.info(
                    "launch_game: 检测到 accept 弹窗 score={:.3f}，点击 ({}, {})",
                    accept_match.score, cx, cy,
                )
                await self._tap(cx, cy)
                continue

            # 启动阶段检测 accept_1 弹窗，出现则点击自身关闭
            accept_1_match = match_template(image, ACCEPT_1_TEMPLATE)
            if accept_1_match is not None:
                cx, cy = accept_1_match.random_point()
                logger.info(
                    "launch_game: 检测到 accept_1 弹窗 score={:.3f}，点击 ({}, {})",
                    accept_1_match.score, cx, cy,
                )
                await self._tap(cx, cy)
                continue

            # UI 检测（复用截图 + hints 优先）
            result = await self.detector.async_detect(image, hints=launch_hints)
            logger.debug("launch_game: 检测结果 ui={} score={:.3f} elapsed={:.1f}s", result.ui, result.score, elapsed)

            # 更新上下文
            if result.ui != "UNKNOWN":
                self._last_ui = result.ui

            if result.ui == "TINGYUAN":
                logger.info("launch_game: 已到达庭院界面")
                return True

            if result.ui == "ENTER":
                self._check_shixiao_on_enter(image)
                logger.info("launch_game: 检测到 ENTER 界面，点击固定坐标 ({}, {})", ENTER_TAP_X, ENTER_TAP_Y)
                await self._tap(ENTER_TAP_X, ENTER_TAP_Y)

            if result.ui == "SHIXIAO":
                logger.warning("launch_game: 检测到账号失效界面(shixiao)")
                raise AccountExpiredException("检测到账号失效界面")

            # UNKNOWN 状态：尝试点击 exit/back 按钮（处理 ENTER→庭院 过渡中间界面）
            if result.ui not in ("ENTER", "TINGYUAN", "SHIXIAO"):
                await self._try_click_exit_or_back(image)

        logger.warning("launch_game: 超时 ({:.0f}s) 未进入庭院", timeout)
        return False

    async def go_to_tingyuan(
        self,
        *,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> bool:
        """在不重启游戏的前提下，尝试从当前 UI 导航到庭院。"""
        tingyuan_hints = ["TINGYUAN", "ENTER", "SHIXIAO"]

        elapsed = 0.0
        while elapsed < timeout:
            # 截图复用
            image = await self._capture()

            # 藏宝阁检测（ENTER→庭院过渡中最先检查）
            self._check_cangbaoge(image)

            # 弹窗检查（复用截图）
            dismissed = await self.popup_handler.check_and_dismiss(image=image)
            if dismissed > 0:
                continue

            # UI 检测（复用截图 + hints 优先）
            result = await self.detector.async_detect(image, hints=tingyuan_hints)
            logger.debug("go_to_tingyuan: ui={} score={:.3f} elapsed={:.1f}s", result.ui, result.score, elapsed)

            # 更新上下文
            if result.ui != "UNKNOWN":
                self._last_ui = result.ui

            if result.ui == "TINGYUAN":
                logger.info("go_to_tingyuan: 已到达庭院界面")
                return True

            if result.ui == "ENTER":
                self._check_shixiao_on_enter(image)
                logger.info("go_to_tingyuan: 检测到 ENTER，点击固定坐标 ({}, {})", ENTER_TAP_X, ENTER_TAP_Y)
                await self._tap(ENTER_TAP_X, ENTER_TAP_Y)

            elif result.ui != "UNKNOWN":
                # 识别到已注册 UI，则尝试走 UI 图跳转
                ok = await self.ensure_ui("TINGYUAN", max_steps=4, step_timeout=1.5)
                if ok:
                    logger.info("go_to_tingyuan: 通过 UI 跳转到庭院成功")
                    return True

            else:
                # UNKNOWN 状态：尝试点击 exit/back 按钮（处理 ENTER→庭院 过渡中间界面）
                await self._try_click_exit_or_back(image)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning("go_to_tingyuan: 超时 ({:.0f}s) 未进入庭院", timeout)
        return False

    async def ensure_game_ready(
        self,
        *,
        mode: str = "adb_monkey",
        timeout: float = 60.0,
        poll_interval: float = 2.0,
    ) -> bool:
        """确保游戏处于可执行状态（已启动且在庭院）。

        规则：
        1) 若游戏未启动：直接启动并等待进入庭院。
        2) 若游戏已启动：先检测当前 UI。
           - 在可识别 UI 上：优先通过 UI 导航进入庭院。
           - 在未知 UI 上：重启游戏后再等待进入庭院。
        """
        running = False
        try:
            running = await self._is_app_running()
        except Exception as e:
            logger.warning("ensure_game_ready: 检查进程失败，按未启动处理: {}", e)

        if not running:
            logger.info("ensure_game_ready: 游戏未启动，执行启动流程")
            return await self.launch_game(mode=mode, timeout=timeout, poll_interval=poll_interval)

        logger.info("ensure_game_ready: 游戏已启动，检测当前 UI")
        try:
            cur = await self.detect_ui()
            logger.info("ensure_game_ready: 当前 UI={} score={:.3f}", cur.ui, cur.score)

            if cur.ui == "SHIXIAO":
                logger.warning("ensure_game_ready: 检测到账号失效界面(shixiao)")
                raise AccountExpiredException("检测到账号失效界面")

            if cur.ui == "ENTER":
                # ENTER 界面不在导航图中，必须完成进入流程到达庭院
                ok = await self.go_to_tingyuan(timeout=min(timeout, 45.0), poll_interval=poll_interval)
                if ok:
                    return True

            elif cur.ui != "UNKNOWN":
                # 游戏已启动且在可识别界面（庭院、商店、寮等），
                # 直接返回 True，由后续 ensure_ui(target) 负责导航到目标界面。
                # 这样批次内连续任务可以从上一个任务的结束界面直接导航，避免冗余回庭院。
                logger.info("ensure_game_ready: 游戏已就绪，当前 UI={}", cur.ui)
                return True
        except (AccountExpiredException, CangbaogeListedException):
            raise
        except Exception as e:
            logger.warning("ensure_game_ready: UI 检测/跳转失败，准备重启: {}", e)

        logger.info("ensure_game_ready: 当前状态异常，执行重启流程")
        try:
            await self._stop_app()
        except Exception as e:
            logger.warning("ensure_game_ready: 停止游戏失败，继续尝试启动: {}", e)

        return await self.launch_game(mode=mode, timeout=timeout, poll_interval=poll_interval)

    def navigate(self, source: str, target: str) -> bool:
        path = self.graph.find_path(source, target)
        return bool(path)

    async def read_asset(
        self,
        asset_type: "AssetType",
        *,
        retries: int = 2,
    ) -> Optional[int]:
        """读取指定游戏资产的当前值（通过 OCR）。

        流程：导航到资产所在界面 → 截图 → OCR 识别 ROI 区域 → 解析整数。

        Args:
            asset_type: 资产类型（来自 ui.assets.AssetType）
            retries: OCR 解析失败时重试次数

        Returns:
            解析出的整数值，失败返回 None
        """
        from .assets import get_asset_def
        from ..ocr.recognize import ocr as ocr_recognize
        from ..ocr.recognize import ocr_digits

        asset_def = get_asset_def(asset_type)
        if asset_def is None:
            logger.warning("read_asset: 未注册的资产类型 {}", asset_type)
            return None

        # 导航到目标界面
        cur = await self.detect_ui()
        if cur.ui != asset_def.screen:
            ok = await self.ensure_ui(asset_def.screen, max_steps=6, step_timeout=2.0)
            if not ok:
                logger.warning("read_asset: 导航到 {} 失败", asset_def.screen)
                return None

        # 等待指定模板出现，确认界面完全加载
        if asset_def.wait_template:
            already_visible = False
            if asset_def.pre_tap:
                # 先检查 wait_template 是否已匹配（侧边栏是否已展开），
                # 避免 toggle 关闭已展开的侧边栏
                screenshot = await self._capture()
                if screenshot is not None:
                    templates = (
                        [asset_def.wait_template]
                        if isinstance(asset_def.wait_template, str)
                        else asset_def.wait_template
                    )
                    for tpl in templates:
                        if match_template(screenshot, tpl) is not None:
                            already_visible = True
                            logger.debug("read_asset: 模板 {} 已可见，跳过展开点击", tpl)
                            break

                if not already_visible:
                    tx, ty = asset_def.pre_tap
                    await self._adb_tap(tx, ty)
                    logger.debug("read_asset: 点击 ({}, {}) 展开菜单", tx, ty)
                    await asyncio.sleep(1.0)

            if not already_visible:
                from ..executor.helpers import wait_for_template
                m = await wait_for_template(
                    self.adapter,
                    self.capture_method,
                    asset_def.wait_template,
                    timeout=8.0,
                    interval=1.0,
                    label=asset_def.label,
                )
                if not m:
                    logger.warning("read_asset: 等待 {} 模板超时", asset_def.wait_template)
                    return None

        # OCR 识别（带重试）
        for attempt in range(retries + 1):
            await asyncio.sleep(0.5)
            image = await self._capture()
            if image is None:
                logger.warning("read_asset: 截图失败 (attempt={})", attempt + 1)
                continue

            recognize_fn = ocr_digits if asset_def.digit_only else ocr_recognize
            result = recognize_fn(image, roi=asset_def.roi)
            raw_text = result.text.strip()
            logger.debug(
                "read_asset: {} OCR 原始文本='{}' (attempt={})",
                asset_def.label, raw_text, attempt + 1,
            )

            value = asset_def.parser(raw_text)
            if value is not None:
                logger.info("read_asset: {}={}", asset_def.label, value)
                return value

        logger.warning("read_asset: {} OCR 解析失败", asset_def.label)
        return None


__all__ = ["UIManager"]
