"""
遥测注册表与指令注册表
运行时内存数据库，管理所有遥测包定义和指令定义。
支持动态增删（通过 UI 操作导出为 YAML 补丁）。
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import (
    TelemetryPackageDef, TelemetryParam,
    CommandDef, InjectionDef,
)

logger = logging.getLogger(__name__)


class TelemetryRegistry:
    """运行时遥测注册表——管理所有遥测包定义"""

    def __init__(self):
        self._packages: dict[str, TelemetryPackageDef] = {}
        # 索引：param_id → TelemetryParam（跨包搜索加速）
        self._param_index: dict[str, TelemetryParam] = {}
        self._param_to_package: dict[str, str] = {}  # param_id → package_name

    def add_package(self, pkg: TelemetryPackageDef):
        """添加一个遥测包"""
        self._packages[pkg.name] = pkg
        for param in pkg.parameters:
            self._param_index[param.id] = param
            self._param_to_package[param.id] = pkg.name
        logger.info(f"Telemetry package added: {pkg.name} ({len(pkg.parameters)} params)")

    def remove_package(self, name: str):
        """移除一个遥测包"""
        pkg = self._packages.pop(name, None)
        if pkg:
            for param in pkg.parameters:
                self._param_index.pop(param.id, None)
                self._param_to_package.pop(param.id, None)
            logger.info(f"Telemetry package removed: {name}")

    def get_package(self, name: str) -> TelemetryPackageDef | None:
        """获取遥测包"""
        return self._packages.get(name)

    def get_param(self, param_id: str) -> TelemetryParam | None:
        """跨包搜索参数"""
        return self._param_index.get(param_id)

    def get_package_for_param(self, param_id: str) -> str | None:
        """返回参数所属的包名"""
        return self._param_to_package.get(param_id)

    def list_packages(self) -> list[TelemetryPackageDef]:
        """列出所有遥测包"""
        return list(self._packages.values())

    def list_package_names(self) -> list[str]:
        return list(self._packages.keys())

    def get_all_params(self) -> list[TelemetryParam]:
        """获取所有参数（跨包扁平化）"""
        return list(self._param_index.values())

    def clear(self):
        """清空所有注册信息"""
        self._packages.clear()
        self._param_index.clear()
        self._param_to_package.clear()

    @property
    def total_params(self) -> int:
        return len(self._param_index)

    @property
    def total_packages(self) -> int:
        return len(self._packages)


class CommandRegistry:
    """运行时指令注册表——管理所有指令定义"""

    def __init__(self):
        self._commands: dict[str, CommandDef] = {}       # id → CommandDef
        self._injections: list[InjectionDef] = []

    def add_command(self, cmd: CommandDef):
        """添加一条指令"""
        self._commands[cmd.id] = cmd

    def add_commands(self, cmds: list[CommandDef]):
        for cmd in cmds:
            self._commands[cmd.id] = cmd
        logger.info(f"Loaded {len(cmds)} commands")

    def get_command(self, cmd_id: str) -> CommandDef | None:
        """通过指令代号获取指令定义"""
        return self._commands.get(cmd_id)

    def list_commands(self) -> list[CommandDef]:
        """列出所有指令"""
        return list(self._commands.values())

    def list_polling_commands(self) -> list[CommandDef]:
        """列出所有轮询指令"""
        return [cmd for cmd in self._commands.values() if cmd.is_polling]

    def add_injection(self, inj: InjectionDef):
        self._injections.append(inj)

    def get_injections(self) -> list[InjectionDef]:
        return self._injections

    def clear(self):
        self._commands.clear()
        self._injections.clear()
