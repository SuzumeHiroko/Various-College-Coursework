import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.viewer.point_cloud_viewer import PointCloudViewer  # noqa: E402


@dataclass
class RadarFrame:
    timestamp: float = 0.0
    point_cloud: List[List[float]] = field(default_factory=list)
    velocities: List[float] = field(default_factory=list)
    snr: List[float] = field(default_factory=list)
    frame_number: int = 0


def _cluster(cx: float, cy: float, n: int, sx: float, sy: float) -> List[List[float]]:
    pts: List[List[float]] = []
    for _ in range(n):
        x = random.gauss(cx, sx)
        y = random.gauss(cy, sy)
        pts.append([x, y, 0.0])
    return pts


def _clutter(n: int, xlim: float, ylim: float) -> List[List[float]]:
    pts: List[List[float]] = []
    for _ in range(n):
        x = random.uniform(-xlim, xlim)
        y = random.uniform(0.0, ylim)
        pts.append([x, y, 0.0])
    return pts


def main() -> None:
    xlim = 3.0
    ylim = 6.0

    viewer = PointCloudViewer(refresh_hz=20.0, xlim=xlim, ylim=ylim, show_origin=True)
    viewer.show()

    i = 0
    t0 = time.time()

    # Tunables
    targets_enabled = 2
    points_per_target = 60
    cluster_spread_x = 0.08
    cluster_spread_y = 0.10

    clutter_points = 25
    dropout_prob = 0.05  # probability a whole frame is "missing"

    try:
        while True:
            # Simulate occasional sensor dropouts / empty frames
            if random.random() < dropout_prob:
                frame = RadarFrame(
                    timestamp=time.time(),
                    point_cloud=[],
                    velocities=[],
                    snr=[],
                    frame_number=i,
                )
                viewer.update(frame)
                time.sleep(0.02)
                i += 1
                continue

            t = time.time() - t0

            # Smooth motion paths for 1-2 targets
            centers = [(1.0 * math.sin(t), 2.4 + 0.7 * math.cos(t))]
            if targets_enabled >= 2:
                centers.append((-1.0 * math.sin(0.7 * t), 4.2 + 0.6 * math.cos(0.7 * t)))

            pts: List[List[float]] = []
            for cx, cy in centers[:targets_enabled]:
                pts += _cluster(cx, cy, points_per_target, cluster_spread_x, cluster_spread_y)

            # Add background clutter/noise
            pts += _clutter(clutter_points, xlim=xlim, ylim=ylim)

            frame = RadarFrame(
                timestamp=time.time(),
                point_cloud=pts,
                velocities=[0.0] * len(pts),
                snr=[10.0] * len(pts),
                frame_number=i,
            )

            viewer.update(frame)
            time.sleep(0.02)
            i += 1

    except KeyboardInterrupt:
        pass
    finally:
        viewer.close()


if __name__ == "__main__":
    main()
