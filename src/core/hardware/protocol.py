"""
协议编解码层
ProtocolCodec 接口定义了统一的帧编解码方式。
当前实现：CCSDSCodec — CCSDS Space Packet Protocol
"""

from __future__ import annotations

import logging
import struct
from abc import ABC, abstractmethod
from typing import Any

from ..models import CommandDef, FrameInfo

logger = logging.getLogger(__name__)


class ProtocolCodec(ABC):
    """协议编解码抽象——CCSDS、CAN 帧、Modbus 统一接口"""

    @abstractmethod
    def encode_command(self, cmd_def: CommandDef, seq: int,
                       params: dict | None = None) -> bytes:
        """将指令定义编码为发送字节流"""
        ...

    @abstractmethod
    def decode_frame(self, raw: bytes) -> FrameInfo:
        """解析原始字节为结构化帧信息"""
        ...

    @abstractmethod
    def calculate_checksum(self, frame: bytes) -> bytes:
        """计算校验和"""
        ...

    @property
    @abstractmethod
    def protocol_type(self) -> str:
        ...


class CCSDSCodec(ProtocolCodec):
    """
    CCSDS Space Packet 协议编解码
    帧结构：
      字节 0-1:  标识符 0xEB90
      字节 2-3:  Version(3) + Type(1) + SubHdr(1) + APID(11)
      字节 4-5:  GroupFlag(2) + SequenceCount(14)
      字节 6-7:  数据域长度（实际长度-1）
      字节 8-9:  指令码
      字节 10~N: 参数（可选）
      字节 N+1~N+2: 校验和（字节 3~N 求和取反，取低16位）
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._command_identifier: int = 0xEB90
        self._telemetry_identifier: int = 0x1ACF
        self._apid: int = 0x520
        self._endian: str = "big"
        self._checksum_range: tuple[int, int] = (2, 9)  # 从字节3到字节10
        
        if config:
            self._command_identifier = config.get('command_identifier', config.get('identifier', self._command_identifier))
            self._telemetry_identifier = config.get('telemetry_identifier', config.get('identifier', 0x1ACF))
            self._apid = config.get('apid', self._apid)
            self._endian = config.get("endian", self._endian)
            cs_config = config.get("checksum_config", {})
            if cs_config:
                self._checksum_range = tuple(cs_config.get("range", self._checksum_range))
    
    def encode_command(self, cmd_def: CommandDef, seq: int,
                       params: dict | None = None) -> bytes:
        """编码一条 CCSDS 指令帧"""
        # 1. 解析指令码
        cmd_code = self._hex_to_bytes(cmd_def.command_code, 2)
        
        # 2. 解析参数
        param_bytes = bytearray()
        if params:
            param_str = params.get("value", cmd_def.default_param)
            if param_str:
                param_bytes = bytearray(self._hex_to_bytes(param_str))
        elif cmd_def.default_param:
            param_bytes = bytearray(self._hex_to_bytes(cmd_def.default_param))
        
        # 3. 计算数据域长度（指令码 + 参数，实际长度-1）
        data_payload = cmd_code + bytes(param_bytes)
        data_length = len(data_payload) - 1
        
        # 4. 构建完整帧（不含校验和）
        frame = bytearray()
        frame += struct.pack(">H", self._command_identifier)           # 字节 0-1: 标识符
        
        # 字节 2-3: Version(3) + Type(1) + SubHdr(1) + APID(11)
        # Version=0, Type=0, SubHdr=0, APID_high=5, APID_low=0x20
        frame += struct.pack(">H", self._apid)                  # 字节 2-3: APID
        
        # 字节 4-5: GroupFlag=0b11 + SeqCount (14-bit)
        frame += struct.pack(">H", 0xC000 | (seq & 0x3FFF))    # 字节 4-5
        
        # 字节 6-7: 数据域长度
        frame += struct.pack(">H", data_length)                 # 字节 6-7
        
        # 数据域
        frame += data_payload                                   # 字节 8~N
        
        # 5. 计算校验和（从字节 3 开始）
        checksum = self.calculate_checksum(bytes(frame))
        frame += checksum
        
        return bytes(frame)
    
    def decode_frame(self, raw: bytes) -> FrameInfo:
        """解析 CCSDS 帧"""
        info = FrameInfo(raw_length=len(raw))
        
        if len(raw) < 10:
            info.is_valid = False
            return info
        
        # 解析帧头
        info.identifier = struct.unpack(">H", raw[0:2])[0]
        info.apid = struct.unpack(">H", raw[2:4])[0]
        seq_field = struct.unpack(">H", raw[4:6])[0]
        info.sequence_count = seq_field & 0x3FFF
        info.data_length = struct.unpack(">H", raw[6:8])[0]
        
        # 校验标识符
        info.is_valid = (info.identifier == self._command_identifier or info.identifier == self._telemetry_identifier)
        
        # 提取指令码（如果有）
        if len(raw) >= 10:
            info.command_code = struct.unpack(">H", raw[8:10])[0]
        
        # 校验 checksum（如果帧足够长）
        if len(raw) >= 12:
            expected_cs = raw[-2:]
            # 校验范围：从字节 3 到数据域结束
            cs_start = self._checksum_range[0]
            cs_end = len(raw) - 2  # 去掉最后2字节校验和
            if cs_end > cs_start:
                calculated = self._calc_checksum(raw[cs_start:cs_end])
                info.checksum_ok = (expected_cs == calculated)
            else:
                info.checksum_ok = True
        else:
            info.checksum_ok = True
        
        return info
    
    def calculate_checksum(self, frame: bytes) -> bytes:
        """计算校验和：指定范围内字节求和取反，取低16bit"""
        cs_start = self._checksum_range[0]
        cs_end = len(frame)
        return self._calc_checksum(frame[cs_start:cs_end])
    
    def _calc_checksum(self, data: bytes) -> bytes:
        """单字节求和 → 取反 → 低16位"""
        total = sum(data) & 0xFFFF
        checksum = (~total) & 0xFFFF
        return struct.pack(">H", checksum)
    
    @staticmethod
    def _hex_to_bytes(hex_str: str, expected_length: int | None = None) -> bytes:
        """将 '00 5A' 格式的 hex 字符串转为字节"""
        clean = hex_str.replace(" ", "").replace("0x", "").replace("0X", "")
        if len(clean) % 2:
            clean = "0" + clean
        result = bytes.fromhex(clean)
        if expected_length and len(result) < expected_length:
            result = b"\x00" * (expected_length - len(result)) + result
        return result
    
    @property
    def protocol_type(self) -> str:
        return "ccsds"
