"""
Raw serial dump for IWR6843AOP data port.

Sends a .cfg file over the config port then streams raw bytes from the data
port to stdout — useful for verifying the radar is alive and the magic word
appears before wiring up the full TLV parser.

Usage:
    python tests/test_raw_serial.py \
        --config-port COM3 --data-port COM4 \
        --cfg-file src/radar/profile_3d.cfg

    # Linux / RPi
    python tests/test_raw_serial.py \
        --config-port /dev/ttyUSB0 --data-port /dev/ttyUSB1 \
        --cfg-file src/radar/profile_3d.cfg

Output format per line:
    [t=<elapsed_s>] +<offset_hex>  <hex bytes>  |<ascii>|
"""

import argparse
import sys
import time
import serial

# Same constants as radar_interface.py
MAGIC_WORD = b"\x02\x01\x04\x03\x06\x05\x08\x07"
CONFIG_BAUD = 115200
DATA_BAUD = 921600
SENSOR_START_DELAY = 0.5  # seconds — mirrors radar_interface.py
CFG_LINE_DELAY = 0.03  # seconds between config lines
READ_CHUNK = 256  # bytes per data-port read


# ---------------------------------------------------------------------------
# Config sender  (mirrors RadarController._send_config)
# ---------------------------------------------------------------------------


def send_config(port: serial.Serial, cfg_path: str, delay: float = CFG_LINE_DELAY) -> None:
    """Send a .cfg file line-by-line to the radar config port."""
    sent = 0
    with open(cfg_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            port.write((line + "\n").encode("ascii"))
            print(f"  cfg >> {line}", flush=True)
            time.sleep(delay)
            sent += 1
    print(f"[cfg] Sent {sent} lines from {cfg_path}", flush=True)


# ---------------------------------------------------------------------------
# Hex dump helper
# ---------------------------------------------------------------------------


def hex_dump_line(data: bytes, offset: int, t0: float) -> str:
    """Format one row of hex dump output."""
    elapsed = time.time() - t0
    hex_part = " ".join(f"{b:02x}" for b in data)
    # Printable ASCII, dots for non-printable
    ascii_part = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in data)
    return f"[t={elapsed:8.3f}] +{offset:08x}  {hex_part:<48}  |{ascii_part}|"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Configure IWR6843AOP and dump raw data-port bytes.")
    ap.add_argument("--data-port", required=True, help="Data UART  (e.g. /dev/ttyUSB1 or COM4)")
    ap.add_argument("--config-port", default=None, help="Config UART (e.g. /dev/ttyUSB0 or COM3)")
    ap.add_argument("--cfg-file", default=None, help=".cfg file to send at startup")
    ap.add_argument("--data-baud", type=int, default=DATA_BAUD)
    ap.add_argument(
        "--bytes", type=int, default=0, help="Stop after N bytes (0 = run until Ctrl-C)"
    )
    ap.add_argument(
        "--chunk",
        type=int,
        default=READ_CHUNK,
        help=f"Read chunk size in bytes (default {READ_CHUNK})",
    )
    args = ap.parse_args()

    config_serial = None
    data_serial = None
    t0 = time.time()
    total_bytes = 0
    magic_hits = 0

    try:
        # -- Config port -------------------------------------------------------
        if args.config_port:
            print(f"[cfg] Opening config port {args.config_port} @ {CONFIG_BAUD}", flush=True)
            config_serial = serial.Serial(
                port=args.config_port,
                baudrate=CONFIG_BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
            )

        if args.cfg_file and config_serial:
            send_config(config_serial, args.cfg_file)
            print(f"[cfg] Waiting {SENSOR_START_DELAY}s for sensorStart ...", flush=True)
            time.sleep(SENSOR_START_DELAY)
        elif args.cfg_file and not config_serial:
            print(
                "[cfg] WARNING: --cfg-file given but no --config-port; skipping config", flush=True
            )

        # -- Data port ---------------------------------------------------------
        print(f"[data] Opening data port {args.data_port} @ {args.data_baud}", flush=True)
        data_serial = serial.Serial(
            port=args.data_port,
            baudrate=args.data_baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
        )

        print(
            f"[data] Streaming raw bytes (chunk={args.chunk}). Press Ctrl-C to stop.\n", flush=True
        )

        t0 = time.time()
        search_buf = b""  # sliding window for magic-word detection

        while True:
            chunk = data_serial.read(args.chunk)
            if not chunk:
                # Serial timeout — radar may still be starting up
                continue

            # -- Hex dump ------------------------------------------------------
            row_start = 0
            while row_start < len(chunk):
                row = chunk[row_start : row_start + 16]
                print(hex_dump_line(row, total_bytes + row_start, t0))
                row_start += 16

            # -- Magic-word annotation -----------------------------------------
            search_buf = (search_buf + chunk)[-(len(MAGIC_WORD) - 1 + len(chunk)) :]
            combined = search_buf
            pos = 0
            while True:
                idx = combined.find(MAGIC_WORD, pos)
                if idx == -1:
                    break
                abs_offset = total_bytes - (len(combined) - idx - len(chunk))
                print(
                    f"  *** MAGIC WORD @ absolute byte +{abs_offset} "
                    f"(hit #{magic_hits + 1}) ***",
                    flush=True,
                )
                magic_hits += 1
                pos = idx + 1

            total_bytes += len(chunk)
            sys.stdout.flush()

            if args.bytes and total_bytes >= args.bytes:
                print(f"\n[data] Reached --bytes limit ({args.bytes}). Stopping.", flush=True)
                break

    except KeyboardInterrupt:
        print("\n[data] Stopped by user.", flush=True)

    finally:
        elapsed = time.time() - t0
        print(
            f"\n[summary] {total_bytes} bytes in {elapsed:.1f}s  |  "
            f"magic-word hits: {magic_hits}",
            flush=True,
        )
        if data_serial and data_serial.is_open:
            data_serial.close()
        if config_serial and config_serial.is_open:
            config_serial.close()


if __name__ == "__main__":
    main()
