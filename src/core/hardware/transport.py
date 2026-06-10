"""
硬件传输层抽象
Transport 接口定义了统一的通讯方式，支持 TCP/CAN/串口等。
当前实现：TCPTransport — asyncio socket 连接串口转以太网通讯盒
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Transport(ABC):
    """硬件传输抽象——TCP、CAN、串口统一接口"""

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> bool:
        """建立连接"""
        ...

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        ...

    @abstractmethod
    async def send(self, data: bytes) -> int:
        """发送原始字节，返回发送字节数"""
        ...

    @abstractmethod
    async def recv(self, timeout_s: float | None = None) -> bytes | None:
        """接收原始字节，超时返回 None"""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @property
    @abstractmethod
    def transport_type(self) -> str:
        """返回 'tcp', 'can', 'serial'"""
        ...


class TCPTransport(Transport):
    """TCP 传输实现——连接串口转以太网通讯盒"""

    def __init__(self, config: dict[str, Any] | None = None):
        self._host: str = "127.0.0.1"
        self._port: int = 2000
        self._reconnect_max_retries: int = 3
        self._reconnect_interval_s: float = 2.0
        self._timeout_s: float = 3.0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected: bool = False
        
        if config:
            self._host = config.get("host", self._host)
            self._port = config.get("port", self._port)
            self._reconnect_max_retries = config.get("reconnect_max_retries", self._reconnect_max_retries)
            self._reconnect_interval_s = config.get("reconnect_interval_s", self._reconnect_interval_s)
            self._timeout_s = config.get("timeout_s", self._timeout_s)

    async def connect(self, config: dict[str, Any] | None = None) -> bool:
        if config:
            self._host = config.get("host", self._host)
            self._port = config.get("port", self._port)
        
        for attempt in range(1, self._reconnect_max_retries + 1):
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=self._timeout_s,
                )
                self._connected = True
                logger.info(f"TCP connected to {self._host}:{self._port} (attempt {attempt})")
                return True
            except (OSError, asyncio.TimeoutError, ConnectionRefusedError) as e:
                logger.warning(f"TCP connection attempt {attempt} failed: {e}")
                if attempt < self._reconnect_max_retries:
                    await asyncio.sleep(self._reconnect_interval_s)
        
        self._connected = False
        logger.error(f"TCP connection to {self._host}:{self._port} failed after all retries")
        return False

    async def disconnect(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
        self._connected = False
        self._reader = None
        self._writer = None

    async def send(self, data: bytes) -> int:
        if not self._writer:
            raise ConnectionError("Not connected")
        self._writer.write(data)
        await self._writer.drain()
        return len(data)

    async def recv(self, timeout_s: float | None = None) -> bytes | None:
        if not self._reader:
            raise ConnectionError("Not connected")
        
        timeout = timeout_s or self._timeout_s
        try:
            data = await asyncio.wait_for(self._reader.read(65535), timeout=timeout)
            return data if data else None  # 空字节 = 连接关闭
        except asyncio.TimeoutError:
            return None
    
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None
    
    @property
    def transport_type(self) -> str:
        return "tcp"
