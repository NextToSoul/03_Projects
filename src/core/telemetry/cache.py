"""
遥测缓存
存储每个遥测包的最新快照，供验证步骤零等待读取。
支持流式监听（用于时序验证的时间点检查）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from ..models import TelemetrySnapshot, TelemetryUpdate


class TelemetryCache:
    """遥测缓存——保存每包最新快照"""

    def __init__(self):
        # package_name → list[TelemetrySnapshot]
        self._snapshots: dict[str, list[TelemetrySnapshot]] = {}
        # package_name → datetime
        self._timestamps: dict[str, datetime] = {}
        # 监听者（用于异步流式读取）
        self._listeners: list[asyncio.Future] = []

    def update_package(self, package_name: str, snapshots: list[TelemetrySnapshot]):
        """更新一个包的最新遥测数据"""
        self._snapshots[package_name] = snapshots
        self._timestamps[package_name] = datetime.now()
        
        # 通知所有监听者
        update = TelemetryUpdate(
            package_name=package_name,
            snapshots=snapshots,
            timestamp=self._timestamps[package_name],
        )
        for future in self._listeners[:]:
            if not future.done():
                future.set_result(update)
        self._listeners.clear()

    def get_latest(self, package_name: str) -> list[TelemetrySnapshot] | None:
        """获取某个包的最新快照"""
        return self._snapshots.get(package_name)

    def get_param_value(self, param_id: str) -> TelemetrySnapshot | None:
        """跨包搜索参数的最新值"""
        for pkg_snapshots in self._snapshots.values():
            for snap in pkg_snapshots:
                if snap.param_id == param_id:
                    return snap
        return None

    def get_package_timestamp(self, package_name: str) -> datetime | None:
        """获取某个包的最后更新时间"""
        return self._timestamps.get(package_name)

    async def stream(self) -> AsyncIterator[TelemetryUpdate]:
        """
        异步迭代器——监听遥测更新流
        用于时序验证的时间点检查和 wait_for_condition
        """
        while True:
            future = asyncio.get_event_loop().create_future()
            self._listeners.append(future)
            try:
                update = await future
                yield update
            except asyncio.CancelledError:
                # 清理
                self._listeners.remove(future)
                return

    def clear(self):
        """清空所有缓存"""
        self._snapshots.clear()
        self._timestamps.clear()
        for future in self._listeners[:]:
            if not future.done():
                future.cancel()
        self._listeners.clear()

    @property
    def cached_packages(self) -> list[str]:
        return list(self._snapshots.keys())
