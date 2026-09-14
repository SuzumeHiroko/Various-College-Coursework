"""
test_upload.py — tests the full packet pipeline without radar hardware.

Fakes RadarFrame objects and sends them through PacketConstructor →
AwsUploader → AWS IoT Core. Run alongside test_sub.py to verify
frames are arriving.

Usage:
    python test_upload.py \
        --endpoint <your>.iot.<region>.amazonaws.com \
        --ca certs/AmazonRootCA1.pem \
        --cert certs/device-cert.pem \
        --key certs/device-private.key
"""

import argparse
import time

from packet.packet_constructor import PacketConstructor
from packet.aws_uploader import AwsUploader
from radar.radar_interface import RadarFrame


def make_fake_frame(i: int) -> RadarFrame:
    return RadarFrame(
        timestamp=time.time(),
        point_cloud=[[0.1 * i, 0.2 * i, 0.3], [0.5, 0.1 * i, 0.0]],
        velocities=[0.1, -0.2],
        snr=[12.0, 9.5],
        noise=[1.0, 1.2],
        frame_number=i,
    )


def main():
    ap = argparse.ArgumentParser(description="Fake radar → AWS IoT Core upload test")
    ap.add_argument("--endpoint",   required=True)
    ap.add_argument("--topic",      default="radar/frames")
    ap.add_argument("--ca",         required=True)
    ap.add_argument("--cert",       required=True)
    ap.add_argument("--key",        required=True)
    ap.add_argument("--sensor-id",  default="test_sensor_001")
    ap.add_argument("--frames",     type=int, default=10, help="Number of fake frames to send")
    args = ap.parse_args()

    constructor = PacketConstructor(serial_no=args.sensor_id)

    uploader = AwsUploader(
        endpoint=args.endpoint,
        topic=args.topic,
        ca_path=args.ca,
        cert_path=args.cert,
        key_path=args.key,
    )

    print(f"Connecting to {args.endpoint} ...")
    uploader.start()

    for _ in range(40):
        if uploader.is_connected():
            break
        time.sleep(0.25)

    if not uploader.is_connected():
        print(f"ERROR: Failed to connect — {uploader.last_error}")
        uploader.stop()
        raise SystemExit(1)

    print(f"Connected. Sending {args.frames} fake frames to topic '{args.topic}' ...")

    for i in range(args.frames):
        frame = make_fake_frame(i)
        packet = constructor.format_packet(frame)
        uploader.enqueue(packet)
        print(f"  frame {i:>3}  points={len(frame.point_cloud)}  dropped={uploader.dropped_count}")
        time.sleep(0.1)

    print("Flushing queue ...")
    time.sleep(2.0)

    uploader.stop()
    print(f"Done.  dropped={uploader.dropped_count}  last_error={uploader.last_error}")


if __name__ == "__main__":
    main()