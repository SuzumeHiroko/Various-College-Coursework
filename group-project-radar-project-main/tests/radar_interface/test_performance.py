"""
Performance benchmark for RadarController / RadarFrame.

Runs an extended collection (default 5 minutes) and measures:
  - Frame rate (fps) and inter-frame jitter
  - Dropped frames (gaps in frame_number sequence)
  - Sync loss rate
  - DSP processing margin (from TLV 6 stats)

Per-frame output is suppressed. A status line prints every 10 seconds.
A full summary is printed at the end.

Instructions:
    Stand or move naturally in the room.

Usage:
    python tests/radar_interface/test_performance.py \\
        --data-port /dev/tty.usbserial-011D1B5A1 \\
        --config-port /dev/tty.usbserial-011D1B5A0 \\
        --cfg-file src/radar/profile_3d.cfg

    # Override run duration
    python tests/radar_interface/test_performance.py ... --duration 120
"""

import argparse
import logging
import time

from radar_test_utils import (
    inter_frame_stats,
    add_common_args,
    build_radar,
)

logger = logging.getLogger(__name__)

DEFAULT_DURATION_S = 300.0  # 5 minutes


def run(radar, duration_s: float) -> dict:
    frames_collected = 0
    dropped_frames = 0
    prev_frame_number = None
    frame_timestamps = []
    last_status_t = time.time()
    start_t = time.time()

    try:
        while (time.time() - start_t) < duration_s:
            if radar.is_available():
                frame = radar.read()
                frame_timestamps.append(time.time())
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

                now = time.time()
                if now - last_status_t >= 10.0:
                    elapsed = now - start_t
                    fps = frames_collected / elapsed if elapsed > 0 else 0.0
                    logger.info(
                        "[t=%5.0fs] frames=%d  fps=%.1f  " "dropped=%d  sync_losses=%d",
                        elapsed,
                        frames_collected,
                        fps,
                        dropped_frames,
                        radar.sync_loss_count,
                    )
                    if (
                        frame.stats is not None
                        and frame.stats.get("inter_frame_processing_margin_us", 1) == 0
                    ):
                        logger.warning(
                            "  [DSP] inter_frame_processing_margin_us=0 "
                            "— radar DSP is at capacity"
                        )
                    last_status_t = now

            elif not radar.is_healthy():
                logger.warning("Radar not healthy — no fresh data")

            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Stopped by user (Ctrl-C)")

    elapsed_total = time.time() - start_t
    sync_losses = radar.sync_loss_count
    sync_loss_rate = sync_losses / frames_collected if frames_collected > 0 else 0.0
    perf = inter_frame_stats(frame_timestamps)

    return {
        "frames_collected": frames_collected,
        "elapsed_s": elapsed_total,
        "dropped_frames": dropped_frames,
        "sync_losses": sync_losses,
        "sync_loss_rate": sync_loss_rate,
        "perf": perf,
    }


def print_summary(results: dict) -> None:
    perf = results["perf"]

    logger.info("")
    logger.info("=== Summary — Performance benchmark ===")
    logger.info("Duration         : %.1f s", results["elapsed_s"])
    logger.info("Frames received  : %d", results["frames_collected"])
    logger.info("")
    logger.info("--- Frame rate ---")
    logger.info("  Measured fps   : %.2f Hz", perf["fps"])
    logger.info("  Interval mean  : %.1f ms", perf["interval_mean_ms"])
    logger.info("  Interval jitter: %.1f ms (std dev)", perf["interval_std_ms"])
    logger.info("  Interval min   : %.1f ms", perf["interval_min_ms"])
    logger.info("  Interval max   : %.1f ms", perf["interval_max_ms"])
    logger.info("")
    logger.info("--- Reliability ---")
    logger.info("  Dropped frames : %d", results["dropped_frames"])
    logger.info(
        "  Sync losses    : %d (%.2f%%)", results["sync_losses"], results["sync_loss_rate"] * 100
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Performance benchmark — frame rate, jitter, and reliability over time"
    )
    add_common_args(ap)
    ap.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_S,
        help=f"Run duration in seconds (default: {DEFAULT_DURATION_S:.0f})",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("=" * 60)
    logger.info("Scenario: Performance benchmark")
    logger.info("=" * 60)
    logger.info("  Stand or move naturally in the room.")
    logger.info("  Running for %.0f seconds (%.1f min).", args.duration, args.duration / 60)
    logger.info("  Status lines print every 10 seconds.")
    logger.info("=" * 60)
    input("Press Enter when ready...")
    for i in range(5, 0, -1):
        logger.info("Starting in %d...", i)
        time.sleep(1)

    radar = build_radar(args)
    try:
        results = run(radar, args.duration)
    finally:
        radar.stop()

    print_summary(results)


if __name__ == "__main__":
    main()
