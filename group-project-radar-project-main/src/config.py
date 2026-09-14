"""
Project configuration loader.

Reads config.yaml from the project root and exposes typed dataclasses.
CLI arguments in main.py override these values when provided.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class RadarConfig:
    data_port: Optional[str]
    config_port: Optional[str]
    cfg_file: Optional[str]
    data_baud: int


@dataclass(frozen=True)
class LoggingConfig:
    output_dir: str


@dataclass(frozen=True)
class AppConfig:
    radar: RadarConfig
    logging: LoggingConfig


def load(path: Optional[Path] = None) -> AppConfig:
    """Load and validate config.yaml. Raises FileNotFoundError if missing."""
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH

    with open(resolved) as f:
        raw = yaml.safe_load(f)

    r = raw.get("radar", {})
    radar = RadarConfig(
        data_port=str(r["data_port"]) if r.get("data_port") else None,
        config_port=str(r["config_port"]) if r.get("config_port") else None,
        cfg_file=str(r["cfg_file"]) if r.get("cfg_file") else None,
        data_baud=int(r.get("data_baud", 921600)),
    )

    lg = raw.get("logging", {})
    logging_cfg = LoggingConfig(
        output_dir=str(lg.get("output_dir", "logs")),
    )

    return AppConfig(radar=radar, logging=logging_cfg)
