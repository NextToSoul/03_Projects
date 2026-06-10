"""
安全保护系统
三层保护：
  1. 指令分类拦截（按类别禁止发送特定指令）
  2. 高危确认（高危指令发送前弹出确认）
  3. 参数范围校验（注入参数超限拦截）
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import SafetyConfig, CommandDef
from ..definitions import SafetyLevel

logger = logging.getLogger(__name__)


class SafetyGuard:
    """安全拦截器"""

    def __init__(self, config: SafetyConfig | None = None):
        self._config = config or SafetyConfig()
        # 缓存：command_id → is_blocked
        self._blocked_cache: dict[str, str] = {}  # command_id → reason
        self._high_risk_cache: dict[str, str] = {}  # command_id → name
        self._build_cache()
    
    def _build_cache(self):
        """从配置构建拦截缓存"""
        self._blocked_cache.clear()
        self._high_risk_cache.clear()
        
        for category in self._config.blocked_categories:
            reason = category.get("reason", "安全策略拦截")
            for cmd_id in category.get("commands", []):
                self._blocked_cache[cmd_id] = reason
        
        for cmd in self._config.high_risk_commands:
            cmd_id = cmd.get("command_id", "")
            if cmd_id:
                self._high_risk_cache[cmd_id] = cmd.get("name", "")
    
    def check_command(self, cmd: CommandDef) -> tuple[bool, str | None]:
        """
        检查指令是否被拦截
        Returns: (is_allowed, block_reason_or_None)
        """
        if not self._config.enabled:
            return True, None
        
        # 1. 分类拦截检查
        reason = self._blocked_cache.get(cmd.id)
        if reason:
            return False, reason
        
        return True, None
    
    def is_high_risk(self, cmd: CommandDef) -> bool:
        """是否高危指令（需要确认）"""
        return cmd.id in self._high_risk_cache
    
    def get_high_risk_name(self, cmd: CommandDef) -> str:
        return self._high_risk_cache.get(cmd.id, cmd.name)
    
    def validate_param(self, value: float, param_name: str = "") -> tuple[bool, str | None]:
        """
        校验参数值范围
        Returns: (is_valid, error_message_or_None)
        """
        if not self._config.validate_param_range:
            return True, None
        
        if abs(value) > self._config.max_injection_value:
            return False, f"参数 '{param_name}' 值 {value} 超出安全范围"
        
        return True, None
    
    def reload(self, config: SafetyConfig):
        """重新加载安全策略"""
        self._config = config
        self._build_cache()
        logger.info("Safety config reloaded")
    
    @property
    def is_enabled(self) -> bool:
        return self._config.enabled
    
    @property
    def config(self) -> SafetyConfig:
        return self._config
    
    @property
    def blocked_commands(self) -> list[str]:
        return list(self._blocked_cache.keys())
    
    @property
    def high_risk_commands(self) -> list[tuple[str, str]]:
        return [(k, v) for k, v in self._high_risk_cache.items()]
