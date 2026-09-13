# core/controller.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import re
from threading import Thread, Lock
from core.protocols import PelcoDProtocol, parse_gs232b_command
from hardware.interfaces import SerialHandler, TCPHandler, UDPHandler

# Command prefix regex for splitting concatenated commands from HRD Rotator
# C2(?!W)   - match C2 but NOT C2W (keep C2W as combined command)
# (?<!C2)W  - match W but NOT when preceded by C2 (part of C2W)
_CMD_SPLIT_RE = re.compile(r'(?<!\\)(?=C2(?!W)|(?<!C2)W|\\set_pos)')


class ControlSystem:
    def __init__(self, config, log_callback):
        self.config = config
        self.log = log_callback
        self.running = False
        self._connection_lock = Lock()
        self.gs232b = None
        self.pelco = None
        self.thread = None
        self._cmd_buffer = ""

        try:
            self._init_connections()
            self.log("[系统] 硬件初始化成功")
        except Exception as e:
            self.log(f"[错误] 初始化失败: {str(e)}")
            raise

    def _init_connections(self):
        with self._connection_lock:
            try:
                if self.gs232b:
                    self.gs232b.close()
                if self.pelco and self.pelco.hw:
                    self.pelco.hw.close()

                self.gs232b = self._create_handler("gs232b")
                self.log("[连接] GS-232B连接已建立")

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
            "tcp": TCPHandler,
            "udp": UDPHandler
        }
        handler_cls = handlers.get(protocol)
        if not handler_cls:
            raise ValueError(f"不支持的协议: {protocol}")
        handler = handler_cls(config, self.log)
        if not handler.connect():
            raise ConnectionError(f"{device} 连接失败")
        return handler

    def start(self):
        """启动系统"""
        if not self.running:
            if self.thread and self.thread.is_alive():
                self.log("[警告] 系统已在运行中")
                return
            self._cmd_buffer = ""
            self.running = True
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()
            self.log("[系统] 系统已启动")

    @staticmethod
    def _split_commands(raw):
        """将粘连的原始字符串拆分为独立命令列表。

        处理 HRD Rotator 快速发送时产生的粘包问题：
        C2C2 -> [C2, C2]
        C2W 114 51C2 -> [C2W 114 51, C2]
        W 114 51C2 -> [W 114 51, C2]
        """
        if not raw.strip():
            return []
        return [c for c in _CMD_SPLIT_RE.split(raw) if c.strip()]

    def _run(self):
        """主控制循环"""
        while self.running:
            try:
                data = self.gs232b.recv(1024, timeout=1.0)
                if data:
                    text = self._cmd_buffer + parse_gs232b_command(data)
                    commands = self._split_commands(text)

                    if not commands:
                        continue

                    # 最后一个片段可能不完整，保留在缓冲区
                    last = commands[-1].strip()
                    if last and not any(
                        last.startswith(p) for p in ('C2', 'W', '\\set_pos')
                    ):
                        self._cmd_buffer = commands.pop()
                    else:
                        self._cmd_buffer = ""

                    for cmd in commands:
                        cmd = cmd.strip()
                        if not cmd:
                            continue
                        self.log(f"[命令] 收到命令: {cmd}")
                        response = self._process_command(cmd)
                        if response:
                            self.log(f"[系统] 返回：{response}")
                            self.gs232b.send(response.encode())

            except Exception as e:
                self.log(f"[错误] 处理错误: {str(e)}")

    def _process_command(self, cmd):
        # 处理组合命令 C2W / WC2
        if cmd.startswith("C2W") or (cmd.startswith("W") and cmd.endswith("C2")):
            return self._handle_combined_command(cmd)

        for prefix, handler in [
            ('C2', self._handle_c2),
            ('W', self._handle_w),
            ('\\set_pos', self._handle_setpos),
        ]:
            if cmd.startswith(prefix):
                return handler(cmd[len(prefix):].strip())

        return ""

    def _handle_combined_command(self, cmd):
        self.log("[命令] 接收到 C2 和 W 组合命令")
        w_cmd = cmd[3:] if cmd.startswith("C2W") else cmd[1:-2]
        w_result = self._execute_angle_control_command(w_cmd)
        return self._execute_angle_query_command() if w_result else ""

    def _handle_c2(self, _):
        return self._execute_angle_query_command()

    def _handle_w(self, cmd):
        return self._execute_angle_control_command(cmd)

    def _handle_setpos(self, cmd):
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

    def _execute_angle_control_command(self, w_cmd):
        """执行 W 命令：设置方位角和俯仰角"""
        try:
            parts = w_cmd.split()
            azi = float(parts[0])
            ele = float(parts[1])
            success = (
                    self.pelco.set_angle(azi, PelcoDProtocol.CMD_SET_AZIMUTH) and
                    self.pelco.set_angle(ele, PelcoDProtocol.CMD_SET_ELEVATION)
            )
            return "ACK\r\n" if success else ""
        except (IndexError, ValueError):
            self.log("[命令] W 命令参数解析失败")
            return ""

    def _execute_angle_query_command(self):
        """执行 C2 命令：查询当前方位角和俯仰角"""
        self.log("[命令] 处理 C2 查询")
        azimuth = self.pelco.query_angle(PelcoDProtocol.CMD_QUERY_AZIMUTH)
        elevation = self.pelco.query_angle(PelcoDProtocol.CMD_QUERY_ELEVATION)

        if azimuth is not None and elevation is not None:
            azimuth_deg = azimuth // 100
            elevation_deg = elevation // 100
            self.log(f"水平角度 {azimuth_deg} 俯仰角度 {elevation_deg}")
            return f"AZ={azimuth_deg:03d} EL={elevation_deg:03d}\r\n"
        return ""

    def select_angle(self, angle, set_cmd):
        """选择角度并执行命令。"""
        axis = "俯仰角度" if set_cmd == PelcoDProtocol.CMD_SET_ELEVATION else "水平角度"
        self.log(f"[命令] 选择角度 {angle} 并执行{axis}调整命令")
        self.pelco.set_angle(angle, set_cmd)

    def stop(self):
        with self._connection_lock:
            self.running = False
            self._cmd_buffer = ""
            if self.gs232b:
                self.gs232b.close()
                self.gs232b = None
                self.log("[连接] GS-232B连接已关闭")
            if self.pelco:
                self.pelco.hw.close()
                self.pelco = None
                self.log("[连接] Pelco-D连接已关闭")
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5)
