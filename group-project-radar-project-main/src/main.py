"""
Radar data capture — reads from IWR6843AOP and streams point cloud frames
to a remote viewer via TCP (PointCloudStreamer, default port 9999).

Connect from your PC with:
    python src/viewer/client/radar_client.py --host radarnode1.local

Defaults are loaded from config.yaml at the project root.
Any argument provided on the CLI overrides the config file value.

Usage:
    python src/main.py
    python src/main.py --data-port COM5
    python src/main.py --data-port /dev/ttyUSB1 --config-port /dev/ttyUSB0
    python src/main.py --stream-port 9999
"""

import argparse
import logging
import time

import config as cfg_module
from radar import RadarController, POLL_RATE_SLEEP_SECONDS
from viewer import PointCloudStreamer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    # Load config.yaml for defaults; fall back gracefully if missing.
    try:
        cfg = cfg_module.load()
        radar_defaults = cfg.radar
        log_defaults = cfg.logging
    except FileNotFoundError:
        logger.warning("config.yaml not found — falling back to CLI-only mode")
        radar_defaults = None
        log_defaults = None

    ap = argparse.ArgumentParser(description="Radar capture + TCP point cloud streamer")

    ap.add_argument(
        "--data-port",
        default=radar_defaults.data_port if radar_defaults else None,
        help="Data UART (e.g. COM3 or /dev/ttyUSB1). Auto-detected from /dev/ttyUSB* if omitted.",
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
    ap.add_argument("--xlim", type=float, default=3.0, help="Half-width of scene in meters")
    ap.add_argument("--ylim", type=float, default=6.0, help="Depth of scene in meters")
    ap.add_argument("--zlim", type=float, default=3.0, help="Half-height of scene in meters")
    ap.add_argument("--refresh-hz", type=float, default=10.0, help="Stream transmit rate")
    ap.add_argument("--stream-port", type=int, default=9999, help="TCP port to listen on")

    return ap.parse_args()


def main():
    args = parse_args()

    radar = RadarController(
        data_port=args.data_port,
        config_port=args.config_port,
        cfg_file=args.cfg_file,
        data_baud=args.data_baud,
    )

    viewer = PointCloudStreamer(
        refresh_hz=args.refresh_hz,
        xlim=args.xlim,
        ylim=args.ylim,
        zlim=args.zlim,
        port=args.stream_port,
    )
    viewer.show()

    logger.info(
        "Starting radar on %s (logs -> %s) ...",
        args.data_port or "auto-detected /dev/ttyUSB*",
        args.log_dir,
    )
    radar.run()

    try:
        while True:
            if radar.is_available():
                frame = radar.read()
                viewer.update(frame)
            else:
                if not radar.is_healthy():
                    logger.warning("Radar not healthy — no fresh data")
                time.sleep(POLL_RATE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        radar.stop()
        viewer.close()


if __name__ == "__main__":
    main()
