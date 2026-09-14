"""
Replay a radar JSONL log file in the 3-D viewer at the original recorded speed.

Frame timestamps are used to schedule each display update, so long gaps between
frames are reproduced faithfully — the viewer will idle for the same duration
that the radar was idle during recording.

If the viewer or system falls behind (e.g. rendering took too long), the next
frame is shown immediately rather than trying to catch up.

Usage:
    python examples/replay_log.py logs/radar_20260225_143012.jsonl
    python examples/replay_log.py logs/session.jsonl --xlim 4 --ylim 8
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from viewer import PointCloudViewer3D

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class _ReplayFrame:
    """Duck-typed frame compatible with PointCloudViewer / PointCloudViewer3D."""
    point_cloud: list
    timestamp: Optional[float] = None
    frame_number: Optional[int] = None


def load_frames(path: Path) -> List[_ReplayFrame]:
    frames = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed line %d: %s", lineno, exc)
                continue
            frames.append(_ReplayFrame(
                point_cloud=obj.get("point_cloud", []),
                timestamp=obj.get("timestamp"),
                frame_number=obj.get("frame_number"),
            ))

    if not frames:
        raise ValueError(f"No valid frames found in {path}")

    # Sort by timestamp so out-of-order writes replay correctly.
    frames.sort(key=lambda f: (f.timestamp is None, f.timestamp))
    return frames


def parse_args():
    ap = argparse.ArgumentParser(description="Replay a radar JSONL log in the 3-D viewer")
    ap.add_argument("log_file", help="Path to the .jsonl log file")
    ap.add_argument("--xlim", type=float, default=3.0, help="Half-width of view in meters")
    ap.add_argument("--ylim", type=float, default=6.0, help="Depth of view in meters")
    ap.add_argument("--zlim", type=float, default=3.0, help="Half-height of view in meters")
    ap.add_argument("--refresh-hz", type=float, default=10.0, help="Viewer refresh rate")
    return ap.parse_args()


def main():
    args = parse_args()
    log_path = Path(args.log_file)

    if not log_path.exists():
        logger.error("Log file not found: %s", log_path)
        sys.exit(1)

    logger.info("Loading %s ...", log_path)
    frames = load_frames(log_path)
    logger.info("Loaded %d frames", len(frames))

    viewer = PointCloudViewer3D(
        refresh_hz=args.refresh_hz,
        xlim=args.xlim,
        ylim=args.ylim,
        zlim=args.zlim,
        title=f"Replay — {log_path.name}",
    )
    viewer.show()

    # Anchor: map the first frame's timestamp to right now.
    log_start = frames[0].timestamp or 0.0
    playback_start = time.time()

    logger.info("Replaying %d frames (Ctrl-C to stop) ...", len(frames))
    try:
        for frame in frames:
            # How many seconds into the log this frame belongs.
            frame_offset = (frame.timestamp or log_start) - log_start

            # How many seconds have elapsed in real playback time.
            elapsed = time.time() - playback_start

            wait = frame_offset - elapsed
            if wait > 0:
                time.sleep(wait)

            viewer.update(frame)

    except KeyboardInterrupt:
        logger.info("Replay stopped by user")
    finally:
        viewer.close()

    logger.info("Replay complete")


if __name__ == "__main__":
    main()
