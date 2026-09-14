"""
Correctness test for RadarController / RadarFrame.

Validates that all five fields (x, y, z, velocity, snr) are present,
correctly typed, and within plausible physical ranges for every frame.
Also checks bounding box against expected room dimensions and detects
dropped frames (gaps in frame_number sequence).

Instructions:
    Stand 1-2 m in front of the radar and move around naturally.

Usage:
    python tests/radar_interface/test_correctness.py \\
        --data-port /dev/tty.usbserial-011D1B5A1 \\
        --config-port /dev/tty.usbserial-011D1B5A0 \\
        --cfg-file src/radar/profile_3d.cfg

    # Override frame count
    python tests/radar_interface/test_correctness.py ... --frames 100

    # Skip bounding box check
    python tests/radar_interface/test_correctness.py ... --no-bounds-check
"""

import argparse
import logging
import sys
import time

from radar_test_utils import (
    validate_frame_fields,
    check_bounds,
    add_common_args,
    build_radar,
)

logger = logging.getLogger(__name__)

DEFAULT_FRAMES = 50


def run(radar, max_frames: int, no_bounds_check: bool) -> dict:
    frames_collected = 0
    total_errors = 0
    dropped_frames = 0
    prev_frame_number = None

    try:
        while frames_collected < max_frames:
            if radar.is_available():
                frame = radar.read()
                frames_collected += 1

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
                n = len(frame.point_cloud)

                max_vel = max(frame.velocities, key=abs) if frame.velocities else float("nan")
                status = "PASS" if not errors else f"FAIL ({len(errors)} error(s))"
                logger.info(
                    "Frame %4d | %3d pts | vel_max=%+.2f m/s | snr[0]=%.1f dB | %s",
                    frame.frame_number,
                    n,
                    max_vel,
                    frame.snr[0] if frame.snr else float("nan"),
                    status,
                )
                for err in errors:
                    logger.error("  [FIELD] %s", err)

                if not no_bounds_check:
                    dims = check_bounds(frame)
                    if dims:
                        logger.info(
                            "  [BOUNDS] x=[%.2f, %.2f]  y=[%.2f, %.2f]  z=[%.2f, %.2f]",
                            dims["x_min"],
                            dims["x_max"],
                            dims["y_min"],
                            dims["y_max"],
                            dims["z_min"],
                            dims["z_max"],
                        )

            elif not radar.is_healthy():
                logger.warning("Radar not healthy — no fresh data")

            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Stopped by user (Ctrl-C)")

    return {
        "frames_collected": frames_collected,
        "total_errors": total_errors,
        "dropped_frames": dropped_frames,
        "sync_losses": radar.sync_loss_count,
    }


def print_summary(results: dict) -> None:
    logger.info("")
    logger.info("=== Summary — Correctness ===")
    logger.info("Frames received  : %d", results["frames_collected"])
    logger.info("")
    logger.info("--- Reliability ---")
    logger.info("  Field errors   : %d", results["total_errors"])
    logger.info("  Dropped frames : %d", results["dropped_frames"])
    logger.info("  Sync losses    : %d", results["sync_losses"])
    logger.info("")
    logger.info("Result           : %s", "PASS" if results["total_errors"] == 0 else "FAIL")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Correctness test — validates RadarFrame field types and ranges"
    )
    add_common_args(ap)
    ap.add_argument(
        "--frames",
        type=int,
        default=DEFAULT_FRAMES,
        help=f"Number of frames to collect (default: {DEFAULT_FRAMES})",
    )
    ap.add_argument("--no-bounds-check", action="store_true", help="Skip bounding box check")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("=" * 60)
    logger.info("Scenario: Correctness")
    logger.info("=" * 60)
    logger.info("  Stand 1-2 m in front of the radar and move around naturally.")
    logger.info("  Collecting %d frames.", args.frames)
    logger.info("=" * 60)
    input("Press Enter when ready...")
    for i in range(5, 0, -1):
        logger.info("Starting in %d...", i)
        time.sleep(1)

    radar = build_radar(args)
    try:
        results = run(radar, args.frames, args.no_bounds_check)
    finally:
        radar.stop()

    print_summary(results)
    sys.exit(0 if results["total_errors"] == 0 else 1)


if __name__ == "__main__":
    main()
