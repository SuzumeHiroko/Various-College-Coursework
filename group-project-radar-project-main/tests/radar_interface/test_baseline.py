"""
Empty-room baseline test for RadarController / RadarFrame.

Measures background clutter (false positives) with no target present.
Mean points/frame should be near zero for a clean radar installation.
High clutter may indicate reflective surfaces near the sensor.

Instructions:
    Clear the room — nobody should be in the radar's field of view.

Usage:
    python tests/radar_interface/test_baseline.py \\
        --data-port /dev/tty.usbserial-011D1B5A1 \\
        --config-port /dev/tty.usbserial-011D1B5A0 \\
        --cfg-file src/radar/profile_3d.cfg

    # Override frame count
    python tests/radar_interface/test_baseline.py ... --frames 200
"""

import argparse
import logging
import time

from radar_test_utils import (
    BASELINE_POINT_WARN,
    validate_frame_fields,
    add_common_args,
    build_radar,
)

logger = logging.getLogger(__name__)

DEFAULT_FRAMES = 100


def run(radar, max_frames: int) -> dict:
    frames_collected = 0
    total_points = 0
    total_errors = 0
    dropped_frames = 0
    prev_frame_number = None

    try:
        while frames_collected < max_frames:
            if radar.is_available():
                frame = radar.read()
                frames_collected += 1
                n = len(frame.point_cloud)
                total_points += n

                if prev_frame_number is not None:
                    gap = frame.frame_number - prev_frame_number - 1
                    if gap > 0:
                        dropped_frames += gap
                        logger.warning(
                            "Dropped %d frame(s) between #%d and #%d",
                            gap,
                            prev_frame_number,
                            frame.frame_number,
                        )
                prev_frame_number = frame.frame_number

                errors = validate_frame_fields(frame)
                total_errors += len(errors)

                logger.info("Frame %4d | %3d pts", frame.frame_number, n)
                for err in errors:
                    logger.error("  [FIELD] %s", err)

            elif not radar.is_healthy():
                logger.warning("Radar not healthy — no fresh data")

            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Stopped by user (Ctrl-C)")

    mean_pts = total_points / frames_collected if frames_collected > 0 else 0.0

    return {
        "frames_collected": frames_collected,
        "mean_pts": mean_pts,
        "total_errors": total_errors,
        "dropped_frames": dropped_frames,
        "sync_losses": radar.sync_loss_count,
    }


def print_summary(results: dict) -> None:
    mean_pts = results["mean_pts"]

    logger.info("")
    logger.info("=== Summary — Empty-room baseline ===")
    logger.info("Frames received  : %d", results["frames_collected"])
    logger.info("Mean pts / frame : %.1f", mean_pts)
    logger.info("")
    logger.info("--- Reliability ---")
    logger.info("  Field errors   : %d", results["total_errors"])
    logger.info("  Dropped frames : %d", results["dropped_frames"])
    logger.info("  Sync losses    : %d", results["sync_losses"])
    logger.info("")
    logger.info("--- Clutter ---")
    if mean_pts > BASELINE_POINT_WARN:
        logger.warning(
            "  [BASELINE] Mean %.1f pts/frame exceeds threshold (%d) with empty room. "
            "High background clutter — check for reflective surfaces near the radar.",
            mean_pts,
            BASELINE_POINT_WARN,
        )
    else:
        logger.info("  [BASELINE] Mean %.1f pts/frame — clutter level acceptable.", mean_pts)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Empty-room baseline test — measures background clutter with no target"
    )
    add_common_args(ap)
    ap.add_argument(
        "--frames",
        type=int,
        default=DEFAULT_FRAMES,
        help=f"Number of frames to collect (default: {DEFAULT_FRAMES})",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("=" * 60)
    logger.info("Scenario: Empty-room baseline")
    logger.info("=" * 60)
    logger.info("  Clear the room — nobody should be in the radar's field of view.")
    logger.info("  Collecting %d frames.", args.frames)
    logger.info("=" * 60)
    input("Press Enter when ready...")
    for i in range(5, 0, -1):
        logger.info("Starting in %d...", i)
        time.sleep(1)

    radar = build_radar(args)
    try:
        results = run(radar, args.frames)
    finally:
        radar.stop()

    print_summary(results)


if __name__ == "__main__":
    main()
