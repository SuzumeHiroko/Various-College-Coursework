from pathlib import Path

from .radar_interface import RadarController, RadarFrame, POLL_RATE_SLEEP_SECONDS, detect_radar_ports

DEFAULT_CFG_PATH = Path(__file__).parent / "profile_3d.cfg"

__all__ = ["RadarController", "RadarFrame", "POLL_RATE_SLEEP_SECONDS", "DEFAULT_CFG_PATH", "detect_radar_ports"]
