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
        # 验证角度范围
        if set_cmd == 0x4B:  # 方位角
            if not (0 <= angle <= 360):
                return False
        elif set_cmd == 0x4D:  # 俯仰角
            if not (0 <= angle <= 90):
                return False

        value = int(angle * 100)
        data1 = (value >> 8) & 0xFF
        data2 = value & 0xFF
        packet = self.generate_packet(command2=set_cmd, data1=data1, data2=data2)
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
        """应用角度修正"""
        corrected = raw_value / 100.0
        config = self.config["angle_correction"]

        if cmd_type == 0x51:  # 方位角
            corrected += config["azimuth_offset"] + config["initial_azimuth"]
            corrected %= 360  # 确保在0-360度范围内
            return int(corrected * 100)

        elif cmd_type == 0x53:  # 俯仰角
            min_ele = config["min_elevation"]
            max_ele = config["max_elevation"]

            if corrected > max_ele:
                # 当超过最大值时：计算值 = 原始值 + 最小角度绝对值
                adjusted = corrected + abs(min_ele)
                adjusted %= 360  # 超过360度取余
                return int(adjusted * 100)

            return int(corrected * 100)

        return raw_value


class GS232BProtocol:
    @staticmethod
    def parse_command(data: bytes) -> str:
        return data.decode(errors='ignore').strip()