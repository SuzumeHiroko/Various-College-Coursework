"""
test_sub.py — subscribes to your AWS IoT Core topic and prints every
frame that arrives. Run this in one terminal while upload.py runs
in another.

Usage:
    python test_sub.py --endpoint <your>.iot.<region>.amazonaws.com --ca certs/AmazonRootCA1.pem --cert certs/device-cert.pem --key certs/device-private.key
"""

import argparse
import json
import ssl

import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0 or str(reason_code) == "Success":
        print(f"Connected. Listening on topic '{userdata['topic']}' ...\n")
        client.subscribe(userdata["topic"], qos=1)
    else:
        print(f"ERROR: Connection failed ({reason_code})")


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    print(f"Disconnected rc={reason_code}")


def on_message(client, userdata, msg):
    try:
        p = json.loads(msg.payload)
    except json.JSONDecodeError:
        print(f"BAD JSON: {msg.payload}")
        return

    point_cloud = p.get("point_cloud", [])
    dimensions  = p.get("dimensions", [])

    print(
        f"frame  "
        f"sensor={p.get('serial_no')}  "
        f"radar_frame_no={p.get('radar_frame_number')}  "
        f"boot_frame={p.get('boot_frame_counter')}  "
        f"ts={p.get('timestamp', 0):.3f}  "
        f"points={len(point_cloud)}  "
        f"dims={[round(d, 3) for d in dimensions]}"
    )

    # Print first 3 points if any
    for pt in point_cloud[:3]:
        print(f"  x={pt[0]:+.3f}  y={pt[1]:+.3f}  z={pt[2]:+.3f}")
    if len(point_cloud) > 3:
        print(f"  ... and {len(point_cloud) - 3} more")


def main():
    ap = argparse.ArgumentParser(description="AWS IoT Core MQTT subscriber test")
    ap.add_argument("--endpoint",  required=True)
    ap.add_argument("--topic",     default="radar/frames")
    ap.add_argument("--ca",        required=True)
    ap.add_argument("--cert",      required=True)
    ap.add_argument("--key",       required=True)
    ap.add_argument("--client-id", default="test-subscriber")
    args = ap.parse_args()

    userdata = {"topic": args.topic}

    client = mqtt.Client(
        client_id=args.client_id,
        userdata=userdata,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.tls_set(
        ca_certs=args.ca,
        certfile=args.cert,
        keyfile=args.key,
        tls_version=ssl.PROTOCOL_TLSv1_2,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    print(f"Connecting to {args.endpoint}:8883 ...")
    client.connect(args.endpoint, 8883, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()