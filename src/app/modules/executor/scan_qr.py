"""
扫码执行器 - 交互式多阶段执行
"""
from __future__ import annotations

import asyncio
import base64
import shutil
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ...core.logger import logger
from ...db.models import Emulator, SystemConfig
from ..cloud.scan_poller import ScanCancelledException
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..emu.async_adapter import AsyncEmulatorAdapter
from ..emu.adb import Adb
from ..vision.qrcode_detect import detect_qrcode


PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"
PUTONG_DIR = "putonglogindata"

# 选区坐标
ZONE_COORDS = {
    1: (216, 388),
    2: (391, 388),
    3: (533, 387),
    4: (685, 391),
}

# 选角色坐标（暂定，后续可调整）
ROLE_COORDS = {
    1: (216, 388),
    2: (391, 388),
    3: (533, 387),
    4: (685, 391),
}


class ScanQRExecutor:
    """扫码执行器 - 不继承 BaseExecutor，独立实现"""

    def __init__(
        self,
        worker_id: int,
        emulator_id: int,
        emulator_row: Emulator,
        system_config: Optional[SystemConfig],
        scan_job_id: int,
        login_id: str,
        cloud_client,
        agent_token: str,
        node_id: str,
        lease_seconds: int = 120,
    ):
        self.worker_id = worker_id
        self.emulator_id = emulator_id
        self.emulator_row = emulator_row
        self.system_config = system_config
        self.scan_job_id = scan_job_id
        self.login_id = login_id
        self.cloud_client = cloud_client
        self.agent_token = agent_token
        self.node_id = node_id
        self.lease_seconds = lease_seconds
        self.adapter: Optional[AsyncEmulatorAdapter] = None
        self.log = logger.bind(module="ScanQRExecutor", scan_id=scan_job_id)

        # 模板图片目录（项目根目录下的 assets/ui/templates）
        self._template_dir = Path("assets/ui/templates")

    async def run_scan(self) -> None:
        """完整的扫码流程"""
        try:
            await self._init_adapter()
            await self._phase_launching()
            await self._phase_qrcode_ready()
            await self._phase_choose_system()
            await self._phase_choose_zone()
            await self._phase_entering()
            await self._phase_pulling_data()
            await self._phase_done()
        finally:
            await self._cleanup()

    async def _init_adapter(self) -> None:
        """初始化模拟器 adapter"""
        syscfg = self.system_config
        cfg = AdapterConfig(
            adb_path=(syscfg.adb_path if syscfg and syscfg.adb_path else "") or "",
            adb_addr=self.emulator_row.adb_addr,
            pkg_name=PKG_NAME,
            ipc_dll_path=(syscfg.ipc_dll_path if syscfg else "") or "",
            mumu_manager_path=(syscfg.mumu_manager_path if syscfg else "") or "",
            nemu_folder=(syscfg.nemu_folder if syscfg else "") or "",
            instance_id=getattr(self.emulator_row, "instance_id", None),
            activity_name=(syscfg.activity_name if syscfg else None) or ".MainActivity",
        )
        raw_adapter = EmulatorAdapter(cfg)
        self.adapter = AsyncEmulatorAdapter(raw_adapter)
        self.log.info("Adapter 初始化完成")

    async def _update_phase(self, phase: str, screenshot_key: str = None, screenshot_b64: str = None) -> None:
        """上报阶段变更到 oasbackend"""
        await self.cloud_client.scan_update_phase(
            agent_token=self.agent_token,
            node_id=self.node_id,
            scan_id=self.scan_job_id,
            phase=phase,
            screenshot=screenshot_b64,
            screenshot_key=screenshot_key,
        )
        self.log.info(f"Phase 更新: {phase}")

    async def _heartbeat(self) -> None:
        """续约心跳"""
        await self.cloud_client.scan_heartbeat(
            agent_token=self.agent_token,
            node_id=self.node_id,
            scan_id=self.scan_job_id,
            lease_seconds=self.lease_seconds,
        )

    async def _wait_user_choice(self, choice_type: str, timeout: float = 300) -> str:
        """轮询等待用户选择"""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            await self._heartbeat()

            resp = await self.cloud_client.scan_get_choice(
                agent_token=self.agent_token,
                scan_id=self.scan_job_id,
                node_id=self.node_id,
            )

            if resp.get("cancelled"):
                raise ScanCancelledException("用户取消了扫码")
            if not resp.get("user_online", True):
                raise ScanCancelledException("用户已离开扫码页面")

            if resp.get("has_choice") and resp.get("choice_type") == choice_type:
                return str(resp["value"])

            await asyncio.sleep(2)

        raise asyncio.TimeoutError(f"等待用户选择 {choice_type} 超时")

    async def _capture_ndarray(self) -> np.ndarray:
        """截图返回 BGR ndarray"""
        capture_method = "adb"
        if self.system_config and hasattr(self.system_config, "capture_method"):
            capture_method = self.system_config.capture_method or "adb"
        return await self.adapter.capture_ndarray(capture_method)

    async def _capture_base64(self) -> str:
        """截图并编码为 base64"""
        img = await self._capture_ndarray()
        if img is None:
            return ""
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    async def _tap(self, x: int, y: int) -> None:
        """点击屏幕"""
        await self.adapter.tap(x, y)

    async def _match_template(self, template_name: str, image: np.ndarray = None) -> Optional[tuple]:
        """匹配模板图片，返回中心坐标 (x, y) 或 None"""
        if image is None:
            image = await self._capture_ndarray()
        if image is None:
            return None

        template_path = self._template_dir / template_name
        if not template_path.exists():
            self.log.warning(f"模板图片不存在: {template_path}")
            return None

        template = cv2.imread(str(template_path))
        if template is None:
            return None

        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= 0.8:  # 匹配阈值
            h, w = template.shape[:2]
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            return (cx, cy)
        return None

    async def _wait_for_template(self, template_name: str, timeout: float = 60, interval: float = 2) -> Optional[tuple]:
        """等待模板出现，返回中心坐标"""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            pos = await self._match_template(template_name)
            if pos:
                return pos
            await asyncio.sleep(interval)
        return None

    async def _click_template(self, template_name: str, timeout: float = 30) -> bool:
        """等待模板出现并点击"""
        pos = await self._wait_for_template(template_name, timeout=timeout)
        if pos:
            await self._tap(pos[0], pos[1])
            return True
        return False

    # === 各阶段实现 ===

    async def _phase_launching(self) -> None:
        """Phase 1: 删除登录数据 -> 启动游戏 -> 点击accept -> 点击saoma"""
        await self._update_phase("launching")

        # 1. 删除登录数据
        self.log.info("删除模拟器登录数据...")
        try:
            await self.adapter.adb_root()
            shared_prefs_path = f"/data/user/0/{PKG_NAME}/shared_prefs"
            await self.adapter.adb_shell(f"rm -rf {shared_prefs_path}", timeout=30.0)
            self.log.info("登录数据已删除")
        except Exception as e:
            self.log.warning(f"删除登录数据失败: {e}")

        # 2. 启动游戏
        self.log.info("启动游戏...")
        await self.adapter.start_app()
        await asyncio.sleep(5)  # 等待游戏加载

        # 3. 检测 accept.png 并点击（用户协议）
        self.log.info("检测 accept 按钮...")
        for _ in range(30):  # 最多等60秒
            await self._heartbeat()
            pos = await self._match_template("accept.png")
            if pos:
                await self._tap(pos[0], pos[1])
                self.log.info("已点击 accept")
                await asyncio.sleep(2)
                break
            # 检查是否已经跳过了 accept
            saoma_pos = await self._match_template("saoma.png")
            if saoma_pos:
                break
            await asyncio.sleep(2)

        # 4. 等待 saoma.png 出现并点击
        self.log.info("等待 saoma 按钮...")
        if not await self._click_template("saoma.png", timeout=120):
            raise Exception("等待扫码按钮超时")
        self.log.info("已点击 saoma")
        await asyncio.sleep(2)

    async def _phase_qrcode_ready(self) -> None:
        """Phase 2: 检测二维码出现 -> 上传截图 -> 等待扫码（二维码消失）"""
        # 等待二维码出现
        self.log.info("等待二维码出现...")
        qr_found = False
        for _ in range(60):  # 最多等120秒
            await self._heartbeat()
            img = await self._capture_ndarray()
            if img is not None and detect_qrcode(img):
                qr_found = True
                break
            await asyncio.sleep(2)

        if not qr_found:
            raise Exception("等待二维码出现超时")

        # 截图上传
        screenshot_b64 = await self._capture_base64()
        await self._update_phase("qrcode_ready", screenshot_key="qrcode", screenshot_b64=screenshot_b64)
        self.log.info("二维码已就绪，等待用户扫码...")

        # 等待二维码消失（用户扫码后）
        for _ in range(150):  # 最多等300秒（5分钟）
            await self._heartbeat()
            img = await self._capture_ndarray()
            if img is not None and not detect_qrcode(img):
                self.log.info("二维码已消失，用户已扫码")
                await asyncio.sleep(2)  # 等待画面稳定
                return
            await asyncio.sleep(2)

        raise asyncio.TimeoutError("等待用户扫码超时（5分钟）")

    async def _phase_choose_system(self) -> None:
        """Phase 3: 用户选择系统 -> 点击对应按钮 -> 等待 tag_xuanqu"""
        await self._update_phase("choose_system")
        choice = await self._wait_user_choice("system")
        self.log.info(f"用户选择系统: {choice}")

        # 根据选择点击
        if choice == "ios":
            await self._click_template("ios.png", timeout=30)
        else:
            await self._click_template("anzhuo.png", timeout=30)
        await asyncio.sleep(1)

        # 点击 (473, 397) 直到出现 tag_xuanqu.png
        self.log.info("等待选区界面...")
        for _ in range(30):
            await self._heartbeat()
            pos = await self._match_template("tag_xuanqu.png")
            if pos:
                self.log.info("进入选区界面")
                return
            await self._tap(473, 397)
            await asyncio.sleep(2)

        raise Exception("等待选区界面超时")

    async def _phase_choose_zone(self) -> None:
        """Phase 4: 点击229,443 -> 截图上传 -> 用户选区 -> 点击对应坐标"""
        await self._tap(229, 443)
        await asyncio.sleep(2)

        # 截图上传
        screenshot_b64 = await self._capture_base64()
        await self._update_phase("choose_zone", screenshot_key="xuanqu", screenshot_b64=screenshot_b64)

        # 等待用户选择
        choice = await self._wait_user_choice("zone")
        zone_num = int(choice)
        self.log.info(f"用户选择第 {zone_num} 区")

        # 点击对应坐标
        coords = ZONE_COORDS.get(zone_num)
        if coords:
            await self._tap(coords[0], coords[1])
            await asyncio.sleep(2)

    async def _phase_entering(self) -> None:
        """Phase 5: 检测enter -> 点击 -> 检测tag_dark -> 可能需要选角色"""
        await self._update_phase("entering")

        # 等待 enter.png
        self.log.info("等待进入按钮...")
        if not await self._click_template("enter.png", timeout=60):
            # 可能已经自动进入了
            self.log.warning("未检测到 enter.png，继续")

        await self._tap(467, 446)
        await asyncio.sleep(3)

        # 检测 tag_dy.png（需要选角色?）
        tag_dark_pos = await self._match_template("tag_dy.png")
        if tag_dark_pos:
            self.log.info("检测到需要选择角色")
            await self._phase_choose_role()
        else:
            self.log.info("无需选角色，直接进入游戏")

        # 等待进入庭院
        await self._wait_for_tingyuan()

    async def _phase_choose_role(self) -> None:
        """Phase 5.5: 截图上传 -> 用户选角色 -> 点击 -> 处理 tag_dark 区域"""
        screenshot_b64 = await self._capture_base64()
        await self._update_phase("choose_role", screenshot_key="role", screenshot_b64=screenshot_b64)

        choice = await self._wait_user_choice("role")
        role_num = int(choice)
        self.log.info(f"用户选择角色: {role_num}")

        coords = ROLE_COORDS.get(role_num)
        if coords:
            await self._tap(coords[0], coords[1])
            await asyncio.sleep(2)

        # 参考正常启动游戏流程的 tag_dy.png 区域点击操作
        # 点击中心区域多次确保进入
        for _ in range(5):
            await self._heartbeat()
            await self._tap(480, 270)  # 屏幕中心附近
            await asyncio.sleep(2)
            # 检查是否还在 tag_dark
            if not await self._match_template("tag_dy.png"):
                break

    async def _wait_for_tingyuan(self) -> None:
        """等待进入庭院界面"""
        self.log.info("等待进入庭院...")
        # 多次点击和等待，处理可能的弹窗
        for i in range(60):  # 最多等120秒
            await self._heartbeat()

            # 检测 accept.png（可能有新弹窗）
            accept_pos = await self._match_template("accept.png")
            if accept_pos:
                await self._tap(accept_pos[0], accept_pos[1])
                await asyncio.sleep(2)
                continue

            # 检测 tag_dy.png（可能还需要点击）
            dark_pos = await self._match_template("tag_dy.png")
            if dark_pos:
                await self._tap(480, 270)
                await asyncio.sleep(2)
                continue

            # 简单检测：截图后检查是否进入了庭院
            # 这里可以通过检测庭院特征来判断
            # 暂时用等待时间来判断
            if i > 15:  # 至少等30秒
                self.log.info("假设已进入庭院")
                return

            await asyncio.sleep(2)

        raise Exception("等待进入庭院超时")

    async def _phase_pulling_data(self) -> None:
        """Phase 6: 抓取账号数据"""
        await self._update_phase("pulling_data")
        self.log.info(f"开始抓取账号数据: login_id={self.login_id}")

        save_dir = Path(PUTONG_DIR) / self.login_id
        save_dir.mkdir(parents=True, exist_ok=True)

        adb_addr = self.emulator_row.adb_addr
        adb = Adb(
            (self.system_config.adb_path if self.system_config and self.system_config.adb_path else "") or ""
        )

        try:
            adb.root(adb_addr)

            # 抓取 shared_prefs
            shared_prefs_remote = f"/data/user/0/{PKG_NAME}/shared_prefs"
            shared_prefs_local = save_dir / "shared_prefs"
            if shared_prefs_local.exists():
                shutil.rmtree(shared_prefs_local)

            ok, msg = adb.pull(adb_addr, shared_prefs_remote, str(save_dir), timeout=120.0)
            if ok:
                self.log.info("抓取 shared_prefs 成功")
            else:
                self.log.warning(f"抓取 shared_prefs 失败: {msg}")

            # 抓取 clientconfig
            clientconfig_remote = f"/sdcard/Android/data/{PKG_NAME}/files/netease/onmyoji/Documents/clientconfig"
            ok, msg = adb.pull(adb_addr, clientconfig_remote, str(save_dir), timeout=120.0)
            if ok:
                self.log.info("抓取 clientconfig 成功")
            else:
                self.log.warning(f"抓取 clientconfig 失败: {msg}")

        except Exception as e:
            self.log.error(f"抓取数据失败: {e}")
            raise

    async def _phase_done(self) -> None:
        """Phase 7: 标记完成"""
        await self.cloud_client.scan_complete(
            agent_token=self.agent_token,
            node_id=self.node_id,
            scan_id=self.scan_job_id,
            message=f"扫码完成: login_id={self.login_id}",
        )
        self.log.info(f"扫码任务完成: login_id={self.login_id}")

    async def _cleanup(self) -> None:
        """清理：关闭游戏、删除登录数据"""
        if not self.adapter:
            return

        try:
            await self.adapter.adb_force_stop(PKG_NAME)
            self.log.info("游戏已关闭")
        except Exception as e:
            self.log.warning(f"关闭游戏失败: {e}")

        try:
            await self.adapter.adb_root()
            shared_prefs_path = f"/data/user/0/{PKG_NAME}/shared_prefs"
            await self.adapter.adb_shell(f"rm -rf {shared_prefs_path}", timeout=30.0)
            self.log.info("登录数据已清理")
        except Exception as e:
            self.log.warning(f"清理登录数据失败: {e}")
