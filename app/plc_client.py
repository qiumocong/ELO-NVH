import socket
import time
from dataclasses import dataclass


class PlcError(RuntimeError):
    pass


@dataclass
class PlcResponse:
    command: str
    success: bool
    message: str
    raw_response: str


class PlcClient:
    def __init__(self, mode: str, host: str, port: int, timeout_sec: float, read_response: bool = True):
        self.mode = mode
        self.host = host
        self.port = port
        self.timeout_sec = timeout_sec
        self.read_response = read_response

    def send_command(self, command: str) -> PlcResponse:
        if not command.strip():
            raise PlcError("PLC command cannot be empty")

        if self.mode == "mock":
            time.sleep(0.1)
            return PlcResponse(command=command, success=True, message="mock sent", raw_response="MOCK_OK")

        if self.mode == "tcp":
            return self._send_tcp_command(command)

        raise PlcError(f"Unsupported PLC mode: {self.mode}")

    def _send_tcp_command(self, command: str) -> PlcResponse:
        payload = command.encode("utf-8")
        raw_response = ""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_sec) as sock:
                sock.sendall(payload)
                if self.read_response:
                    sock.settimeout(self.timeout_sec)
                    raw_response = sock.recv(1024).decode("utf-8", errors="ignore")
        except (socket.timeout, OSError) as exc:
            raise PlcError(f"PLC TCP communication failed: {exc}") from exc

        return PlcResponse(command=command, success=True, message="tcp sent", raw_response=raw_response.strip())

