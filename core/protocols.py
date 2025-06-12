# core/protocols.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
class PelcoDProtocol:
    START_BYTE = 0xFF
    DEFAULT_ADDRESS = 0x01

    def __init__(self, hardware, config):  # 添加 config 参数
        self.hw = hardware
        self.config = config  # 保存配置
        self.address = self.DEFAULT_ADDRESS

    def generate_packet(self, command1=0x00, command2=0x00, data1=0x00, data2=0x00) -> bytes:
        header = [self.START_BYTE, self.address, command1, command2, data1, data2]
        checksum = sum(header[1:]) % 256
        return bytes(header + [checksum])

    def query_angle(self, query_cmd: int) -> int:
        packet = self.generate_packet(command2=query_cmd)

        # 清空接收缓冲区
        while self.hw.recv(1024, timeout=0.1):
            pass

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
            0x4D: self._handle_elevation,
            0x4B: self._handle_azimuth
        }

        handler = angle_handlers.get(set_cmd)
        return handler(angle) if handler else False

    def _handle_elevation(self, angle: float) -> bool:
        config = self.config["angle_correction"]
        abs_min = abs(config["min_elevation"])

        # 计算调整后的角度
        adjusted = angle - abs_min if angle >= abs_min else 360 + config["min_elevation"] + angle
        return self._send_angle_command(adjusted, 0x4D)

    def _handle_azimuth(self, angle: float) -> bool:
        if angle < 0:
            return False
        if angle > 360:
            angle %= 360
        return self._send_angle_command(angle, 0x4B)

    def _send_angle_command(self, angle: float, command: int) -> bool:
        value = int(angle * 100)
        data1 = (value >> 8) & 0xFF
        data2 = value & 0xFF
        packet = self.generate_packet(command2=command, data1=data1, data2=data2)
        return self.hw.send(packet)

    def _validate_response(self, response: bytes) -> bool:
        """验证配置有效性"""
        expected_checksum = sum(response[1:-1]) % 256
        actual_checksum = response[-1]
        # 俯仰角范围验证允许负值
        pelco_corr = self.config["angle_correction"]
        if pelco_corr["min_elevation"] > pelco_corr["max_elevation"]:
            raise ValueError("最小俯仰角不能大于最大俯仰角")
        if pelco_corr["min_elevation"] < -180 or pelco_corr["max_elevation"] > 360:
            raise ValueError("俯仰角范围应在[-180, 360]之间")
        return expected_checksum == actual_checksum

    def _apply_angle_correction(self, raw_value: int, cmd_type: int) -> int:
        """统一处理角度修正逻辑"""
        corrected = raw_value / 100.0
        config = self.config["angle_correction"]
        abs_min = abs(config["min_elevation"])

        # 处理俯仰角查询响应
        if cmd_type == 0x53:
            # 所有查询结果均加上最小角度绝对值
            adjusted = corrected + abs_min
            adjusted %= 360  # 确保在0-360范围内
            return int(adjusted * 100)

        # 处理方位角查询响应
        elif cmd_type == 0x51:
            corrected += config["azimuth_offset"] + config["initial_azimuth"]
            corrected %= 360
            return int(corrected * 100)

        return raw_value


class GS232BProtocol:
    @staticmethod
    def parse_command(data: bytes) -> str:
        return data.decode(errors='ignore').strip()