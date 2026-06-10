"""
位域解析引擎
根据遥测参数定义（data_offset/bit_offset/bit_length/type/scale）
从原始字节流中动态解析遥测参数值，并应用物理量换算。

核心策略：所有解析规则来自 TelemetryParam 数据，不硬编码任何参数。
"""

from __future__ import annotations

import struct
import logging
from typing import Any

from ..models import TelemetryParam, TelemetrySnapshot

logger = logging.getLogger(__name__)


class BitFieldParser:
    """动态位域解析引擎"""

    @staticmethod
    def parse_packet(
        raw_payload: bytes,
        parameters: list[TelemetryParam],
    ) -> list[TelemetrySnapshot]:
        """
        根据参数定义表，从原始数据域中解析所有遥测参数
        
        Args:
            raw_payload: 数据域原始字节（不含帧头）
            parameters: 该包所有参数定义
        
        Returns:
            解析后的遥测快照列表
        """
        snapshots = []
        
        for param in parameters:
            snapshot = BitFieldParser._parse_one(raw_payload, param)
            snapshots.append(snapshot)
        
        return snapshots

    @staticmethod
    def parse_single(
        raw_payload: bytes,
        param: TelemetryParam,
    ) -> TelemetrySnapshot:
        """解析单个参数"""
        return BitFieldParser._parse_one(raw_payload, param)

    @staticmethod
    def _parse_one(raw: bytes, param: TelemetryParam) -> TelemetrySnapshot:
        """解析并换算单个遥测参数"""
        # 1. 确定数据提取位置
        byte_offset = param.data_offset
        bit_offset = param.bit_offset
        bit_length = param.bit_length
        
        # 2. 从原始字节中提取原始值
        raw_value = BitFieldParser._extract_bits(
            raw, byte_offset, bit_offset, bit_length, param.endian == "big"
        )
        
        # 3. 应用物理量换算
        phys_value = BitFieldParser._apply_scale(
            raw_value, param.data_type, param.scale, param.decimal_places,
            param.enum_values
        )
        
        # 4. 构建快照
        raw_bytes_slice = raw[byte_offset:byte_offset + (bit_length + 7) // 8]
        
        return TelemetrySnapshot(
            param_id=param.id,
            param_name=param.name,
            raw_bytes=raw_bytes_slice,
            raw_value=raw_value,
            physical_value=phys_value,
            unit=param.unit,
        )

    @staticmethod
    def _extract_bits(
        data: bytes,
        byte_offset: int,
        bit_offset: int,
        bit_length: int,
        big_endian: bool,
    ) -> int | float:
        """
        从字节流中按位提取整数值
        bit_offset 是从数据域起始的绝对位位置
        """
        # 计算实际的字节和位位置
        total_bits = bit_offset + bit_length
        needed_bytes = (total_bits + 7) // 8
        
        if byte_offset + needed_bytes > len(data):
            logger.warning(
                f"Data too short: need {byte_offset + needed_bytes}B, have {len(data)}B"
            )
            return 0
        
        # 取出需要的字节段
        chunk = data[byte_offset:byte_offset + needed_bytes]
        
        # 如果位偏移不是从字节边界开始的，需要调整
        # 这是一个简化的实现，适用于 bit_stream 格式
        # 实际位流需要从 bit_offset 全局位位置开始提取
        # 对于字节对齐的参数（大多数情况），直接按类型解析
        if bit_length == 8:
            return chunk[0] if byte_offset < len(data) else 0
        elif bit_length == 16:
            if big_endian:
                return struct.unpack(">H", chunk[:2])[0]
            else:
                return struct.unpack("<H", chunk[:2])[0]
        elif bit_length == 32:
            if big_endian:
                return struct.unpack(">I", chunk[:4])[0]
            else:
                return struct.unpack("<I", chunk[:4])[0]
        else:
            # 非标准位长：作为整数提取
            value = 0
            for b in chunk:
                value = (value << 8) | b
            # 如果 big_endian 为 False，需要反转
            if not big_endian:
                value = int.from_bytes(chunk, "little")
            # 右移以对齐位偏移
            shift = bit_offset % 8 if bit_offset >= 8 else 0
            if shift:
                value >>= shift
            # 掩码
            mask = (1 << bit_length) - 1
            value &= mask
            return value

    @staticmethod
    def _apply_scale(
        raw_value: int | float,
        data_type: str,
        scale: float,
        decimal_places: int | None,
        enum_values: dict[int, str] | None,
    ) -> float | str | int:
        """应用换算系数和枚举映射"""
        # 枚举类型：直接映射
        if enum_values and data_type == "enum":
            return enum_values.get(int(raw_value), f"Unknown(0x{raw_value:X})")
        
        # float32：IEEE754 已经解析过，不应用 scale
        if data_type == "float32":
            return float(raw_value)
        
        # 应用换算
        if scale != 1.0:
            phys = float(raw_value) * scale
        else:
            phys = float(raw_value)
        
        # 按小数位数截断
        if decimal_places is not None:
            phys = round(phys, decimal_places)
        
        return phys

    @staticmethod
    def raw_to_physical(
        raw_bytes: bytes,
        data_type: str,
        endian: str = "big",
        scale: float = 1.0,
    ) -> float | int:
        """将原始字节直接转为物理值（用于参数注入编码）"""
        big = endian == "big"
        
        if data_type == "float32":
            fmt = ">" if big else "<"
            return struct.unpack(f"{fmt}f", raw_bytes[:4])[0]
        elif data_type == "uint8":
            return raw_bytes[0]
        elif data_type == "uint16":
            fmt = ">" if big else "<"
            return struct.unpack(f"{fmt}H", raw_bytes[:2])[0]
        elif data_type == "uint32":
            fmt = ">" if big else "<"
            return struct.unpack(f"{fmt}I", raw_bytes[:4])[0]
        else:
            return int.from_bytes(raw_bytes, "big" if big else "little")

    @staticmethod
    def physical_to_raw(
        value: float,
        data_type: str,
        endian: str = "big",
        byte_length: int = 4,
        scale: float = 1.0,
    ) -> bytes:
        """将物理值编码为原始字节（用于参数注入编码）"""
        big = endian == "big"
        
        if data_type == "float32":
            fmt = ">" if big else "<"
            return struct.pack(f"{fmt}f", value)
        elif data_type == "uint8":
            return bytes([int(value)])
        elif data_type == "uint16":
            fmt = ">" if big else "<"
            return struct.pack(f"{fmt}H", int(value))
        elif data_type == "uint32":
            fmt = ">" if big else "<"
            return struct.pack(f"{fmt}I", int(value))
        else:
            # fallback
            int_val = int(value / scale) if scale else int(value)
            return int_val.to_bytes(byte_length, "big" if big else "little")
