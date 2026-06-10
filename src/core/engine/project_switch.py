"""
运行时项目切换逻辑
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..models import ProjectContext
from ...config.loader import ProfileLoader

logger = logging.getLogger(__name__)


class ProjectSwitcher:
    """运行时项目切换管理器"""

    def __init__(self, callback: Any = None):
        self._loader = ProfileLoader()
        self._current_project: ProjectContext | None = None
        self._on_switch = callback  # for UI integration

    async def switch_to(self, project_path: str | Path) -> ProjectContext:
        """切换到指定项目"""
        if self._current_project and self._current_project.transport:
            await self._current_project.transport.disconnect()
        
        ctx = await self._loader.load(project_path)
        self._current_project = ctx
        
        logger.info(f"Switched to project: {ctx.name}")
        if self._on_switch:
            self._on_switch(ctx)
        
        return ctx

    @property
    def current(self) -> ProjectContext | None:
        return self._current_project

    async def connect(self):
        """连接当前项目的硬件"""
        if self._current_project and self._current_project.transport:
            cfg = self._current_project.profile.transport_config if self._current_project.profile else {}
            return await self._current_project.transport.connect(cfg)
        return False

    async def disconnect(self):
        if self._current_project and self._current_project.transport:
            await self._current_project.transport.disconnect()
