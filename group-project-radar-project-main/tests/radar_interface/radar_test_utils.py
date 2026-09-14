"""
Shared utilities for radar interface live tests.

Provides:
  - Physical plausibility constants
  - validate_frame_fields() — per-frame field and stats validation
  - check_bounds()          — bounding box sanity check
  - inter_frame_stats()     — frame rate and jitter from timestamps
  - add_common_args()       — standard serial port argparse arguments
  - build_radar()           — construct and start a RadarController from args
"""

import math
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.radar.radar_interface import RadarController, RadarFrame  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plausible physical ranges for IWR6843AOP in a room environment
# ---------------------------------------------------------------------------

X_RANGE = (-5.0, 5.0)  # meters lateral
Y_RANGE = (0.0, 8.0)  # meters depth (radar never sees behind itself)
Z_RANGE = (-4.0, 4.0)  # meters height
VEL_RANGE = (-10.0, 10.0)  # m/s (human motion is well within ±5 m/s)
SNR_MIN = 0.0  # dB  (SNR is always non-negative)

# Room boundary warning thresholds (edit for your test environment)
ROOM_X_MAX = 3.0  # meters
ROOM_Y_MAX = 5.0  # meters
ROOM_Z_MAX = 3.5  # meters

# Baseline scenario: warn if mean points/frame exceeds this with an empty room
BASELINE_POINT_WARN = 5


# ---------------------------------------------------------------------------
# Per-frame validation
# ---------------------------------------------------------------------------


def validate_frame_fields(frame: RadarFrame) -> list[str]:
    """
    Check that every point has valid x, y, z, velocity, snr values,
    and that frame.stats (if present) contains sane DSP timing data.

    Returns a list of error strings (empty = frame passed).
    """
    errors = []
    n = len(frame.point_cloud)

    if len(frame.velocities) != n:
        errors.append(f"velocities length {len(frame.velocities)} != point_cloud length {n}")
    if len(frame.snr) != n:
        errors.append(f"snr length {len(frame.snr)} != point_cloud length {n}")

    for i, pt in enumerate(frame.point_cloud):
        if len(pt) != 3:
            errors.append(f"point[{i}] has {len(pt)} coords, expected 3")
            continue
        x, y, z = pt
        for name, val in (("x", x), ("y", y), ("z", z)):
            if not isinstance(val, float):
                errors.append(f"point[{i}].{name} is {type(val).__name__}, expected float")
        if not (X_RANGE[0] <= x <= X_RANGE[1]):
            errors.append(f"point[{i}].x={x:.2f} outside plausible range {X_RANGE}")
        if not (Y_RANGE[0] <= y <= Y_RANGE[1]):
            errors.append(f"point[{i}].y={y:.2f} outside plausible range {Y_RANGE}")
        if not (Z_RANGE[0] <= z <= Z_RANGE[1]):
            errors.append(f"point[{i}].z={z:.2f} outside plausible range {Z_RANGE}")

    for i, vel in enumerate(frame.velocities):
        if not isinstance(vel, float):
            errors.append(f"velocities[{i}] is {type(vel).__name__}, expected float")
        if not (VEL_RANGE[0] <= vel <= VEL_RANGE[1]):
            errors.append(f"velocities[{i}]={vel:.2f} outside plausible range {VEL_RANGE}")

    for i, snr_val in enumerate(frame.snr):
        if not isinstance(snr_val, float):
            errors.append(f"snr[{i}] is {type(snr_val).__name__}, expected float")
        if snr_val < SNR_MIN:
            errors.append(f"snr[{i}]={snr_val:.2f} is negative (should be >= 0 dB)")

    if frame.stats is not None:
        s = frame.stats
        expected_keys = (
            "inter_frame_processing_time_us",
            "transmit_output_time_us",
            "inter_frame_processing_margin_us",
            "inter_chirp_processing_margin_us",
            "active_frame_cpu_load_pct",
            "inter_frame_cpu_load_pct",
        )
        for key in expected_keys:
            if key not in s:
                errors.append(f"stats missing key '{key}'")
        for key in ("active_frame_cpu_load_pct", "inter_frame_cpu_load_pct"):
            if key in s and not (0 <= s[key] <= 100):
                errors.append(f"stats.{key}={s[key]} out of range [0, 100]")
        for key in (
            "inter_frame_processing_time_us",
            "transmit_output_time_us",
            "inter_frame_processing_margin_us",
        ):
            if key in s and s[key] < 0:
                errors.append(f"stats.{key}={s[key]} is negative")

    return errors


