# core/controller.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
from threading import Thread, Lock
from core.protocols import PelcoDProtocol, GS232BProtocol
from hardware.interfaces import SerialHandler, TCPHandler


class ControlSystem:
    def __init__(self, config, log_callback):
        self.config = config
        self.log = log_callback
        self.running = False
        self._connection_lock = Lock()
        self.gs232b = None
        self.pelco = None

        try:
            self._init_connections()
            self.log("[系统] 硬件初始化成功")
        except Exception as e:
            self.log(f"[错误] 初始化失败: {str(e)}")
            raise

    def _init_connections(self):
        with self._connection_lock:
            try:
                # 关闭旧连接
                if self.gs232b:
                    self.gs232b.close()
                if self.pelco and self.pelco.hw:
                    self.pelco.hw.close()

                # 初始化 GS-232B
                self.gs232b = self._create_handler("gs232b")
                self.log("[连接] GS-232B连接已建立")

                # 初始化 Pelco-D
                pelco_hw = self._create_handler("pelco")
                self.pelco = PelcoDProtocol(pelco_hw, self.config["pelco"])
                self.log("[连接] Pelco-D连接已建立")
            except Exception as e:
                self.log(f"[错误] 连接初始化失败: {str(e)}")
                raise

    def _create_handler(self, device):
        config = self.config[device]
        protocol = config["protocol"]
        handlers = {
            "serial": SerialHandler,
            "tcp": TCPHandler
        }

        handler = handlers[protocol](config, self.log)
        if not handler.connect():
            raise ConnectionError(f"{device} 连接失败")
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
                        self.log(f"[系统] 返回：{response}")
                        self.gs232b.send(response.encode())
            except Exception as e:
                self.log(f"[错误] 处理错误: {str(e)}")

    def _process_command(self, cmd: str) -> str:
        command_handlers = {
            'C2': self._handle_c2,
            'W': self._handle_w,
            r'\set_pos': self._handle_setpos
        }

        # 处理组合命令
        if cmd.startswith("C2W") or (cmd.startswith("W") and cmd.endswith("C2")):
            return self._handle_combined_command(cmd)

        # 遍历处理标准命令
        for prefix, handler in command_handlers.items():
            if cmd.startswith(prefix):
                return handler(cmd[len(prefix):].strip())

        return ""

    def _handle_combined_command(self, cmd: str) -> str:
        self.log("[命令] 接收到 C2 和 W 命令")
        w_cmd = cmd[3:] if cmd.startswith("C2W") else cmd[1:-2]
        w_result = self._execute_angle_control_command(w_cmd)
        return self._execute_angle_query_command() if w_result else ""

    def _handle_c2(self, _) -> str:
        return self._execute_angle_query_command()

    def _handle_w(self, cmd: str) -> str:
        return self._execute_angle_control_command(cmd)

    def _handle_setpos(self, cmd: str) -> str:
        parts = cmd.split()
        if len(parts) != 2:
            return ""

        try:
            azi, ele = map(float, parts)
            if ele < 0:
                return ""
            self.log(f"[命令] 收到 look4sat 角度指令: 方位 {azi} 俯仰 {ele}")
            return self._execute_angle_control_command(f"{round(azi)} {round(ele)}")
        except ValueError:
            return ""

    def _execute_angle_control_command(self, w_cmd: str) -> str:
        """执行 W 命令。"""
        try:
            parts = w_cmd.split()
            azi = float(parts[0])
            ele = float(parts[1])
            success = (
                    self.pelco.set_a    ngle(azi, 0x4B) and
                    self.pelco.set_angle(ele, 0x4D)
            )
            return "ACK\r\n" if success else ""
        except (IndexError, ValueError):
            self.log("[命令] W 命令参数解析失败")
            return ""

    def _execute_angle_query_command(self) -> str:
        """执行 C2 命令。"""
        self.log("[命令] 处理 C2 查询")
        azimuth = self.pelco.query_angle(0x51)
        elevation = self.pelco.query_angle(0x53)

        if azimuth is not None and elevation is not None:
            azimuth_deg = azimuth // 100
            elevation_deg = elevation // 100
            log_msg = f"水平角度 {azimuth_deg} 俯仰角度 {elevation_deg}"
            self.log(log_msg)
            return f"AZ={azimuth_deg:03d} EL={elevation_deg:03d}\r\n"
        return ""

    def stop(self):
        with self._connection_lock:
            self.running = False
            if self.gs232b:
                self.gs232b.close()
                self.gs232b = None
                self.log("[连接] GS-232B连接已关闭")
            if self.pelco:
                self.pelco.hw.close()
                self.pelco = None
                self.log("[连接] Pelco-D连接已关闭")
            if self.thread.is_alive():
                self.thread.join(timeout=5)