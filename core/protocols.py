# core/protocols.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
class PelcoDProtocol:
    START_BYTE = 0xFF
    DEFAULT_ADDRESS = 0x01

    def __init__(self, hardware):
        self.hw = hardware
        self.address = self.DEFAULT_ADDRESS

    def generate_packet(self, command1=0x00, command2=0x00, data1=0x00, data2=0x00) -> bytes:
        header = [self.START_BYTE, self.address, command1, command2, data1, data2]
        checksum = sum(header[1:]) % 256
        return bytes(header + [checksum])

    def query_angle(self, query_cmd: int) -> int:
        packet = self.generate_packet(command2=query_cmd)

        # 清空缓冲区
        while self.hw.recv(1024, timeout=0.1):
            pass

        if not self.hw.send(packet):
            return None

        response = self.hw.recv(7, timeout=3.0)
        if not response:
            return None

        if len(response) != 7:
            return None

        if not self._validate_response(response):
            return None

        return (response[4] << 8) | response[5]

    def set_angle(self, angle: float, set_cmd: int) -> bool:
        value = int(angle * 100)
        data1 = (value >> 8) & 0xFF
        data2 = value & 0xFF
        packet = self.generate_packet(command2=set_cmd, data1=data1, data2=data2)
        return self.hw.send(packet)

    def _validate_response(self, response: bytes) -> bool:
        expected_checksum = sum(response[1:-1]) % 256
        actual_checksum = response[-1]
        return expected_checksum == actual_checksum


class GS232BProtocol:
    @staticmethod
    def parse_command(data: bytes) -> str:
        return data.decode(errors='ignore').strip()