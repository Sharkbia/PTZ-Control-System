# hardware/interfaces.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import serial
import socket
import select
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
            self.log(f"[错误] 串口发送失败: {str(e)}")
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
    def __init__(self, config, log_callback):
        super().__init__(config, log_callback)
        self.sock = None
        self.client_sock = None
        self._is_connected = False

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            # 创建服务器套接字
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.config["tcp"]["host"], self.config["tcp"]["port"]))
            self.sock.listen(1)
            self.log(f"[TCP] 正在 {self.config['tcp']['host']}:{self.config['tcp']['port']} 监听...")

            while not self._is_connected:
                # 使用 select 来检查是否有新的连接请求
                readable, writable, exceptional = select.select([self.sock], [], [], 0.5)
                if self.sock in readable:
                    try:
                        # 尝试接受客户端连接
                        self.client_sock, addr = self.sock.accept()
                        self.client_sock.setblocking(False)  # 设置为非阻塞模式
                        self._is_connected = True
                        self.log(f"[TCP] 已接受来自 {addr} 的连接")
                    except BlockingIOError:
                        # 当前没有客户端连接，继续等待
                        pass

            return True

        except Exception as e:
            raise ConnectionError(f"TCP服务器启动失败：{str(e)}")

    def send(self, data: bytes) -> bool:
        if not self._is_connected or not self.client_sock:
            return False
        try:
            return self.client_sock.send(data) == len(data)
        except Exception as e:
            self.log(f"[错误] TCP发送错误：{str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        if not self._is_connected or not self.client_sock:
            return b""
        try:
            if timeout:
                self.client_sock.settimeout(timeout)
            return self.client_sock.recv(length)
        except socket.timeout:
            return b""
        except Exception as e:
            self.log(f"[错误] TCP接收错误：{str(e)}")
            return b""

    def close(self):
        """关闭所有连接"""
        if self.client_sock:
            try:
                self.client_sock.close()
            except Exception as e:
                self.log(f"[错误] 客户端套接字关闭错误：{str(e)}")
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                self.log(f"[错误] 服务器套接字关闭错误：{str(e)}")
        self._is_connected = False