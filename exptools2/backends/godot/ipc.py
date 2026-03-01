from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UDPConfig:
    host: str = "127.0.0.1"
    port: int = 5005
    timeout_s: float = 0.1


class UDPChannel:
    def __init__(self, cfg: UDPConfig):
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(cfg.timeout_s)

    def send(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf8")
        self.sock.sendto(data, (self.cfg.host, self.cfg.port))

    def recv(self) -> dict[str, Any] | None:
        try:
            data, _addr = self.sock.recvfrom(1024 * 1024)
        except socket.timeout:
            return None
        return json.loads(data.decode("utf8"))

    def close(self) -> None:
        self.sock.close()
