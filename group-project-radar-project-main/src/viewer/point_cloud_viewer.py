import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple
import numpy as np

import matplotlib.pyplot as plt


@dataclass(frozen=True)
class ViewerStats:
    points: int
    fps: float


class PointCloudViewer:
    """
    Real-time top-down (X/Y) point cloud viewer for RadarFrame-like objects.

    Expected frame interface:
      - frame.point_cloud: Sequence[Sequence[float]] where each point is [x, y, z]
      - frame.timestamp (optional): float epoch seconds
      - frame.frame_number (optional): int

    Notes:
      - Labeling points is expensive; keep it off unless debugging.
      - Designed to be light enough for Pi-class hardware.
    """

    __slots__ = (
        "_refresh_hz",
        "_xlim",
        "_ylim",
        "_invert_y",
        "_show_labels",
        "_max_labels",
        "_max_points",
        "_point_size",
        "_title",
        "_show_origin",
        "_fig",
        "_ax",
        "_scatter",
        "_texts",
        "_last_redraw",
        "_last_fps_t",
        "_frames_since_fps",
        "_fps",
    )

    def __init__(
        self,
        refresh_hz: float = 10.0,
        xlim: float = 3.0,
        ylim: float = 6.0,
        *,
        invert_y: bool = False,
        show_labels: bool = False,
        max_labels: int = 50,
        max_points: int = 5000,
        point_size: float = 10.0,
        title: str = "Radar Point Cloud (Top-Down X/Y)",
        show_origin: bool = True,
    ):
        self._refresh_hz = float(refresh_hz)
        self._xlim = float(xlim)
        self._ylim = float(ylim)
        self._invert_y = bool(invert_y)

        self._show_labels = bool(show_labels)
        self._max_labels = int(max_labels)
        self._max_points = int(max_points)
        self._point_size = float(point_size)
        self._title = str(title)
        self._show_origin = bool(show_origin)

        self._fig, self._ax = plt.subplots()
        self._scatter = self._ax.scatter([], [], s=self._point_size)
        self._texts: List[Any] = []

        self._ax.set_xlabel("lateral — x (m)")
        self._ax.set_ylabel("forward / range — y (m)")
        self._ax.set_xlim(-self._xlim, self._xlim)
        self._ax.set_ylim(0.0, self._ylim)
        self._ax.set_aspect("equal", adjustable="box")
        if self._invert_y:
            self._ax.invert_yaxis()

        if self._show_origin:
            self._ax.axhline(0.0, linewidth=0.8)
            self._ax.axvline(0.0, linewidth=0.8)

        self._ax.grid(True, linestyle="--", linewidth=0.5)

        self._last_redraw = 0.0
        self._last_fps_t = time.time()
        self._frames_since_fps = 0
        self._fps = 0.0

        self._fig.tight_layout()

    def show(self) -> None:
        plt.show(block=False)

    def close(self) -> None:
        plt.close(self._fig)

    def set_limits(self, *, xlim: Optional[float] = None, ylim: Optional[float] = None) -> None:
        if xlim is not None:
            self._xlim = float(xlim)
            self._ax.set_xlim(-self._xlim, self._xlim)
        if ylim is not None:
            self._ylim = float(ylim)
            self._ax.set_ylim(0.0, self._ylim)
            if self._invert_y:
                self._ax.invert_yaxis()
        self._fig.tight_layout()

    def set_label_mode(self, *, enabled: bool, max_labels: Optional[int] = None) -> None:
        self._show_labels = bool(enabled)
        if max_labels is not None:
            self._max_labels = int(max_labels)
        if not self._show_labels:
            self._clear_texts()

    def stats(self) -> ViewerStats:
        offsets = self._scatter.get_offsets()
        return ViewerStats(points=int(len(offsets)), fps=float(self._fps))

    def update(self, frame: Any) -> None:
        now = time.time()

        pts = getattr(frame, "point_cloud", None) or []
        xy = self._extract_xy(pts, max_points=self._max_points)
        if xy:
            self._scatter.set_offsets(xy)
        else:
            self._scatter.set_offsets(np.empty((0, 2)))

        if self._refresh_hz > 0.0 and (now - self._last_redraw) < (1.0 / self._refresh_hz):
            return
        self._last_redraw = now

        if self._show_labels:
            self._render_labels(xy)
        elif self._texts:
            self._clear_texts()

        self._tick_fps(now)
        self._ax.set_title(self._format_title(frame, points=len(xy)))

        self._fig.canvas.draw_idle()
        plt.pause(0.001)

    def _extract_xy(self, pts: Any, *, max_points: int) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        if not isinstance(pts, (Sequence, np.ndarray)):
            return out

        n = 0
        for p in pts:
            if n >= max_points:
                break
            if not isinstance(p, Sequence) or len(p) < 2:
                continue
            try:
                x = float(p[0])
                y = float(p[1])
            except Exception:
                continue
            out.append((x, y))
            n += 1

        return out

    def _render_labels(self, xy: Sequence[Tuple[float, float]]) -> None:
        self._clear_texts()
        limit = min(len(xy), self._max_labels)
        for i in range(limit):
            x, y = xy[i]
            self._texts.append(self._ax.text(x, y, str(i), fontsize=6))

    def _clear_texts(self) -> None:
        for t in self._texts:
            try:
                t.remove()
            except Exception:
                pass
        self._texts = []

    def _tick_fps(self, now: float) -> None:
        self._frames_since_fps += 1
        dt = now - self._last_fps_t
        if dt >= 1.0:
            self._fps = self._frames_since_fps / dt
            self._frames_since_fps = 0
            self._last_fps_t = now

    def _format_title(self, frame: Any, *, points: int) -> str:
        ts = getattr(frame, "timestamp", None)
        fn = getattr(frame, "frame_number", None)

        parts = [self._title, f"points={points}", f"fps={self._fps:.1f}"]

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

        return " | ".join(parts)
