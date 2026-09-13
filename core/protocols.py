# core/protocols.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details


class PelcoDProtocol:
    START_BYTE = 0xFF
    DEFAULT_ADDRESS = 0x01

    # 查询命令常量（消除魔数）
    CMD_QUERY_AZIMUTH = 0x51
    CMD_QUERY_ELEVATION = 0x53
    CMD_SET_AZIMUTH = 0x4B
    CMD_SET_ELEVATION = 0x4D

    def __init__(self, hardware, config):
        self.hw = hardware
        self.config = config
        self.address = self.DEFAULT_ADDRESS

        # 启动时校验一次角度修正参数
        corr = self.config["angle_correction"]
        if corr["min_elevation"] > corr["max_elevation"]:
            raise ValueError("最小俯仰角不能大于最大俯仰角")
        if corr["min_elevation"] < -180 or corr["max_elevation"] > 360:
            raise ValueError("俯仰角范围应在[-180, 360]之间")

    def generate_packet(self, command1=0x00, command2=0x00, data1=0x00, data2=0x00) -> bytes:
        header = [self.START_BYTE, self.address, command1, command2, data1, data2]
        checksum = sum(header[1:]) % 256
        return bytes(header + [checksum])

    def query_angle(self, query_cmd: int) -> int:
        packet = self.generate_packet(command2=query_cmd)

        # 清空接收缓冲区（最多清空 3 次，避免 busy-loop）
        for _ in range(3):
            if not self.hw.recv(1024, timeout=0.1):
                break

        # 发送指令
        if not self.hw.send(packet):
            return None

        # 循环读取直到获取有效响应
        max_retries = 3
        for _ in range(max_retries):
            response = self.hw.recv(7, timeout=1.0)

            # 跳过空响应和回显包
            if not response or response == packet:
                continue

            # 验证响应有效性
            if len(response) == 7 and self._validate_response(response):
                raw_value = (response[4] << 8) | response[5]
                return self._apply_angle_correction(raw_value, query_cmd)

        return None

    def set_angle(self, angle: float, set_cmd: int) -> bool:
        angle_handlers = {
            self.CMD_SET_ELEVATION: self._handle_elevation,
            self.CMD_SET_AZIMUTH: self._handle_azimuth
        }
        handler = angle_handlers.get(set_cmd)
        return handler(angle) if handler else False

    def _handle_elevation(self, angle: float) -> bool:
        config = self.config["angle_correction"]
        abs_min = abs(config["min_elevation"])

        # 计算调整后的角度
        if angle >= abs_min:
            adjusted = angle - abs_min
        else:
            adjusted = 360 + config["min_elevation"] + angle
        adjusted %= 360  # 规范化到 0-360
        return self._send_angle_command(adjusted, self.CMD_SET_ELEVATION)

    def _handle_azimuth(self, angle: float) -> bool:
        if angle < 0:
            return False
        angle %= 360
        return self._send_angle_command(angle, self.CMD_SET_AZIMUTH)

    def _send_angle_command(self, angle: float, command: int) -> bool:
        value = int(angle * 100)
        data1 = (value >> 8) & 0xFF
        data2 = value & 0xFF
        packet = self.generate_packet(command2=command, data1=data1, data2=data2)
        return self.hw.send(packet)

    def _validate_response(self, response: bytes) -> bool:
        """验证响应校验和"""
        expected_checksum = sum(response[1:-1]) % 256
        actual_checksum = response[-1]
        return expected_checksum == actual_checksum

    def _apply_angle_correction(self, raw_value: int, cmd_type: int) -> int:
        """统一处理角度修正逻辑"""
        corrected = raw_value / 100.0
        config = self.config["angle_correction"]
        abs_min = abs(config["min_elevation"])

        if cmd_type == self.CMD_QUERY_ELEVATION:
            # 俯仰角：加上最小角度绝对值
            adjusted = corrected + abs_min
            adjusted %= 360
            return int(adjusted * 100)

        elif cmd_type == self.CMD_QUERY_AZIMUTH:
            # 方位角：加上偏移和初始角度
            corrected += config["azimuth_offset"] + config["initial_azimuth"]
            corrected %= 360
            return int(corrected * 100)

        return raw_value


def parse_gs232b_command(data: bytes) -> str:
    """解析 GS-232B 命令"""
    return data.decode(errors='ignore').strip()
