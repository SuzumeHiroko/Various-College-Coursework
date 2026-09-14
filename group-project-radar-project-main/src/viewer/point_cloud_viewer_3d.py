import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple
import numpy as np

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 – registers 3-D projection


@dataclass(frozen=True)
class ViewerStats:
    points: int
    fps: float


class PointCloudViewer3D:
    """
    Real-time 4-quadrant 3-D point cloud viewer for RadarFrame-like objects.

    Layout:
      ┌─────────────────┬─────────────────┐
      │  3-D perspective│   Top-Down      │
      │   (X / Y / Z)   │  (X lat / Y rng)│
      ├─────────────────┼─────────────────┤
      │   Side View     │  Face-Forward   │
      │  (Y rng / Z ht) │  (X lat / Z ht) │
      └─────────────────┴─────────────────┘

    Side view: left edge = closest to radar (small Y / range).
    Face-forward: radar's POV looking forward (X = lateral, Z = height).

    Expected frame interface (identical to PointCloudViewer):
      - frame.point_cloud: Sequence[Sequence[float]]  — each point [x, y, z]
      - frame.timestamp    (optional): float epoch seconds
      - frame.frame_number (optional): int
    """

    __slots__ = (
        "_refresh_hz",
        "_xlim",
        "_ylim",
        "_zlim",
        "_invert_y",
        "_show_labels",
        "_max_labels",
        "_max_points",
        "_point_size",
        "_title",
        "_show_origin",
        "_fig",
        "_ax3d",
        "_ax_top",
        "_ax_side",
        "_ax_front",
        "_sc3d",
        "_sc_top",
        "_sc_side",
        "_sc_front",
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
        zlim: float = 3.0,
        invert_y: bool = False,
        show_labels: bool = False,
        max_labels: int = 50,
        max_points: int = 5000,
        point_size: float = 10.0,
        title: str = "Radar Point Cloud — 3D",
        show_origin: bool = True,
    ):
        self._refresh_hz = float(refresh_hz)
        self._xlim = float(xlim)
        self._ylim = float(ylim)
        self._zlim = float(zlim)
        self._invert_y = bool(invert_y)
        self._show_labels = bool(show_labels)
        self._max_labels = int(max_labels)
        self._max_points = int(max_points)
        self._point_size = float(point_size)
        self._title = str(title)
        self._show_origin = bool(show_origin)

        self._fig = plt.figure(figsize=(12, 9))

        self._ax3d = self._fig.add_subplot(2, 2, 1, projection="3d")
        self._ax_top = self._fig.add_subplot(2, 2, 2)
        self._ax_side = self._fig.add_subplot(2, 2, 3)
        self._ax_front = self._fig.add_subplot(2, 2, 4)

        # ── 3-D perspective ──────────────────────────────────────────────────
        self._sc3d = self._ax3d.scatter([], [], [], s=self._point_size)
        self._ax3d.set_xlabel("x (lat)")
        self._ax3d.set_ylabel("y (rng)")
        self._ax3d.set_zlabel("z (ht)")
        self._ax3d.set_xlim(-self._xlim, self._xlim)
        self._ax3d.set_ylim(0.0, self._ylim)
        self._ax3d.set_zlim(-self._zlim, self._zlim)
        self._ax3d.set_title("3-D View")

        # ── Top-down  (X lateral  ×  Y range) ───────────────────────────────
        self._sc_top = self._ax_top.scatter([], [], s=self._point_size)
        self._ax_top.set_xlabel("lateral — x (m)")
        self._ax_top.set_ylabel("range — y (m)")
        self._ax_top.set_xlim(-self._xlim, self._xlim)
        self._ax_top.set_ylim(0.0, self._ylim)
        self._ax_top.set_aspect("equal", adjustable="box")
        self._ax_top.set_title("Top-Down")
        if self._invert_y:
            self._ax_top.invert_yaxis()
        if self._show_origin:
            self._ax_top.axhline(0.0, linewidth=0.8)
            self._ax_top.axvline(0.0, linewidth=0.8)
        self._ax_top.grid(True, linestyle="--", linewidth=0.5)

        # ── Side view  (Y range on X-axis, Z height on Y-axis) ──────────────
        # Left = near (small Y), right = far (large Y)
        self._sc_side = self._ax_side.scatter([], [], s=self._point_size)
        self._ax_side.set_xlabel("range — y (m)  [left = near]")
        self._ax_side.set_ylabel("height — z (m)")
        self._ax_side.set_xlim(0.0, self._ylim)
        self._ax_side.set_ylim(-self._zlim, self._zlim)
        self._ax_side.set_title("Side View")
        if self._show_origin:
            self._ax_side.axhline(0.0, linewidth=0.8)
            self._ax_side.axvline(0.0, linewidth=0.8)
        self._ax_side.grid(True, linestyle="--", linewidth=0.5)

        # ── Face-forward  (X lateral  ×  Z height) ──────────────────────────
        self._sc_front = self._ax_front.scatter([], [], s=self._point_size)
        self._ax_front.set_xlabel("lateral — x (m)")
        self._ax_front.set_ylabel("height — z (m)")
        self._ax_front.set_xlim(-self._xlim, self._xlim)
        self._ax_front.set_ylim(-self._zlim, self._zlim)
        self._ax_front.set_aspect("equal", adjustable="box")
        self._ax_front.set_title("Face-Forward")
        if self._show_origin:
            self._ax_front.axhline(0.0, linewidth=0.8)
            self._ax_front.axvline(0.0, linewidth=0.8)
        self._ax_front.grid(True, linestyle="--", linewidth=0.5)

        self._texts: List[Any] = []

        self._last_redraw = 0.0
        self._last_fps_t = time.time()
        self._frames_since_fps = 0
        self._fps = 0.0

        self._fig.suptitle(self._title, fontsize=12)
        self._fig.tight_layout()

    # ── Public API (mirrors PointCloudViewer) ────────────────────────────────

    def show(self) -> None:
        plt.show(block=False)

    def close(self) -> None:
        plt.close(self._fig)

    def set_limits(
        self,
        *,
        xlim: Optional[float] = None,
        ylim: Optional[float] = None,
        zlim: Optional[float] = None,
    ) -> None:
        if xlim is not None:
            self._xlim = float(xlim)
            self._ax3d.set_xlim(-self._xlim, self._xlim)
            self._ax_top.set_xlim(-self._xlim, self._xlim)
            self._ax_front.set_xlim(-self._xlim, self._xlim)
        if ylim is not None:
            self._ylim = float(ylim)
            self._ax3d.set_ylim(0.0, self._ylim)
            self._ax_top.set_ylim(0.0, self._ylim)
            if self._invert_y:
                self._ax_top.invert_yaxis()
            self._ax_side.set_xlim(0.0, self._ylim)
        if zlim is not None:
            self._zlim = float(zlim)
            self._ax3d.set_zlim(-self._zlim, self._zlim)
            self._ax_side.set_ylim(-self._zlim, self._zlim)
            self._ax_front.set_ylim(-self._zlim, self._zlim)
        self._fig.tight_layout()

    def set_label_mode(self, *, enabled: bool, max_labels: Optional[int] = None) -> None:
        self._show_labels = bool(enabled)
        if max_labels is not None:
            self._max_labels = int(max_labels)
        if not self._show_labels:
            self._clear_texts()

    def stats(self) -> ViewerStats:
        offsets = self._sc_top.get_offsets()
        return ViewerStats(points=int(len(offsets)), fps=float(self._fps))

    def update(self, frame: Any) -> None:
        now = time.time()

        pts = getattr(frame, "point_cloud", None) or []
        xyz = self._extract_xyz(pts, max_points=self._max_points)

        if xyz:
            arr = np.array(xyz, dtype=float)
            xs, ys, zs = arr[:, 0], arr[:, 1], arr[:, 2]
        else:
            xs = ys = zs = np.empty(0)

        # 3-D scatter — update via internal offset array
        self._sc3d._offsets3d = (xs, ys, zs)

        # 2-D projections
        if len(xs):
            self._sc_top.set_offsets(np.column_stack([xs, ys]))
            self._sc_side.set_offsets(np.column_stack([ys, zs]))
            self._sc_front.set_offsets(np.column_stack([xs, zs]))
        else:
            _empty = np.empty((0, 2))
            self._sc_top.set_offsets(_empty)
            self._sc_side.set_offsets(_empty)
            self._sc_front.set_offsets(_empty)

        if self._refresh_hz > 0.0 and (now - self._last_redraw) < (1.0 / self._refresh_hz):
            return
        self._last_redraw = now

        if self._show_labels:
            self._render_labels(xyz)
        elif self._texts:
            self._clear_texts()

        self._tick_fps(now)
        self._fig.suptitle(self._format_title(frame, points=len(xyz)), fontsize=12)

        self._fig.canvas.draw_idle()
        plt.pause(0.001)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _extract_xyz(self, pts: Any, *, max_points: int) -> List[Tuple[float, float, float]]:
        out: List[Tuple[float, float, float]] = []
        if not isinstance(pts, (Sequence, np.ndarray)):
            return out

        n = 0
        for p in pts:
            if n >= max_points:
                break
            if not isinstance(p, Sequence) or len(p) < 3:
                continue
            try:
                x = float(p[0])
                y = float(p[1])
                z = float(p[2])
            except Exception:
                continue
            out.append((x, y, z))
            n += 1

        return out

    def _render_labels(self, xyz: Sequence[Tuple[float, float, float]]) -> None:
        self._clear_texts()
        limit = min(len(xyz), self._max_labels)
        for i in range(limit):
            x, y, z = xyz[i]
            self._texts.append(self._ax3d.text(x, y, z, str(i), fontsize=6))

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
