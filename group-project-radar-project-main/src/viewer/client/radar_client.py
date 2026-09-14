"""
Radar point cloud remote viewer.

Connects to a PointCloudStreamer running on the Pi (default radarnode1.local)
and displays received frames using the OpenCV 3-D perspective viewer.
Automatically reconnects if the connection drops.

Usage:
    python src/viewer/client/radar_client.py
    python src/viewer/client/radar_client.py --host radarnode1.local
    python src/viewer/client/radar_client.py --host 192.168.1.50 --port 9999

Wire protocol — see point_cloud_streamer.py for full spec.
"""

import argparse
import logging
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

# Allow running directly from any working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from viewer.point_cloud_viewer_cv import PointCloudViewerCV  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Protocol constants (must match point_cloud_streamer.py) ─────────────────
MAGIC = b"RC"
HEADER_FMT = "<2sHfffId"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 28 bytes


@dataclass
class RemoteFrame:
    """Minimal frame object accepted by PointCloudViewerCV.update()."""

    point_cloud: List[List[float]]
    frame_number: int = 0
    timestamp: float = 0.0


# ── Network helpers ──────────────────────────────────────────────────────────


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from sock, raising ConnectionError on EOF."""
    buf = bytearray(n)
    view = memoryview(buf)
    pos = 0
    while pos < n:
        received = sock.recv_into(view[pos:], n - pos)
        if not received:
            raise ConnectionError("server closed the connection")
        pos += received
    return bytes(buf)


def receive_frame(sock: socket.socket) -> Tuple[RemoteFrame, Tuple[float, float, float]]:
    """
    Read one frame from the socket.
    Returns (RemoteFrame, (xlim, ylim, zlim)).
    Raises ConnectionError / ValueError on bad data.
    """
    raw = recv_exact(sock, HEADER_SIZE)
    magic, n_pts, xlim, ylim, zlim, frame_num, timestamp = struct.unpack(HEADER_FMT, raw)

    if magic != MAGIC:
        raise ValueError(f"bad magic bytes: {magic!r}")

    points: List[List[float]] = []
    if n_pts > 0:
        payload = recv_exact(sock, n_pts * 12)
        arr = np.frombuffer(payload, dtype=np.float32).reshape(n_pts, 3)
        points = arr.tolist()

    return (
        RemoteFrame(point_cloud=points, frame_number=frame_num, timestamp=timestamp),
        (xlim, ylim, zlim),
    )


# ── Main ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Radar remote point cloud viewer")
    ap.add_argument(
        "--host",
        default="radarnode1.local",
        help="Streamer hostname or IP (default: radarnode1.local)",
    )
    ap.add_argument("--port", type=int, default=9999, help="Streamer port (default: 9999)")
    ap.add_argument(
        "--xlim",
        type=float,
        default=None,
        help="Override lateral view limit (m) — uses server value if omitted",
    )
    ap.add_argument(
        "--ylim",
        type=float,
        default=None,
        help="Override range view limit (m)   — uses server value if omitted",
    )
    ap.add_argument(
        "--zlim",
        type=float,
        default=None,
        help="Override height view limit (m)  — uses server value if omitted",
    )
    ap.add_argument(
        "--point-radius", type=int, default=3, help="Point radius in pixels (default: 3)"
    )
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument(
        "--retry-delay", type=float, default=2.0, help="Seconds to wait between reconnect attempts"
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    viewer: Optional[PointCloudViewerCV] = None

    while True:
        logger.info("Connecting to %s:%d …", args.host, args.port)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(5.0)
            sock.connect((args.host, args.port))
            sock.settimeout(None)  # switch to blocking for recv_exact
        except (socket.timeout, OSError) as exc:
            logger.warning("Connection failed: %s — retrying in %.0fs", exc, args.retry_delay)
            time.sleep(args.retry_delay)
            continue

        logger.info("Connected to %s:%d", args.host, args.port)

        try:
            while True:
                frame, (srv_xlim, srv_ylim, srv_zlim) = receive_frame(sock)

                # Build the viewer on the first frame so we can use the
                # server's limits unless the user overrode them on the CLI.
                if viewer is None:
                    viewer = PointCloudViewerCV(
                        refresh_hz=0,  # render every frame we receive
                        xlim=args.xlim if args.xlim is not None else srv_xlim,
                        ylim=args.ylim if args.ylim is not None else srv_ylim,
                        zlim=args.zlim if args.zlim is not None else srv_zlim,
                        point_radius=args.point_radius,
                        width=args.width,
                        height=args.height,
                    )
                    viewer.show()
                else:
                    # Update limits if the server changed them and the user
                    # hasn't pinned them via CLI flags.
                    viewer.set_limits(
                        xlim=args.xlim if args.xlim is not None else srv_xlim,
                        ylim=args.ylim if args.ylim is not None else srv_ylim,
                        zlim=args.zlim if args.zlim is not None else srv_zlim,
                    )

                viewer.update(frame)

        except (ConnectionError, OSError, ValueError) as exc:
            logger.warning("Stream error: %s — reconnecting …", exc)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        finally:
            sock.close()

        time.sleep(args.retry_delay)

    if viewer is not None:
        viewer.close()


if __name__ == "__main__":
    main()
