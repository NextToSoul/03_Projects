"""
PPCU TestBench — 枚举与类型常量定义
所有枚举集中在此，避免循环导入
"""

from enum import Enum, auto


class PollMode(str, Enum):
    """遥测包轮询模式"""
    DISABLED = "disabled"       # 空闲，什么也不发
    SINGLE = "single"           # 单次查询，发一次等一次
    ACTIVE = "active"           # 持续轮询，按周期自动发
    PAUSED = "paused"           # 暂停，保留缓存


class FrameType(str, Enum):
    """遥测帧类型"""
    FAST = "fast"              # 快帧：PPCU 周期上报，PC 只需请求
    SLOW = "slow"              # 慢帧：PC 查询才应答


class DataType(str, Enum):
    """遥测参数数据类型"""
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    FLOAT32 = "float32"
    ENUM = "enum"


class Endian(str, Enum):
    """字节序"""
    BIG = "big"
    LITTLE = "little"


class StepType(str, Enum):
    """测试步骤类型"""
    SEND_COMMAND = "send_command"
    VERIFY_TELEMETRY = "verify_telemetry"
    WAIT_CONDITION = "wait_for_condition"
    TIMING_VERIFICATION = "timing_verification"
    DELAY = "delay"
    SCRIPT = "script"
    ERROR_INJECT = "error_inject"


class StepStatus(str, Enum):
    """步骤执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    BLOCKED = "blocked"
    ERROR = "error"


class CaseStatus(str, Enum):
    """用例执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class OnFailAction(str, Enum):
    """步骤失败后的行为"""
    STOP = "stop"               # 终止用例
    CONTINUE = "continue"       # 继续执行后续步骤
    GOTO = "goto"               # 跳转到指定步骤


class TransportType(str, Enum):
    """传输层类型"""
    TCP = "tcp"
    CAN = "can"
    SERIAL = "serial"
    CUSTOM = "custom"


class ProtocolType(str, Enum):
    """协议类型"""
    CCSDS = "ccsds"
    CAN = "can"
    MODBUS = "modbus"
    CUSTOM = "custom"


class ChecksumType(str, Enum):
    """校验和类型"""
    SUM_INVERT = "sum_invert"   # 求和取反
    CRC16 = "crc16"
    NONE = "none"


class SafetyLevel(str, Enum):
    """安全告警级别"""
    INFO = "info"
    WARNING = "warning"
    BLOCKED = "blocked"
    CRITICAL = "critical"


# 预定义的指令操作码（仅作参考，实际从 Excel 加载）
HARD_CODED_REFERENCE = False
