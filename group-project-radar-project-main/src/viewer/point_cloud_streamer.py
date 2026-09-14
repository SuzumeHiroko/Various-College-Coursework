"""
TCP streaming "viewer" — same interface as the other viewers but renders
nothing locally.  Instead it listens for one TCP client and streams raw
point cloud frames to it.

Drop-in compatible with all other viewers:
  show() / update(frame) / close() / set_limits() / set_label_mode() / stats()

Wire protocol (little-endian):
  Header — 28 bytes:
    2s  magic       b'RC'
    H   n_points    uint16
    f   xlim        float32
    f   ylim        float32
    f   zlim        float32
    I   frame_num   uint32
    d   timestamp   float64
  Payload — n_points * 12 bytes:
    [x float32, y float32, z float32] * n_points
"""

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MAGIC = b"RC"
HEADER_FMT = "<2sHfffId"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 28 bytes
DEFAULT_PORT = 9999


@dataclass(frozen=True)
class ViewerStats:
    points: int
    fps: float


class PointCloudStreamer:
    """
    Listens on a TCP port and streams point cloud frames to one connected
    client at a time.  Runs an accept loop in a daemon thread so the radar
    main loop is never blocked waiting for a connection.

    If no client is connected, update() returns immediately (no data lost
    on the radar side — the client just misses those frames).
    If the client falls behind (send times out), it is dropped and the
    streamer waits for the next connection.
    """

    __slots__ = (
        "_refresh_hz",
        "_xlim",
        "_ylim",
        "_zlim",
        "_max_points",
        "_port",
        "_send_timeout",
        "_server_sock",
        "_conn",
        "_conn_lock",
        "_running",
        "_accept_thread",
        "_last_send",
        "_last_fps_t",
        "_frames_since_fps",
        "_fps",
        "_last_n_points",
    )

    def __init__(
        self,
        refresh_hz: float = 10.0,
        xlim: float = 3.0,
        ylim: float = 6.0,
        *,
        zlim: float = 3.0,
        max_points: int = 2000,
        port: int = DEFAULT_PORT,
        send_timeout: float = 2.0,
        # unused kwargs accepted for interface parity with the display viewers
        **_kwargs: Any,
    ):
        self._refresh_hz = float(refresh_hz)
        self._xlim = float(xlim)
        self._ylim = float(ylim)
        self._zlim = float(zlim)
        self._max_points = int(max_points)
        self._port = int(port)
        self._send_timeout = float(send_timeout)

        self._server_sock: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None
        self._conn_lock = threading.Lock()
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None

        self._last_send = 0.0
        self._last_fps_t = time.time()
        self._frames_since_fps = 0
        self._fps = 0.0
        self._last_n_points = 0

    # ── Public API ──────────────────────────────────────────────────────────

    def show(self) -> None:
        """Bind the server socket and start the accept thread."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("", self._port))
        self._server_sock.listen(1)
        self._running = True
        self._accept_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="streamer-accept"
        )
        self._accept_thread.start()
        logger.info("PointCloudStreamer listening on port %d", self._port)

    def close(self) -> None:
        self._running = False
        with self._conn_lock:
            if self._conn:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass

    def set_limits(
        self,
        *,
        xlim: Optional[float] = None,
        ylim: Optional[float] = None,
        zlim: Optional[float] = None,
    ) -> None:
        if xlim is not None:
            self._xlim = float(xlim)
        if ylim is not None:
            self._ylim = float(ylim)
        if zlim is not None:
            self._zlim = float(zlim)

    def set_label_mode(self, *, enabled: bool, max_labels: Optional[int] = None) -> None:
        pass  # not applicable

    def stats(self) -> ViewerStats:
        return ViewerStats(points=self._last_n_points, fps=float(self._fps))

    def update(self, frame: Any) -> None:
        now = time.time()

        # Rate-limit transmissions the same way the display viewers rate-limit renders
        if self._refresh_hz > 0.0 and (now - self._last_send) < (1.0 / self._refresh_hz):
            return

        pts = getattr(frame, "point_cloud", None) or []
        xyz = self._extract_xyz(pts)
        self._last_n_points = len(xyz)

        data = self._encode(frame, xyz)

        with self._conn_lock:
            conn = self._conn

        if conn is None:
            return

        try:
            conn.sendall(data)
        except OSError:
            logger.warning("Streamer: client disconnected")
            with self._conn_lock:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None
            return

        self._last_send = now
        self._tick_fps(now)

    # ── Internal ────────────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        assert self._server_sock is not None
        self._server_sock.settimeout(1.0)
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.settimeout(self._send_timeout)
            logger.info("Streamer: client connected from %s", addr)

            with self._conn_lock:
                if self._conn:
                    try:
                        self._conn.close()
                    except OSError:
                        pass
                self._conn = conn

    def _encode(self, frame: Any, xyz: List[Tuple[float, float, float]]) -> bytes:
        n = len(xyz)
        fn = 0
        ts = 0.0
        try:
            fn = int(getattr(frame, "frame_number", 0) or 0)
        except Exception:
            pass
        try:
            ts = float(getattr(frame, "timestamp", 0.0) or 0.0)
        except Exception:
            pass

        header = struct.pack(
            HEADER_FMT,
            MAGIC,
            min(n, 65535),
            self._xlim,
            self._ylim,
            self._zlim,
            fn,
            ts,
        )

        if n > 0:
            arr = np.array(xyz, dtype=np.float32)
            return header + arr.tobytes()
        return header

    def _extract_xyz(self, pts: Any) -> List[Tuple[float, float, float]]:
        # Fast path for numpy arrays (e.g. if point_cloud is already Nx3)
        if isinstance(pts, np.ndarray) and pts.ndim == 2 and pts.shape[1] >= 3:
            return [(float(p[0]), float(p[1]), float(p[2])) for p in pts[: self._max_points]]

        out: List[Tuple[float, float, float]] = []
        if not isinstance(pts, (Sequence, np.ndarray)):
            return out
        for p in pts:
            if len(out) >= self._max_points:
                break
            if not isinstance(p, (Sequence, np.ndarray)) or len(p) < 3:
                continue
            try:
                out.append((float(p[0]), float(p[1]), float(p[2])))
            except Exception:
                pass
        return out

    def _tick_fps(self, now: float) -> None:
        self._frames_since_fps += 1
        dt = now - self._last_fps_t
        if dt >= 1.0:
            self._fps = self._frames_since_fps / dt
            self._frames_since_fps = 0
            self._last_fps_t = now
