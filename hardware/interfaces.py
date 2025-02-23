# hardware/interfaces.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import serial
import socket
from abc import ABC, abstractmethod


class HardwareInterface(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def send(self, data: bytes) -> bool: ...

    @abstractmethod
    def recv(self, length: int, timeout: float = None) -> bytes: ...

    @abstractmethod
    def close(self): ...


class SerialHandler(HardwareInterface):
    def __init__(self, config):
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
        if not self._is_connected:
            raise ConnectionAbortedError("连接未建立")
        try:
            return self.ser.write(data) == len(data)
        except Exception as e:
            print(f"串口发送错误：{str(e)}")
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
            print(f"串口接收错误：{str(e)}")
            return b""

    def close(self):
        if self._is_connected and self.ser:
            self.ser.close()
            self._is_connected = False


class TCPHandler(HardwareInterface):
    def __init__(self, config):
        self.config = config
        self.sock = None
        self.conn = None
        self.addr = None
        self._is_connected = False

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.config["tcp"]["host"], self.config["tcp"]["port"]))
            self.sock.listen(1)
            self._is_connected = True
            return True
        except socket.error as e:
            raise ConnectionError(f"TCP连接失败：{str(e)}")

    def send(self, data: bytes) -> bool:
        if not self._is_connected or not self.conn:
            return False
        try:
            return self.conn.send(data) == len(data)
        except Exception as e:
            print(f"TCP发送错误：{str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        try:
            if not self.conn:
                self.conn, self.addr = self.sock.accept()
            if timeout:
                self.conn.settimeout(timeout)
            return self.conn.recv(length)
        except socket.timeout:
            return b""
        except Exception as e:
            print(f"TCP接收错误：{str(e)}")
            return b""

    def close(self):
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()
        self._is_connected = False


class UDPHandler(HardwareInterface):
    def __init__(self, config):
        self.config = config
        self.sock = None
        self.addr = None
        self._is_connected = False

    def connect(self) -> bool:
        if self._is_connected:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.config["udp"]["host"], self.config["udp"]["port"]))
            self._is_connected = True
            return True
        except socket.error as e:
            raise ConnectionError(f"UDP连接失败：{str(e)}")

    def send(self, data: bytes) -> bool:
        if not self._is_connected or not self.addr:
            return False
        try:
            return self.sock.sendto(data, self.addr) == len(data)
        except Exception as e:
            print(f"UDP发送错误：{str(e)}")
            return False

    def recv(self, length: int, timeout: float = None) -> bytes:
        try:
            if timeout:
                self.sock.settimeout(timeout)
            data, self.addr = self.sock.recvfrom(length)
            return data
        except socket.timeout:
            return b""
        except Exception as e:
            print(f"UDP接收错误：{str(e)}")
            return b""

    def close(self):
        if self.sock:
            self.sock.close()
        self._is_connected = False