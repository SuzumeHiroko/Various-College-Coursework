"""
OpenCV-based 2-D point cloud viewer for radar data.

Renders two side-by-side panels on a black background and goes fullscreen:
  Left  — Top-Down   (x = lateral, y = range,  looking straight down)
  Right — Side View  (x = range,   y = height, looking from the side)

Drop-in compatible with all other viewers:
  show() / update(frame) / close() / set_limits() / set_label_mode() / stats()

Points are coloured by range (y) using the TURBO colourmap.
The grid background is built once and copied each frame — only point
drawing and the HUD happen per-frame.
"""

import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class ViewerStats:
    points: int
    fps: float


# Panel-content margins (pixels) — class-level constants, not instance attrs
_ML = 42  # left  (room for y-axis tick labels)
_MR = 10  # right
_MT = 38  # top   (room for panel title)
_MB = 26  # bottom (room for x-axis tick labels)


class PointCloudViewerCV2D:
    """
    Real-time two-panel 2-D point cloud viewer using OpenCV.

    Left panel:  top-down   (x = lateral, y = range)
    Right panel: side view  (x = range,   y = height)

    Expected frame interface (same as all other viewers):
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
        "_color_lut",
        "_td",  # (x0, x1, y0, y1) — top-down content bounds
        "_sv",  # (x0, x1, y0, y1) — side-view content bounds
        "_bg",  # static background (grid + labels), copied each frame
        "_last_n_points",
        "_last_redraw",
        "_last_fps_t",
        "_frames_since_fps",
        "_fps",
    )

    _WIN_NAME = "Radar Point Cloud 2D"

    def __init__(
        self,
        refresh_hz: float = 10.0,
        xlim: float = 3.0,
        ylim: float = 6.0,
        *,
        zlim: float = 3.0,
        max_points: int = 2000,
        point_radius: int = 3,
        title: str = "Radar Point Cloud — 2D",
        width: int = 1280,
        height: int = 720,
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

        # Pre-build a 256-entry BGR colour LUT from the TURBO colourmap
        lut_src = np.arange(256, dtype=np.uint8).reshape(1, 256)
        self._color_lut: np.ndarray = cv2.applyColorMap(lut_src, cv2.COLORMAP_TURBO)[0]

        self._last_n_points = 0
        self._last_redraw = 0.0
        self._last_fps_t = time.time()
        self._frames_since_fps = 0
        self._fps = 0.0

        self._td, self._sv = self._compute_bounds()
        self._bg = self._build_bg()

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
        self._td, self._sv = self._compute_bounds()
        self._bg = self._build_bg()

    def set_label_mode(self, *, enabled: bool, max_labels: Optional[int] = None) -> None:
        pass  # not supported; here for API compatibility

    def stats(self) -> ViewerStats:
        return ViewerStats(points=self._last_n_points, fps=float(self._fps))

    def update(self, frame: Any) -> None:
        now = time.time()

        if self._refresh_hz > 0.0 and (now - self._last_redraw) < (1.0 / self._refresh_hz):
            cv2.waitKey(1)
            return

        pts = getattr(frame, "point_cloud", None) or []
        xyz = self._extract_xyz(pts)
        self._last_n_points = len(xyz)

        # Copy static background — grid and labels are already drawn
        img = self._bg.copy()

        if xyz:
            arr = np.array(xyz, dtype=np.float32)

            # Colour by range (y), same mapping in both panels
            y_norm = np.clip(arr[:, 1] / self._ylim * 255.0, 0, 255).astype(np.uint8)
            colors = self._color_lut[y_norm]  # Nx3 BGR

            td = self._td
            px, py = self._map_td(arr)
            self._draw_pts(img, px, py, colors, td[0], td[1], td[2], td[3])

            sv = self._sv
            px, py = self._map_sv(arr)
            self._draw_pts(img, px, py, colors, sv[0], sv[1], sv[2], sv[3])

        self._tick_fps(now)
        self._draw_hud(img, frame, n_points=len(xyz))

        cv2.imshow(self._win, img)
        cv2.waitKey(1)

        self._last_redraw = now

    # ── Coordinate transforms ───────────────────────────────────────────────

    def _compute_bounds(
        self,
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        half_W = self._W // 2
        td = (_ML, half_W - _MR, _MT, self._H - _MB)
        sv = (half_W + _ML, self._W - _MR, _MT, self._H - _MB)
        return td, sv

    def _map_td(self, arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorised: world (x lateral, y range) → top-down pixel coords."""
        x0, x1, y0, y1 = self._td
        w, h = x1 - x0, y1 - y0
        px = ((arr[:, 0] + self._xlim) / (2.0 * self._xlim) * w + x0).astype(np.int32)
        py = ((1.0 - arr[:, 1] / self._ylim) * h + y0).astype(np.int32)
        return px, py

    def _map_sv(self, arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorised: world (y range, z height) → side-view pixel coords."""
        x0, x1, y0, y1 = self._sv
        w, h = x1 - x0, y1 - y0
        px = (arr[:, 1] / self._ylim * w + x0).astype(np.int32)
        py = ((1.0 - (arr[:, 2] + self._zlim) / (2.0 * self._zlim)) * h + y0).astype(np.int32)
        return px, py

    # Scalar helpers used only during background build
    def _td_px(self, x_w: float) -> int:
        x0, x1, _, _ = self._td
        return int((x_w + self._xlim) / (2.0 * self._xlim) * (x1 - x0) + x0)

    def _td_py(self, y_w: float) -> int:
        _, _, y0, y1 = self._td
        return int((1.0 - y_w / self._ylim) * (y1 - y0) + y0)

    def _sv_px(self, y_w: float) -> int:
        x0, x1, _, _ = self._sv
        return int(y_w / self._ylim * (x1 - x0) + x0)

    def _sv_py(self, z_w: float) -> int:
        _, _, y0, y1 = self._sv
        return int((1.0 - (z_w + self._zlim) / (2.0 * self._zlim)) * (y1 - y0) + y0)

    # ── Drawing ─────────────────────────────────────────────────────────────

    def _draw_pts(
        self,
        img: np.ndarray,
        px: np.ndarray,
        py: np.ndarray,
        colors: np.ndarray,
        x0: int,
        x1: int,
        y0: int,
        y1: int,
    ) -> None:
        """Draw points clipped to the given panel bounds."""
        valid = (px >= x0) & (px < x1) & (py >= y0) & (py < y1)
        if not valid.any():
            return
        r = self._point_radius
        if r <= 1:
            # Fast path: single-pixel numpy indexing — no Python loop
            img[py[valid], px[valid]] = colors[valid]
        else:
            for i in np.where(valid)[0]:
                c = (int(colors[i, 0]), int(colors[i, 1]), int(colors[i, 2]))
                cv2.circle(img, (int(px[i]), int(py[i])), r, c, -1, cv2.LINE_AA)

    def _build_bg(self) -> np.ndarray:
        """
        Build the static background image: black canvas with grid lines,
        tick labels, panel borders, titles, and the sensor origin marker.
        Called once at init and again whenever limits change.
        """
        bg = np.zeros((self._H, self._W, 3), dtype=np.uint8)

        GRID = (40, 40, 40)
        CENTER = (65, 65, 65)
        BORDER = (55, 55, 55)
        LABEL = (140, 140, 140)
        DIVIDER = (70, 70, 70)
        TITLE_C = (200, 200, 200)
        FONT = cv2.FONT_HERSHEY_SIMPLEX
        FS = 0.33  # tick-label font scale
        FS_T = 0.47  # panel-title font scale

        half_W = self._W // 2
        td = self._td  # (x0, x1, y0, y1)
        sv = self._sv

        # ── Panel structure ────────────────────────────────────────────────
        cv2.line(bg, (half_W, 0), (half_W, self._H), DIVIDER, 1)
        cv2.rectangle(bg, (td[0], td[2]), (td[1], td[3]), BORDER, 1)
        cv2.rectangle(bg, (sv[0], sv[2]), (sv[1], sv[3]), BORDER, 1)

        cv2.putText(
            bg,
            "Top-Down  (lateral / range)",
            (td[0], td[2] - 10),
            FONT,
            FS_T,
            TITLE_C,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            bg,
            "Side View  (range / height)",
            (sv[0], sv[2] - 10),
            FONT,
            FS_T,
            TITLE_C,
            1,
            cv2.LINE_AA,
        )

        # ── Top-down grid ──────────────────────────────────────────────────
        # Range stripes (horizontal lines, one per metre or per ylim/6)
        y_step = max(1.0, round(self._ylim / 6))
        y_m = y_step
        while y_m <= self._ylim + 1e-6:
            py = self._td_py(y_m)
            cv2.line(bg, (td[0], py), (td[1], py), GRID, 1)
            cv2.putText(bg, f"{y_m:.0f}m", (td[0] - 40, py + 4), FONT, FS, LABEL, 1)
            y_m += y_step

        # Lateral stripes (vertical lines)
        x_step = max(1.0, round(self._xlim))
        x_m = -self._xlim
        while x_m <= self._xlim + 1e-6:
            px = self._td_px(x_m)
            cv2.line(bg, (px, td[2]), (px, td[3]), CENTER if abs(x_m) < 1e-6 else GRID, 1)
            cv2.putText(bg, f"{x_m:.0f}", (px - 7, td[3] + 18), FONT, FS, LABEL, 1)
            x_m += x_step

        # Sensor origin triangle marker at (0, 0)
        ox, oy = self._td_px(0.0), self._td_py(0.0)
        cv2.drawMarker(bg, (ox, oy), (120, 120, 120), cv2.MARKER_TRIANGLE_UP, 10, 1, cv2.LINE_AA)

        # ── Side-view grid ─────────────────────────────────────────────────
        # Range stripes (vertical lines, near=left)
        y_m = y_step
        while y_m <= self._ylim + 1e-6:
            px = self._sv_px(y_m)
            cv2.line(bg, (px, sv[2]), (px, sv[3]), GRID, 1)
            cv2.putText(bg, f"{y_m:.0f}m", (px - 8, sv[3] + 18), FONT, FS, LABEL, 1)
            y_m += y_step

        # Height stripes (horizontal lines, up=top)
        z_step = max(1.0, round(self._zlim))
        z_m = -self._zlim
        while z_m <= self._zlim + 1e-6:
            py = self._sv_py(z_m)
            cv2.line(bg, (sv[0], py), (sv[1], py), CENTER if abs(z_m) < 1e-6 else GRID, 1)
            cv2.putText(bg, f"{z_m:.0f}m", (sv[0] - 40, py + 4), FONT, FS, LABEL, 1)
            z_m += z_step

        return bg

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
            (12, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )

    # ── Internals ───────────────────────────────────────────────────────────

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

    def _tick_fps(self, now: float) -> None:
        self._frames_since_fps += 1
        dt = now - self._last_fps_t
        if dt >= 1.0:
            self._fps = self._frames_since_fps / dt
            self._frames_since_fps = 0
            self._last_fps_t = now
