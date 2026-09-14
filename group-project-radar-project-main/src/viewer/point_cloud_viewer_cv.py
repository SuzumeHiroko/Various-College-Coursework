"""
OpenCV-based 3-D point cloud viewer for radar data.

Renders a single perspective-projected 3-D view on a black background and
displays it fullscreen via OpenCV.  Significantly lighter than the matplotlib
viewers — designed for Pi-class hardware.

Drop-in compatible with PointCloudViewer and PointCloudViewer3D:
  show() / update(frame) / close() / set_limits() / set_label_mode() / stats()

Coordinate system (radar convention):
  x — lateral  (right = +)
  y — range    (forward = +)
  z — height   (up = +)

Points are coloured by range (y) using the TURBO colourmap.
A subtle ground-plane grid is drawn for depth reference.
"""

import math
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class ViewerStats:
    points: int
    fps: float


class PointCloudViewerCV:
    """
    Real-time single-view 3-D perspective point cloud viewer using OpenCV.

    Expected frame interface (same as PointCloudViewer / PointCloudViewer3D):
      - frame.point_cloud: Sequence[Sequence[float]]  — each point [x, y, z]
      - frame.timestamp    (optional): float epoch seconds
      - frame.frame_number (optional): int
    """

    __slots__ = (
        "_refresh_hz",
        "_xlim",
        "_ylim",
        "_zlim",
        "_max_points",
        "_point_radius",
        "_title",
        "_win",
        "_W",
        "_H",
        "_az",
        "_el",
        "_fov",
        "_cam_dist",
        "_color_lut",
        "_last_n_points",
        "_last_redraw",
        "_last_fps_t",
        "_frames_since_fps",
        "_fps",
    )

    _WIN_NAME = "Radar Point Cloud"

    def __init__(
        self,
        refresh_hz: float = 10.0,
        xlim: float = 3.0,
        ylim: float = 6.0,
        *,
        zlim: float = 3.0,
        max_points: int = 2000,
        point_radius: int = 3,
        title: str = "Radar Point Cloud — 3D",
        width: int = 1280,
        height: int = 720,
        azimuth: float = 30.0,  # yaw around world-Z, degrees
        elevation: float = 25.0,  # camera tilt above horizon, degrees
        fov: float = 60.0,  # vertical field-of-view, degrees
    ):
        self._refresh_hz = float(refresh_hz)
        self._xlim = float(xlim)
        self._ylim = float(ylim)
        self._zlim = float(zlim)
        self._max_points = int(max_points)
        self._point_radius = int(point_radius)
        self._title = str(title)
        self._win = self._WIN_NAME
        self._W = int(width)
        self._H = int(height)
        self._az = math.radians(float(azimuth))
        self._el = math.radians(float(elevation))
        self._fov = math.radians(float(fov))
        self._cam_dist = max(xlim * 2.0, ylim * 1.2, zlim * 2.0)

        # Pre-build a 256-entry BGR colour LUT from the TURBO colourmap
        lut_src = np.arange(256, dtype=np.uint8).reshape(1, 256)
        self._color_lut: np.ndarray = cv2.applyColorMap(lut_src, cv2.COLORMAP_TURBO)[0]

        self._last_n_points = 0
        self._last_redraw = 0.0
        self._last_fps_t = time.time()
        self._frames_since_fps = 0
        self._fps = 0.0

    # ── Public API ──────────────────────────────────────────────────────────

    def show(self) -> None:
        cv2.namedWindow(self._win, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self._win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def close(self) -> None:
        cv2.destroyWindow(self._win)

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
        self._cam_dist = max(self._xlim * 2.0, self._ylim * 1.2, self._zlim * 2.0)

    def set_label_mode(self, *, enabled: bool, max_labels: Optional[int] = None) -> None:
        pass  # not supported; here for API compatibility

    def stats(self) -> ViewerStats:
        return ViewerStats(points=self._last_n_points, fps=float(self._fps))

    def update(self, frame: Any) -> None:
        now = time.time()

        # Rate-limit renders
        if self._refresh_hz > 0.0 and (now - self._last_redraw) < (1.0 / self._refresh_hz):
            cv2.waitKey(1)
            return

        pts = getattr(frame, "point_cloud", None) or []
        xyz = self._extract_xyz(pts)
        self._last_n_points = len(xyz)

        img = np.zeros((self._H, self._W, 3), dtype=np.uint8)

        self._draw_grid(img)

        if xyz:
            arr = np.array(xyz, dtype=np.float32)
            self._draw_points(img, arr)

        self._tick_fps(now)
        self._draw_hud(img, frame, n_points=len(xyz))

        cv2.imshow(self._win, img)
        cv2.waitKey(1)

        self._last_redraw = now

    # ── Internal helpers ────────────────────────────────────────────────────

    def _extract_xyz(self, pts: Any) -> List[Tuple[float, float, float]]:
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

    def _project(self, arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Project Nx3 world points (x=lateral, y=range, z=height) to pixel
        coordinates via perspective projection.

        The scene is centred at (0, ylim/2, 0).  The camera orbits that
        centre by azimuth (yaw) and elevation (pitch).

        Returns:
            px    — int32 array, screen X  (-1 = behind camera)
            py    — int32 array, screen Y
            depth — float32 array, camera-space depth
        """
        # Centre scene at mid-range
        pts = arr.copy()
        pts[:, 1] -= self._ylim / 2.0

        # Azimuth: rotate around world Z (yaw)
        ca, sa = math.cos(self._az), math.sin(self._az)
        x1 = ca * pts[:, 0] + sa * pts[:, 1]
        y1 = -sa * pts[:, 0] + ca * pts[:, 1]
        z1 = pts[:, 2]

        # Elevation: rotate around new X axis (pitch — tilts camera up)
        ce, se = math.cos(self._el), math.sin(self._el)
        x2 = x1
        y2 = ce * y1 - se * z1  # depth axis
        z2 = se * y1 + ce * z1  # vertical axis in camera space

        # Camera sits cam_dist behind the scene along the depth axis
        depth = y2 + self._cam_dist

        # Perspective scale derived from vertical FoV
        scale = (self._H / 2.0) / math.tan(self._fov / 2.0)

        valid = depth > 0.01
        px = np.full(len(arr), -1, dtype=np.int32)
        py = np.full(len(arr), -1, dtype=np.int32)

        if valid.any():
            d = depth[valid]
            px[valid] = (x2[valid] / d * scale + self._W / 2.0).astype(np.int32)
            py[valid] = (-z2[valid] / d * scale + self._H / 2.0).astype(np.int32)

        return px, py, depth

    def _draw_points(self, img: np.ndarray, arr: np.ndarray) -> None:
        px, py, depth = self._project(arr)

        # Colour by range (y), mapped to [0, 255] then into the LUT
        y_norm = np.clip(arr[:, 1] / self._ylim * 255.0, 0, 255).astype(np.uint8)

        # Sort far → near so near points overdraw far points
        order = np.argsort(depth)[::-1]

        r = self._point_radius
        lut = self._color_lut

        for i in order:
            xi, yi = int(px[i]), int(py[i])
            if xi < 0 or not (0 <= xi < self._W and 0 <= yi < self._H):
                continue
            c = lut[y_norm[i]]
            color = (int(c[0]), int(c[1]), int(c[2]))
            if r <= 1:
                img[yi, xi] = color
            else:
                cv2.circle(img, (xi, yi), r, color, -1, cv2.LINE_AA)

    def _draw_grid(self, img: np.ndarray) -> None:
        """
        Draw a subtle ground-plane reference grid (z = 0) for depth cues.
        Range stripes run left-to-right; lateral lines run near-to-far.
        """
        dim = (35, 35, 35)  # dark grey

        # Range stripes: horizontal lines every 1 m
        step = max(1.0, self._ylim / 6.0)
        r = step
        while r <= self._ylim + 1e-6:
            ends = np.array([[-self._xlim, r, 0.0], [self._xlim, r, 0.0]], dtype=np.float32)
            px, py, depth = self._project(ends)
            if depth[0] > 0.01 and depth[1] > 0.01:
                p0 = (int(px[0]), int(py[0]))
                p1 = (int(px[1]), int(py[1]))
                cv2.line(img, p0, p1, dim, 1)
            r += step

        # Lateral lines: near-to-far spokes at -xlim, 0, +xlim
        for x_val in (-self._xlim, 0.0, self._xlim):
            ends = np.array([[x_val, 0.0, 0.0], [x_val, self._ylim, 0.0]], dtype=np.float32)
            px, py, depth = self._project(ends)
            if depth[0] > 0.01 and depth[1] > 0.01:
                p0 = (int(px[0]), int(py[0]))
                p1 = (int(px[1]), int(py[1]))
                cv2.line(img, p0, p1, dim, 1)

    def _draw_hud(self, img: np.ndarray, frame: Any, *, n_points: int) -> None:
        fn = getattr(frame, "frame_number", None)
        ts = getattr(frame, "timestamp", None)

        parts = [f"pts={n_points}", f"fps={self._fps:.1f}"]
        if fn is not None:
            try:
                parts.append(f"frame={int(fn)}")
            except Exception:
                pass
        if ts is not None:
            try:
                parts.append(f"t={float(ts):.3f}")
            except Exception:
                pass

        cv2.putText(
            img,
            "  ".join(parts),
            (12, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )

    def _tick_fps(self, now: float) -> None:
        self._frames_since_fps += 1
        dt = now - self._last_fps_t
        if dt >= 1.0:
            self._fps = self._frames_since_fps / dt
            self._frames_since_fps = 0
            self._last_fps_t = now
