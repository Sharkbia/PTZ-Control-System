# core/controller.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
from threading import Thread, Lock
from core.protocols import PelcoDProtocol, GS232BProtocol
from hardware.interfaces import SerialHandler, TCPHandler, UDPHandler


class ControlSystem:
    def __init__(self, config, log_callback):
        self.config = config
        self.log = log_callback
        self.running = False
        self._connection_lock = Lock()  # 连接操作锁
        self.gs232b = None
        self.pelco = None

        try:
            self._init_connections()
            self.log("[系统] 硬件初始化成功")
        except Exception as e:
            self.log(f"[错误] 初始化失败: {str(e)}")
            raise

    def _init_connections(self):
        """单次初始化所有硬件连接"""
        with self._connection_lock:
            # 初始化GS-232B接口
            if not self.gs232b or not self.gs232b._is_connected:
                self.gs232b = self._create_handler("gs232b")
                self.log("[连接] GS-232B连接已建立")

            # 初始化Pelco-D接口
            if not self.pelco or not self.pelco.hw._is_connected:
                pelco_hw = self._create_handler("pelco")
                self.pelco = PelcoDProtocol(pelco_hw)
                self.log("[连接] Pelco-D连接已建立")

    def _create_handler(self, device):
        """创建硬件处理器"""
        config = self.config[device]
        protocol = config["protocol"]

        handlers = {
            "serial": SerialHandler,
            "tcp": TCPHandler,
            "udp": UDPHandler
        }

        handler = handlers[protocol](config)
        if not handler.connect():
            raise ConnectionError(f"{device}连接失败")
        return handler

    def start(self):
        """启动系统"""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()
            self.log("[系统] 系统已启动")

    def _run(self):
        """主控制循环"""
        while self.running:
            try:
                data = self.gs232b.recv(1024, timeout=1.0)
                if data:
                    cmd = GS232BProtocol.parse_command(data)
                    self.log(f"[命令] 收到命令: {cmd}")
                    response = self._process_command(cmd)
                    if response:
                        self.gs232b.send(response.encode())
            except Exception as e:
                self.log(f"[错误] 处理错误: {str(e)}")

    def _process_command(self, cmd: str) -> str:
        if cmd == "C2":
            self.log("[命令] 处理C2查询")
            azimuth = self.pelco.query_angle(0x51)
            elevation = self.pelco.query_angle(0x53)

            if azimuth is not None and elevation is not None:
                return f"AZ={azimuth // 100:03d} EL={elevation // 100:03d}\r\n"
            return ""

        elif cmd.startswith("W"):
            try:
                parts = cmd[1:].split()
                azi = float(parts[0])
                ele = float(parts[1])
                success = (
                        self.pelco.set_angle(azi, 0x4B) and
                        self.pelco.set_angle(ele, 0x4D)
                )
                return "ACK\r\n" if success else ""
            except:
                return ""
        return ""

    def stop(self):
        """安全关闭系统"""
        with self._connection_lock:
            self.running = False
            if self.gs232b:
                self.gs232b.close()
                self.log("[连接] GS-232B连接已关闭")
            if self.pelco:
                self.pelco.hw.close()
                self.log("[连接] Pelco-D连接已关闭")
            if self.thread.is_alive():
                self.thread.join()

    def get_current_azimuth(self):
        """获取当前方位角"""
        return self.pelco.query_angle(0x51) // 100 

    def get_current_elevation(self):
        """获取当前俯仰角"""
        return self.pelco.query_angle(0x53) // 100 