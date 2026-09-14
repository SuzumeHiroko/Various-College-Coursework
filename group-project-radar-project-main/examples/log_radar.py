"""
Log 20 seconds of radar data to a JSONL file.

Timestamps written to the log are anchored to 2005-06-12 00:00:00 UTC
regardless of the real wall-clock time.  Elapsed seconds flow forward from
that anchor so relative timing between frames is preserved.

Defaults are loaded from config.yaml at the project root.
Any argument provided on the CLI overrides the config file value.

Usage:
    python examples/log_radar.py
    python examples/log_radar.py --data-port COM5
    python examples/log_radar.py --log-dir my_logs
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from src/ when run directly from the project root or examples/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import config as cfg_module
from logger import DataLogger
from radar import RadarController, POLL_RATE_SLEEP_SECONDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RECORD_DURATION = 20.0  # seconds

# Virtual time anchor: 2005-06-12 00:00:00 UTC
_ANCHOR_EPOCH: float = datetime(2005, 6, 12, 0, 0, 0, tzinfo=timezone.utc).timestamp()


def virtual_timestamp(run_start: float) -> float:
    """Return a virtual epoch timestamp anchored to 2005-06-12 00:00:00 UTC."""
    return _ANCHOR_EPOCH + (time.time() - run_start)


def parse_args():
    try:
        cfg = cfg_module.load()
        radar_defaults = cfg.radar
        log_defaults = cfg.logging
    except FileNotFoundError:
        logger.warning("config.yaml not found — falling back to CLI-only mode")
        radar_defaults = None
        log_defaults = None

    ap = argparse.ArgumentParser(description="Log 20 s of radar data to JSONL")

    ap.add_argument(
        "--data-port",
        default=radar_defaults.data_port if radar_defaults else None,
        required=(radar_defaults is None),
        help="Data UART (e.g. COM5 or /dev/ttyUSB1)",
    )
    ap.add_argument(
        "--config-port",
        default=radar_defaults.config_port if radar_defaults else None,
        help="Config UART (e.g. COM4 or /dev/ttyUSB0)",
    )
    ap.add_argument(
        "--cfg-file",
        default=radar_defaults.cfg_file if radar_defaults else None,
        help=".cfg file to send at startup",
    )
    ap.add_argument(
        "--data-baud",
        type=int,
        default=radar_defaults.data_baud if radar_defaults else 921600,
    )
    ap.add_argument(
        "--log-dir",
        default=log_defaults.output_dir if log_defaults else "logs",
        help="Directory for log output",
    )

    return ap.parse_args()


def main():
    time.sleep(2)
    print("starting")
    args = parse_args()

    log_path = Path(args.log_dir) / f"angle3.jsonl" #f"radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    radar = RadarController(
        data_port=args.data_port,
        config_port=args.config_port,
        cfg_file=args.cfg_file,
        data_baud=args.data_baud,
    )

    data_logger = DataLogger()
    data_logger.create(str(log_path))

    logger.info("Recording %gs to %s (virtual time starts 2005-06-12 00:00:00 UTC) ...",
                RECORD_DURATION, log_path)
    radar.run()

    run_start = time.time()
    frames_logged = 0

    try:
        while (time.time() - run_start) < RECORD_DURATION:
            if radar.is_available():
                frame = radar.read()
                pts = getattr(frame, "point_cloud", []) or []
                data_logger.write({
                    "timestamp": virtual_timestamp(run_start),
                    "frame_number": getattr(frame, "frame_number", None),
                    "point_cloud": [list(p) for p in pts],
                })
                frames_logged += 1
            else:
                if not radar.is_healthy():
                    logger.warning("Radar not healthy — no fresh data")
                time.sleep(POLL_RATE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        radar.stop()
        data_logger.close()
        elapsed = time.time() - run_start
        logger.info("Done — %d frames logged in %.1fs -> %s", frames_logged, elapsed, log_path)


if __name__ == "__main__":
    main()
