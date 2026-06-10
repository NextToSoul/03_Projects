"""
序列号管理器
自动维护 CCSDS 14-bit 源包序列号（0x0000~0x3FFF 循环累加）
"""

import logging

logger = logging.getLogger(__name__)


class SequenceManager:
    """CCSDS 14-bit 源包序列号自动管理器"""

    def __init__(self, initial: int = 0, max_seq: int = 0x3FFF):
        self._current: int = initial
        self._max: int = max_seq
        self._wrap_count: int = 0  # 循环次数统计
    
    def next(self) -> int:
        """获取下一个序列号并自增"""
        seq = self._current
        self._current += 1
        if self._current > self._max:
            self._current = 0
            self._wrap_count += 1
            logger.info(f"Sequence number wrapped around (wrap #{self._wrap_count})")
        return seq
    
    def peek(self) -> int:
        """查看当前序列号（不消耗）"""
        return self._current
    
    def reset(self, value: int = 0):
        """重置序列号"""
        self._current = value
        self._wrap_count = 0
    
    @property
    def wrap_count(self) -> int:
        return self._wrap_count
    
    @property
    def total_sent(self) -> int:
        """总共发出的序列号数量（含回绕）"""
        return self._current + self._wrap_count * (self._max + 1)
