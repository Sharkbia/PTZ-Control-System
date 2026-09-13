# hardware/interfaces.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import serial
import socket
import select
from abc import ABC, abstractmethod


class HardwareInterface(ABC):
    def __init__(self, config, log_callback):
        self.config = config
        self.log = log_callback
        self._is_connected = False

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def send(self, data: bytes) -> bool: ...

    @abstractmethod
    def recv(self, length: int, timeout: float = None) -> bytes: ...

    @abstractmethod
    def close(self): ...


class SerialHandler(HardwareInterface):
    def __init__(self, config, log_callback):
        super().__init__(config, log_callback)
        self.ser = None

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
            if timeout is not None:
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
            try:
                self.ser.close()
            except Exception:
                pass
            finally:
                self._is_connected = False


class TCPHandler(HardwareInterface):
    CONNECT_TIMEOUT = 30  # 连接等待超时（秒）

    def __init__(self, config, log_callback):
        super().__init__(config, log_callback)
        self.sock = None
        self.client_sock = None

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.config["tcp"]["host"], self.config["tcp"]["port"]))
            self.sock.listen(1)
            self.log(f"[TCP] 正在 {self.config['tcp']['host']}:{self.config['tcp']['port']} 监听...")

            import time
            start_time = time.time()
            while not self._is_connected:
                # 检查是否超时
                if time.time() - start_time > self.CONNECT_TIMEOUT:
                    self.close()
                    raise ConnectionError(f"TCP 等待连接超时（{self.CONNECT_TIMEOUT}秒）")

                readable, _, _ = select.select([self.sock], [], [], 0.5)
                if self.sock in readable:
                    try:
                        self.client_sock, addr = self.sock.accept()
                        # 统一使用 settimeout 而非 setblocking
                        self._is_connected = True
                        self.log(f"[TCP] 已接受来自 {addr} 的连接")
                    except BlockingIOError:
                        pass

            return True

        except Exception as e:
            if not isinstance(e, ConnectionError):
                raise ConnectionError(f"TCP服务器启动失败：{str(e)}")
            raise

    def send(self, data: bytes) -> bool:
        if not self._is_connected or not self.client_sock:
            return False
        try:
            # 使用 sendall 确保数据完整发送
            self.client_sock.sendall(data)
            return True
        except Exception as e:
            self.log(f"[错误] TCP发送错误：{str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        if not self._is_connected or not self.client_sock:
            return b""
        try:
            if timeout is not None:
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
            except Exception:
                pass
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self._is_connected = False


class UDPHandler(HardwareInterface):
    def __init__(self, config, log_callback):
        super().__init__(config, log_callback)
        self.sock = None
        self._remote_addr = None

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            udp_cfg = self.config["udp"]
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            local_host = udp_cfg.get("local_host", "0.0.0.0")
            local_port = udp_cfg["local_port"]
            self.sock.bind((local_host, local_port))

            remote_host = udp_cfg["remote_host"]
            remote_port = udp_cfg["remote_port"]
            self._remote_addr = (remote_host, remote_port)

            self._is_connected = True
            self.log(f"[UDP] 已绑定 {local_host}:{local_port}，远程 {remote_host}:{remote_port}")
            return True
        except Exception as e:
            raise ConnectionError(f"UDP 连接失败：{str(e)}")

    def send(self, data: bytes) -> bool:
        if not self._is_connected:
            return False
        try:
            sent = self.sock.sendto(data, self._remote_addr)
            return sent == len(data)
        except Exception as e:
            self.log(f"[错误] UDP 发送失败: {str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        if not self._is_connected:
            return b""
        try:
            if timeout is not None:
                self.sock.settimeout(timeout)
            data, _ = self.sock.recvfrom(length)
            return data
        except socket.timeout:
            return b""
        except Exception as e:
            self.log(f"[错误] UDP 接收错误: {str(e)}")
            return b""

    def close(self):
        if self._is_connected and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            finally:
                self._is_connected = False
