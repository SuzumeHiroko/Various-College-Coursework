"""
packet/upload.py — Radar → AWS IoT Core upload pipeline.

Reads from IWR6843AOP and uploads point cloud frames to AWS IoT Core
via MQTT. Runs independently of the TCP viewer (main.py).

Radar defaults are still loaded from config.yaml if present.
AWS credentials are always passed via CLI flags.

Usage:
    python -m packet.upload \
        --endpoint <your>.iot.<region>.amazonaws.com \
        --ca certs/AmazonRootCA1.pem \
        --cert certs/device-cert.pem \
        --key certs/device-private.key

    # Override radar port too:
    python -m packet.upload \
        --data-port /dev/ttyUSB1 --config-port /dev/ttyUSB0 \
        --endpoint <your>.iot.<region>.amazonaws.com \
        --ca certs/AmazonRootCA1.pem \
        --cert certs/device-cert.pem \
        --key certs/device-private.key
"""

import argparse
import logging
import time

import config as cfg_module
from radar import RadarController, POLL_RATE_SLEEP_SECONDS
from packet.packet_constructor import PacketConstructor
from packet.aws_uploader import AwsUploader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HEALTH_WARN_INTERVAL = 5.0  # seconds between repeated health warnings
LOG_EVERY_N_FRAMES   = 50   # set to 0 to disable periodic stats logs


def parse_args():
    try:
        cfg = cfg_module.load()
        radar_defaults = cfg.radar
    except FileNotFoundError:
        logger.warning("config.yaml not found — radar args required via CLI")
        radar_defaults = None

    ap = argparse.ArgumentParser(description="Radar → AWS IoT Core uploader")

    ap.add_argument(
        "--data-port",
        default=radar_defaults.data_port if radar_defaults else None,
        required=(radar_defaults is None),
        help="Data UART (e.g. COM3 or /dev/ttyUSB1)",
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


    ap.add_argument("--endpoint",  required=True,          help="AWS IoT Core endpoint hostname")
    ap.add_argument("--topic",     default="radar/frames", help="MQTT topic to publish on")
    ap.add_argument("--ca",        required=True,          help="Path to AmazonRootCA1.pem")
    ap.add_argument("--cert",      required=True,          help="Path to device certificate .pem")
    ap.add_argument("--key",       required=True,          help="Path to device private key")
    ap.add_argument("--client-id", default=None,           help="MQTT client ID (default: Pi CPU serial number)")
    ap.add_argument("--sensor-id", default=None,           help="Override sensor ID in packet (default: Pi CPU serial number)")

    return ap.parse_args()


def main():
    args = parse_args()

    radar = RadarController(
        data_port=args.data_port,
        config_port=args.config_port,
        cfg_file=args.cfg_file,
        data_baud=args.data_baud,
    )

    constructor = PacketConstructor(serial_no=args.sensor_id)

    uploader = AwsUploader(
        endpoint=args.endpoint,
        topic=args.topic,
        ca_path=args.ca,
        cert_path=args.cert,
        key_path=args.key,
        client_id=args.client_id,
        queue_size=200,
    )

    logger.info("Connecting to AWS IoT Core (%s) ...", args.endpoint)
    uploader.start()

    for _ in range(40):
        if uploader.is_connected():
            break
        time.sleep(0.25)
    else:
        logger.warning("MQTT not yet connected — will keep retrying in background")

    logger.info("Starting radar on %s ...", args.data_port)
    radar.run()
    logger.info("Uploading to topic: %s", args.topic)

    frame_count      = 0
    last_health_warn = 0.0

    try:
        while True:
            if radar.is_available():
                frame = radar.read()
                if frame is not None:
                    uploader.enqueue(constructor.format_packet(frame))
                    frame_count += 1

                    if LOG_EVERY_N_FRAMES and frame_count % LOG_EVERY_N_FRAMES == 0:
                        logger.info(
                            "frames=%d  points=%d  dropped=%d  connected=%s",
                            frame_count,
                            len(frame.point_cloud),
                            uploader.dropped_count,
                            uploader.is_connected(),
                        )
            else:
                if not radar.is_healthy():
                    now = time.time()
                    if now - last_health_warn > HEALTH_WARN_INTERVAL:
                        logger.warning(
                            "Radar not healthy — no fresh data (sync_losses=%d)",
                            radar.sync_loss_count,
                        )
                        last_health_warn = now
                time.sleep(POLL_RATE_SLEEP_SECONDS)

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        radar.stop()
        uploader.stop()
        logger.info(
            "Done. frames=%d  dropped=%d  sync_losses=%d",
            frame_count,
            uploader.dropped_count,
            radar.sync_loss_count,
        )


if __name__ == "__main__":
    main()