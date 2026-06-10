"""
PPCU TestBench — 数据模型定义
所有 dataclass 集中在此，配置与运行时共用同套模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .definitions import (
    DataType, Endian, FrameType, PollMode,
    StepType, StepStatus, CaseStatus, OnFailAction,
    TransportType, ProtocolType, ChecksumType, SafetyLevel,
)


# ═══════════════════════════════════════════
# 遥测系统模型
# ═══════════════════════════════════════════

@dataclass
class TelemetryParam:
    """单个遥测参数定义（来自 Excel 一行）"""
    id: str                          # "TM1001"
    name: str                        # "遥测请求指令计数"
    data_offset: int = 0             # 数据域内字节偏移
    bit_offset: int = 0              # 位偏移
    bit_length: int = 8              # 位长度
    data_type: str = "uint8"         # uint8/uint16/uint32/float32/enum
    endian: str = "big"              # big/little
    scale: float = 1.0               # 换算系数
    decimal_places: int | None = None
    unit: str = ""
    range_min: float | None = None
    range_max: float | None = None
    enum_values: dict[int, str] | None = None  # {0: "待机模式", ...}


@dataclass
class TelemetryPackageDef:
    """遥测包定义（一张 Excel Sheet = 一个包）"""
    name: str                        # "常规包1"
    command_id: str = ""             # 请求指令代号 "APID_00C0"
    frame_type: str = "fast"         # fast / slow
    default_poll: str = "disabled"   # enabled / disabled
    poll_interval_s: float = 1.0
    parameters: list[TelemetryParam] = field(default_factory=list)
    expected_apid: int | None = None
    expected_identifier: int | None = None


@dataclass
class TelemetrySnapshot:
    """遥测参数值快照（单时刻）"""
    param_id: str
    param_name: str
    raw_bytes: bytes | None = None
    raw_value: int | float | None = None
    physical_value: float | str | None = None
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    checksum_ok: bool = True


@dataclass
class TelemetryUpdate:
    """遥测更新事件（通过 signal 发射）"""
    package_name: str
    snapshots: list[TelemetrySnapshot]
    timestamp: datetime = field(default_factory=datetime.now)


# ═══════════════════════════════════════════
# 指令系统模型
# ═══════════════════════════════════════════

@dataclass
class CommandDef:
    """单条指令定义（来自 Excel 一行）"""
    id: str                          # 指令代号 "APID_00C0"
    name: str                        # 指令名称 "常规遥测1"
    frame_header: str = "EB 90"
    app_process_id: str = "05 20"
    data_length: str = "00 01"       # 数据域长度（hex）
    command_code: str = "00 5A"      # 指令码（hex）
    default_param: str = ""          # 默认参数（hex）
    is_polling: bool = False         # 是否轮询指令


@dataclass
class InjectionParamDef:
    """参数注入定义（from Excel）"""
    name: str                        # 参数名称
    byte_offset: int = 0             # 字节偏移
    byte_length: int = 4             # 字节长度
    data_type: str = "float32"       # 数据类型
    default_value: str = ""
    unit: str = ""


@dataclass
class InjectionDef:
    """参数注入表定义（一张 Excel Sheet）"""
    name: str                        # "参数注入0x03FF"
    instruction_code: str = "03 FF"
    parameters: list[InjectionParamDef] = field(default_factory=list)


@dataclass
class FrameInfo:
    """解析后的帧头信息"""
    is_valid: bool = False
    identifier: int = 0
    apid: int = 0
    sequence_count: int = 0
    data_length: int = 0
    command_code: int | None = None
    checksum_ok: bool = True
    raw_length: int = 0


# ═══════════════════════════════════════════
# 测试用例模型
# ═══════════════════════════════════════════

@dataclass
class TimePointCheck:
    """时序验证中的单个时间点检查项"""
    offset_seconds: float = 0.0
    package: str = ""
    param_id: str = ""
    operator: str = "equals"
    expected_value: str = ""
    tolerance: float | None = None
    # 运行时填充
    actual_value: str | None = None
    actual_timestamp: str | None = None
    result: str | None = None


@dataclass
class ConditionCheck:
    """验证/等待条件"""
    param_id: str = ""
    operator: str = "equals"         # equals / greater_than / less_than / between / in / approx
    expected_value: str = ""
    tolerance: float | None = None
    # 运行时填充
    actual_value: str | None = None
    result: str | None = None


@dataclass
class StepDef:
    """测试步骤定义（来自 YAML）"""
    id: str = ""
    name: str = ""
    type: str = "send_command"       # StepType value
    timeout_s: float = 10.0
    on_fail: str = "stop"
    
    # send_command 字段
    command_id: str = ""
    param_value: str = ""
    
    # verify_telemetry / wait_for_condition 字段
    package: str = ""
    poll_interval_s: float = 1.0
    checks: list[ConditionCheck] = field(default_factory=list)
    
    # timing_verification 字段
    trigger_command: str = ""
    trigger_param: str = ""
    timepoints: list[TimePointCheck] = field(default_factory=list)
    
    # delay 字段
    duration_s: float = 1.0
    
    # goto 字段
    target_step: str = ""
    
    # script 字段
    script_content: str = ""
    script_language: str = "python"


@dataclass
class CaseDef:
    """测试用例定义（来自 YAML）"""
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    steps: list[StepDef] = field(default_factory=list)
    # 参数化
    params: dict[str, Any] = field(default_factory=dict)
    # 前置条件
    prerequisites: list[ConditionCheck] = field(default_factory=list)


@dataclass
class SuiteDef:
    """测试套件定义"""
    name: str = ""
    description: str = ""
    cases: list[CaseDef] = field(default_factory=list)
    # 嵌套套件
    suites: list[SuiteDef] = field(default_factory=list)


# ═══════════════════════════════════════════
# 执行结果模型
# ═══════════════════════════════════════════

@dataclass
class StepReport:
    """单步执行结果"""
    id: str = ""
    name: str = ""
    type: str = ""
    status: str = "pending"
    duration_s: float = 0.0
    # 配置快照（UI 配置了什么就记什么）
    config_snapshot: dict | None = None
    detail: str | None = None
    # 遥测快照
    telemetry_snapshots: list[TelemetrySnapshot] | None = None


@dataclass
class CaseReport:
    """单用例执行结果"""
    name: str = ""
    id: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = "pending"
    duration_s: float = 0.0
    fail_reason: str | None = None
    fail_detail: str | None = None
    steps: list[StepReport] = field(default_factory=list)


@dataclass
class SuiteReport:
    """套件执行结果"""
    project_name: str = ""
    suite_name: str = ""
    test_date: datetime = field(default_factory=datetime.now)
    duration_s: float = 0.0
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    ppcu_firmware_version: str = ""
    profile_version: str = ""
    cases: list[CaseReport] = field(default_factory=list)
    hardware_config: dict = field(default_factory=dict)
    raw_log_path: str = ""


# ═══════════════════════════════════════════
# 配置模型
# ═══════════════════════════════════════════

@dataclass
class ProfileConfig:
    """项目配置文件 (profile.yaml)"""
    name: str = ""
    version: str = "1.0"
    description: str = ""
    created: str = ""
    transport_type: str = "tcp"
    transport_config: dict = field(default_factory=dict)
    protocol_type: str = "ccsds"
    protocol_config: dict = field(default_factory=dict)
    telemetry_excel_path: str = ""
    telemetry_patches_path: str = ""
    telemetry_packages: list[dict] = field(default_factory=list)
    commands_excel_path: str = ""
    injections: list[dict] = field(default_factory=list)
    safety_policy_path: str = ""
    auto_connect: bool = False


@dataclass
class SafetyConfig:
    """安全策略配置"""
    enabled: bool = True
    blocked_categories: list[dict] = field(default_factory=list)
    high_risk_commands: list[dict] = field(default_factory=list)
    validate_param_range: bool = True
    max_injection_value: float = 600.0


@dataclass
class ProjectContext:
    """运行时项目上下文（ProfileLoader 的输出）"""
    name: str = ""
    profile: ProfileConfig | None = None
    telemetry_registry: Any | None = None   # TelemetryRegistry
    command_registry: Any | None = None      # CommandRegistry
    safety: SafetyConfig | None = None
    test_suites: list[SuiteDef] = field(default_factory=list)
    transport: Any | None = None             # Transport
    protocol: Any | None = None              # ProtocolCodec


# ═══════════════════════════════════════════
# 辅助方法
# ═══════════════════════════════════════════

def format_timestamp(dt: datetime | None = None) -> str:
    """统一时间戳格式"""
    dt = dt or datetime.now()
    return dt.strftime("%H:%M:%S.%f")[:12]


def format_duration(seconds: float) -> str:
    """统一耗时格式"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:04.1f}"
