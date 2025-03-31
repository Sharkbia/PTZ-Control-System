# hardware/interfaces.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import serial
import socket
from abc import ABC, abstractmethod


class HardwareInterface(ABC):
    def __init__(self, config, log_callback):  # 新增 log_callback 参数
        self.config = config
        self.log = log_callback  # 保存日志回调函数
        self._is_connected = False  # 可选：统一管理连接状态

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def send(self, data: bytes) -> bool: ...

    @abstractmethod
    def recv(self, length: int, timeout: float = None) -> bytes: ...

    @abstractmethod
    def close(self): ...


class SerialHandler(HardwareInterface):
    def __init__(self, config, log_callback):  # 新增 log_callback
        super().__init__(config, log_callback)  # 调用父类初始化
        self.config = config
        self.ser = None
        self._is_connected = False

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            self.ser = serial.Serial(
                port=self.config["serial"]["port"],
                baudrate=self.config["serial"]["baudrate"],
                timeout=1
            )
            self._is_connected = True
            return True
        except serial.SerialException as e:
            raise ConnectionError(f"串口连接失败：{str(e)}")

    def send(self, data: bytes) -> bool:
        try:
            return self.ser.write(data) == len(data)
        except Exception as e:
            self.log(f"[错误] 串口发送失败: {str(e)}")  # 使用日志回调
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        try:
            if timeout:
                original_timeout = self.ser.timeout
                self.ser.timeout = timeout
                data = self.ser.read(length)
                self.ser.timeout = original_timeout
                return data
            return self.ser.read(length)
        except Exception as e:
            self.log(f"[错误] 串口接收错误：{str(e)}")
            return b""

    def close(self):
        if self._is_connected and self.ser:
            self.ser.close()
            self._is_connected = False


class TCPHandler(HardwareInterface):
    def __init__(self, config, log_callback):  # 必须包含 log_callback
        super().__init__(config, log_callback)
        self.sock = None
        self._is_connected = False

    def connect(self) -> bool:
        if self._is_connected:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.config["tcp"]["host"], self.config["tcp"]["port"]))
            self._is_connected = True
            return True
        except socket.error as e:
            raise ConnectionError(f"TCP连接失败：{str(e)}")

    # 删除原 listen/accept 相关逻辑，简化 send/recv
    def send(self, data: bytes) -> bool:
        if not self._is_connected:
            return False
        try:
            return self.sock.send(data) == len(data)
        except Exception as e:
            self.log(f"[错误] TCP发送错误：{str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        try:
            if timeout:
                self.sock.settimeout(timeout)
            return self.sock.recv(length)
        except socket.timeout:
            return b""
        except Exception as e:
            self.log(f"[错误] TCP接收错误：{str(e)}")
            return b""