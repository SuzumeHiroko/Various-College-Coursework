import json
import threading
from typing import Any, List, Optional


def get_rpi_serial_number() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return "unknown"


class PacketConstructor:
    __slots__ = ("_serial_no", "_boot_frame_counter", "_lock")

    def __init__(self, serial_no: Optional[str] = None):
        self._serial_no = serial_no or get_rpi_serial_number()
        self._boot_frame_counter = 0
        self._lock = threading.Lock()

    def _next_boot_frame_counter(self) -> int:
        with self._lock:
            self._boot_frame_counter += 1
            return self._boot_frame_counter

    @staticmethod
    def _compute_dimensions(point_cloud: List[List[float]]) -> List[float]:
        if not point_cloud:
            return []

        xs = [p[0] for p in point_cloud]
        ys = [p[1] for p in point_cloud]
        zs = [p[2] for p in point_cloud]

        return [
            float(max(xs) - min(xs)),
            float(max(ys) - min(ys)),
            float(max(zs) - min(zs)),
        ]

    def format_packet(self, frame: Any) -> dict:
        return {
            "timestamp": float(frame.timestamp),
            "serial_no": self._serial_no,
            "point_cloud": frame.point_cloud,
            "dimensions": self._compute_dimensions(frame.point_cloud),
            "boot_frame_counter": int(self._next_boot_frame_counter()),
            "radar_frame_number": int(frame.frame_number),
        }

    def format_packet_json(self, frame: Any) -> str:
        return json.dumps(self.format_packet(frame), separators=(",", ":"))
