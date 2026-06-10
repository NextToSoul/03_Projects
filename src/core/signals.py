"""
事件总线——引擎与 UI 的通信契约
基于 QObject Signal/Slot，引擎不直接操作 UI 控件
"""

from __future__ import annotations

try:
    from PySide6.QtCore import QObject, Signal
except ImportError:
    # 用于非 UI 环境（CLI 模式 / 测试）的桩
    class QObject: pass
    def Signal(*args, **kwargs):
        """桩——CLI 模式下不做任何事情"""
        class FakeSignal:
            def connect(self, *a, **kw): pass
            def emit(self, *a, **kw): pass
            def disconnect(self, *a, **kw): pass
        return FakeSignal()


class EngineSignals(QObject):
    """全局事件总线"""
    
    # 连接状态
    connection_changed = Signal(bool, str)           # (is_connected, detail)
    
    # 遥测系统
    telemetry_updated = Signal(str, object)          # (package_name, list[TelemetrySnapshot])
    polling_mode_changed = Signal(str, str)          # (package_name, new_mode_str)
    telemetry_alarm = Signal(str, str, float, float)  # (param_id, name, current, threshold)
    
    # 报文
    raw_frame_sent = Signal(str, str)                # (timestamp, hex_string)
    raw_frame_received = Signal(str, str, bool)      # (timestamp, hex_string, checksum_ok)
    
    # 测试执行
    suite_started = Signal(str)                      # suite_name
    case_started = Signal(str, int, int)              # (case_name, index, total)
    step_status = Signal(str, str, str, str)          # (case_name, step_id, step_name, status)
    case_completed = Signal(str, float, str)          # (case_name, duration, result)
    suite_completed = Signal(str, int, int, int)      # (suite_name, pass, fail, skip)
    
    # 安全
    safety_alert = Signal(str, str)                  # (level, message)
    command_blocked = Signal(str, str)                # (command_name, reason)
    
    # 系统
    project_changed = Signal(str)                     # new_project_name
    error_occurred = Signal(str, str)                 # (source, message)
    progress_update = Signal(str, float)              # (message, percentage 0~100)
