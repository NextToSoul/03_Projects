"""
轮询管理器
每个遥测包独立运行一个状态机，支持四态模式：
  DISABLED → SINGLE → DISABLED
  DISABLED → ACTIVE → PAUSED → ACTIVE
  ACTIVE → DISABLED
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..definitions import PollMode
from ..models import (
    TelemetryPackageDef, TelemetrySnapshot,
    TelemetryUpdate, CommandDef,
)
from .cache import TelemetryCache
from .registry import TelemetryRegistry, CommandRegistry
from ..hardware.packet import BitFieldParser
from ..hardware.transport import Transport
from ..hardware.protocol import ProtocolCodec
from ..hardware.sequencer import SequenceManager

logger = logging.getLogger(__name__)


class PackagePoller:
    """单个遥测包的轮询器（独立状态机）"""

    def __init__(
        self,
        pkg_def: TelemetryPackageDef,
        transport: Transport,
        protocol: ProtocolCodec,
        cmd_def: CommandDef | None,
        seq_mgr: SequenceManager,
        cache: TelemetryCache,
    ):
        self.pkg = pkg_def
        self._transport = transport
        self._protocol = protocol
        self._cmd = cmd_def
        self._seq = seq_mgr
        self._cache = cache
        self._parser = BitFieldParser()
        
        self.mode: PollMode = PollMode.DISABLED
        self._task: asyncio.Task | None = None
        self.consecutive_failures: int = 0

    async def run_loop(self):
        """持续轮询循环"""
        while self.mode == PollMode.ACTIVE:
            t_start = time.monotonic()
            try:
                await self._poll_once()
                self.consecutive_failures = 0
            except Exception as e:
                self.consecutive_failures += 1
                logger.warning(f"Poll error for {self.pkg.name}: {e} (x{self.consecutive_failures})")
            
            elapsed = time.monotonic() - t_start
            sleep_time = max(0, self.pkg.poll_interval_s - elapsed)
            await asyncio.sleep(sleep_time)

    async def poll_once(self) -> list[TelemetrySnapshot] | None:
        """单次查询（SINGLE 模式）"""
        return await self._poll_once()

    async def _poll_once(self) -> list[TelemetrySnapshot] | None:
        """执行一次查询→解析→缓存更新"""
        if not self._cmd or not self._transport.is_connected():
            return None
        
        # 1. 发送轮询指令
        seq = self._seq.next()
        frame = self._protocol.encode_command(self._cmd, seq)
        await self._transport.send(frame)
        
        # 2. 接收应答
        response = await self._transport.recv(timeout_s=3.0)
        if response is None:
            return None
        
        # 3. 解析帧头
        frame_info = self._protocol.decode_frame(response)
        if not frame_info.is_valid:
            logger.warning(f"Invalid frame received for {self.pkg.name}")
            return None
        
        # 4. 计算数据域起始位置
        header_size = 6  # CCSDS 基本帧头 6 字节
        data_payload = response[header_size:-2]  # 去掉校验和
        
        # 5. 位域解析
        snapshots = self._parser.parse_packet(data_payload, self.pkg.parameters)
        
        # 6. 更新缓存
        self._cache.update_package(self.pkg.name, snapshots)
        
        return snapshots

    def start_loop(self):
        """启动持续轮询协程"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self.run_loop())

    def stop(self):
        """停止轮询"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None


class PollingManager:
    """轮询管理器——管理所有包的轮询状态"""

    def __init__(
        self,
        transport: Transport,
        protocol: ProtocolCodec,
        seq_mgr: SequenceManager,
        cache: TelemetryCache,
    ):
        self._transport = transport
        self._protocol = protocol
        self._seq = seq_mgr
        self._cache = cache
        self._pollers: dict[str, PackagePoller] = {}
        self._registry: TelemetryRegistry | None = None
        self._cmd_registry: CommandRegistry | None = None
        self._status_callbacks: list = []  # for UI signal integration

    def set_registries(self, registry: TelemetryRegistry, cmd_registry: CommandRegistry):
        """设置遥测和指令注册表"""
        self._registry = registry
        self._cmd_registry = cmd_registry

    def register_package(self, pkg_def: TelemetryPackageDef):
        """注册一个遥测包的轮询器"""
        if self._cmd_registry is None:
            return
        
        cmd = self._cmd_registry.get_command(pkg_def.command_id) if pkg_def.command_id else None
        poller = PackagePoller(
            pkg_def=pkg_def,
            transport=self._transport,
            protocol=self._protocol,
            cmd_def=cmd,
            seq_mgr=self._seq,
            cache=self._cache,
        )
        self._pollers[pkg_def.name] = poller

    def unregister_package(self, name: str):
        """注销一个遥测包"""
        poller = self._pollers.pop(name, None)
        if poller:
            poller.stop()

    def set_mode(self, package_name: str, mode: PollMode):
        """设置某个包的轮询模式"""
        poller = self._pollers.get(package_name)
        if not poller:
            logger.warning(f"Unknown package: {package_name}")
            return
        
        old_mode = poller.mode
        poller.mode = mode
        
        if mode == PollMode.ACTIVE and old_mode != PollMode.ACTIVE:
            poller.start_loop()
        elif mode == PollMode.DISABLED:
            poller.stop()
        elif mode == PollMode.SINGLE:
            asyncio.create_task(poller.poll_once())
            if old_mode == PollMode.ACTIVE:
                poller.stop()  # ACTIVE→SINGLE→DISABLED
            poller.mode = PollMode.DISABLED  # SINGLE 执行完回到 DISABLED
        
        self._notify_status(package_name, mode)

    def get_mode(self, package_name: str) -> PollMode:
        poller = self._pollers.get(package_name)
        if not poller:
            return PollMode.DISABLED
        return poller.mode

    def start_all_default(self):
        """按配置启动默认启用的包"""
        if self._registry is None:
            return
        for pkg in self._registry.list_packages():
            if pkg.default_poll == "enabled":
                self.set_mode(pkg.name, PollMode.ACTIVE)

    def stop_all(self):
        """停止所有轮询"""
        for poller in self._pollers.values():
            poller.stop()
            poller.mode = PollMode.DISABLED

    def pause_all(self):
        """暂停所有轮询"""
        for poller in self._pollers.values():
            if poller.mode == PollMode.ACTIVE:
                poller.mode = PollMode.PAUSED
                poller.stop()

    def resume_all(self):
        """恢复所有暂停的轮询"""
        for poller in self._pollers.values():
            if poller.mode == PollMode.PAUSED:
                poller.mode = PollMode.ACTIVE
                poller.start_loop()

    async def poll_package_once(self, package_name: str) -> list[TelemetrySnapshot] | None:
        """对外接口：按需查询一次遥测包"""
        poller = self._pollers.get(package_name)
        if not poller:
            return None
        return await poller.poll_once()

    def on_status_changed(self, callback):
        """注册状态变更回调（用于 UI 信号转发）"""
        self._status_callbacks.append(callback)

    def _notify_status(self, package: str, mode: PollMode):
        for cb in self._status_callbacks:
            try:
                cb(package, mode.value)
            except Exception as e:
                logger.warning(f"Status callback error: {e}")

    @property
    def active_pollers(self) -> list[str]:
        """当前 ACTIVE 状态的包"""
        return [n for n, p in self._pollers.items() if p.mode == PollMode.ACTIVE]