# ---------------------------------------------------------------------------
# Bounding box check
# ---------------------------------------------------------------------------


def check_bounds(frame: RadarFrame) -> dict | None:
    """
    Compute bounding box and warn if any axis exceeds expected room dimensions.
    Returns the dims dict, or None if the frame has no points.
    """
    if not frame.point_cloud:
        return None

    xs = [pt[0] for pt in frame.point_cloud]
    ys = [pt[1] for pt in frame.point_cloud]
    zs = [pt[2] for pt in frame.point_cloud]

    dims = {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
        "z_min": min(zs),
        "z_max": max(zs),
    }

    if abs(dims["x_min"]) > ROOM_X_MAX or abs(dims["x_max"]) > ROOM_X_MAX:
        logger.warning(
            "  [BOUNDS] x extent [%.2f, %.2f] exceeds room limit ±%.1fm "
            "— possible calibration issue",
            dims["x_min"],
            dims["x_max"],
            ROOM_X_MAX,
        )
    if dims["y_max"] > ROOM_Y_MAX:
        logger.warning(
            "  [BOUNDS] y_max=%.2f exceeds room depth %.1fm " "— possible calibration issue",
            dims["y_max"],
            ROOM_Y_MAX,
        )
    if abs(dims["z_min"]) > ROOM_Z_MAX or abs(dims["z_max"]) > ROOM_Z_MAX:
        logger.warning(
            "  [BOUNDS] z extent [%.2f, %.2f] exceeds room height limit ±%.1fm "
            "— possible calibration issue",
            dims["z_min"],
            dims["z_max"],
            ROOM_Z_MAX,
        )

    return dims


# ---------------------------------------------------------------------------
# Performance helpers
# ---------------------------------------------------------------------------


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def inter_frame_stats(timestamps: list[float]) -> dict:
    """Compute frame rate and jitter from a list of frame arrival timestamps."""
    if len(timestamps) < 2:
        return {
            "fps": 0.0,
            "interval_mean_ms": 0.0,
            "interval_std_ms": 0.0,
            "interval_min_ms": 0.0,
            "interval_max_ms": 0.0,
        }
    intervals_ms = [(timestamps[i] - timestamps[i - 1]) * 1000 for i in range(1, len(timestamps))]
    mean_ms = sum(intervals_ms) / len(intervals_ms)
    return {
        "fps": 1000.0 / mean_ms if mean_ms > 0 else 0.0,
        "interval_mean_ms": mean_ms,
        "interval_std_ms": _stdev(intervals_ms),
        "interval_min_ms": min(intervals_ms),
        "interval_max_ms": max(intervals_ms),
    }


# ---------------------------------------------------------------------------
# Argparse and RadarController helpers
# ---------------------------------------------------------------------------


def add_common_args(ap) -> None:
    """Add standard serial port arguments to an ArgumentParser."""
    ap.add_argument(
        "--data-port", required=True, help="Data UART port (e.g. /dev/tty.usbserial-011D1B5A1)"
    )
    ap.add_argument(
        "--config-port", default=None, help="Config UART port (e.g. /dev/tty.usbserial-011D1B5A0)"
    )
    ap.add_argument("--cfg-file", default=None, help=".cfg file to send to radar at startup")
    ap.add_argument("--data-baud", type=int, default=921600)


def build_radar(args) -> RadarController:
    """Construct and start a RadarController from parsed args."""
    radar = RadarController(
        data_port=args.data_port,
        config_port=args.config_port,
        cfg_file=args.cfg_file,
        data_baud=args.data_baud,
    )
    radar.run()
    return radar
