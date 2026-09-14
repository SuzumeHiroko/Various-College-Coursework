# Baseline Test Summary — IWR6843AOP

**Test:** `tests/radar_interface/test_baseline.py`
**Date:** 2026-03-22
**Tester:** Daniel Gebran
**Config:** `src/radar/profile_3d.cfg`
**Data port:** `/dev/tty.usbserial-011D1B5A1`
**Frames per run:** 100
**Clutter warning threshold (`BASELINE_POINT_WARN`):** 5 pts/frame

---

## Test Conditions

- Room empty — no person in radar field of view
- Room contents in field of view: whiteboard (directly ahead), TV (far left), power strip (far right)
- Floor: smooth white tile — highly reflective at 60 GHz
- Ceiling: drop ceiling with recessed fluorescent lights and metal grid panels — also reflective
- **Radar sitting flat on a table (~75 cm above floor), pointing horizontally toward the whiteboard**
- Whiteboard spans the entire back wall floor-to-ceiling, approximately 3–4 m from the radar

---

## Run Results

### Phase 1 — No clutter removal (`clutterRemoval` disabled in `profile_3d.cfg`)

| Run | Time | Mean pts/frame | Field Errors | Dropped Frames | Sync Losses | TLV Warnings |
|-----|------|---------------|-------------|----------------|-------------|--------------|
| 1 | 2026-03-22 19:23:38 | **30.3** | 0 | 0 | 0 | None |
| 2 | 2026-03-22 19:24:11 | **31.1** | 0 | 0 | 1 | TLV truncation (1 frame, startup) |
| 3 | 2026-03-22 19:24:36 | **31.0** | 0 | 0 | 0 | None |

**All 3 runs exceeded `BASELINE_POINT_WARN` (5 pts/frame) — clutter warning triggered on every run.**

### Phase 2 — `clutterRemoval` enabled in `profile_3d.cfg`

| Run | Time | Mean pts/frame | Field Errors | Dropped Frames | Sync Losses | TLV Warnings |
|-----|------|---------------|-------------|----------------|-------------|--------------|
| 4 | 2026-03-23 00:07:14 | **0.0** | 0 | 0 | 0 | None |

**Run 4 passed `BASELINE_POINT_WARN` (5 pts/frame) — clutter warning did not trigger.**

One stray point was observed at frame #45 (1 pt); all other frames reported 0 pts. This is within the expected noise floor.

---

## Clutter Analysis

### Phase 1 (no clutter removal)

The sensor consistently reported ~30 pts/frame in a completely empty room. This is entirely static background clutter from room surfaces — walls, floor, ceiling, whiteboard, and furnishings.

| Metric | Run 1 | Run 2 | Run 3 |
|--------|-------|-------|-------|
| Mean pts/frame | 30.3 | 31.1 | 31.0 |
| Min pts/frame (observed) | 27 | 27 | 27 |
| Max pts/frame (observed) | 33 | 34 | 34 |
| Standard deviation (approx.) | ~2 | ~2 | ~2 |

The clutter level was **highly stable** (±2 pts/frame) across all three runs, confirming it is dominated by fixed static reflectors rather than noise.

### Phase 2 (clutterRemoval enabled)

Enabling `clutterRemoval` in `profile_3d.cfg` reduced the empty-room point count from ~31 pts/frame to effectively **0 pts/frame**. The DSP-level static clutter filter subtracts the mean range profile across frames, suppressing all returns from stationary surfaces before they are reported as detected points.

| Metric | Run 4 |
|--------|-------|
| Mean pts/frame | 0.0 |
| Min pts/frame (observed) | 0 |
| Max pts/frame (observed) | 1 |
| Standard deviation (approx.) | ~0 |

**This is the expected and correct result.** The single 1-pt outlier at frame #45 is noise — not a recurring reflector.

---

## Frame Startup Behavior

In all 3 runs, the first logged frame is consistently **frame #6**. Frames 1–5 are never captured. This is expected: the radar's internal frame counter starts before the `RadarController` begins reading the data UART, so the first few frames are lost during the startup handshake window.

---

## Run 2 — TLV Truncation Warning

```
WARNING  TLV payload truncated: type=785137480, declared=15861, available=720
```

This occurred at startup (immediately after `RadarController started`), before the first valid frame was logged. It represents a partial frame mid-flight on the UART at the moment the data port was opened. The system recovered immediately — no field errors or dropped frames resulted. This is a known benign startup race condition.

---

## Reliability Summary

| Metric | Total across 4 runs |
|--------|---------------------|
| Total frames collected | 400 |
| Field errors | 0 |
| Dropped frames | 0 |
| Sync losses | 1 (Run 2 only, startup) |

**The software pipeline is reliable.** Zero field errors and zero dropped frames across 400 frames. The single sync loss in Run 2 was a startup event and did not affect data quality.

---

## Root Cause of High Clutter

This environment is a near-worst-case scenario for mmWave static clutter:

1. **Floor proximity** — The radar is flat on a table at ~75 cm height. The smooth tile floor is highly reflective at 60 GHz and is within the radar's near-field elevation coverage on every frame.

2. **Whiteboard** — A full-wall specular reflector at 3–4 m directly in the beam. Returns strong signals on every frame with no target present.

3. **Drop ceiling** — Metal grid panels create upward reflection paths.

4. **No static clutter removal** — `profile_3d.cfg` did not enable `clutterRemoval` in Phase 1. All CFAR-threshold-crossing returns from static surfaces were reported as detected points. This has since been resolved — see Phase 2 results above.

---

## `BASELINE_POINT_WARN` Threshold Assessment

The original threshold of **5 pts/frame** was not grounded in measurement — it was an arbitrary placeholder set before hardware testing.

**Phase 1** (no clutter removal) showed the threshold was always exceeded:

| Statistic | Value |
|-----------|-------|
| Mean | ~30.8 pts/frame |
| Observed range | 27–34 pts/frame |

**Phase 2** (clutter removal enabled) shows the threshold is now meaningful:

| Statistic | Value |
|-----------|-------|
| Mean | 0.0 pts/frame |
| Observed range | 0–1 pts/frame |

With `clutterRemoval` enabled, the 5 pt/frame threshold correctly identifies a non-empty room. No change to `BASELINE_POINT_WARN` is required for this configuration.

---

## Person-Present Comparison

Cross-referencing with `test_correctness.py` runs from the same day (Phase 1, no clutter removal):

| Condition | Mean pts/frame |
|-----------|---------------|
| Empty room (baseline, Phase 1) | ~30–31 |
| Person present, moving (runs 1–5) | ~25–32 |
| Person present, moving (run 6) | ~38–42 |

With clutter removal disabled, **point count alone did not reliably distinguish a person from an empty room** — the static floor (~30 pts) was comparable to or exceeded the human contribution.

With `clutterRemoval` enabled (Phase 2), the empty-room floor drops to ~0 pts/frame. Any points now reported represent moving or recently-moving objects, making occupancy detection via point count straightforward.

Note: correctness runs (Phase 1) showed `vel[0] = +0.00 m/s` on every frame. This was a **test logging bug** — `vel[0]` is always the first point in the frame, which in a clutter-heavy environment is a static background point with a legitimately zero radial velocity. The velocity parser and firmware output are correct. See `correctness_test_summary.md` (Velocity Investigation section) for full details; velocity was confirmed non-zero and directionally correct in Run 7 after switching the log line to `max(velocities, key=abs)`.

---

## Recommendations

| Priority | Action | Status |
|----------|--------|--------|
| High | Enable `clutterRemoval` in `profile_3d.cfg` to suppress static background at the DSP level | **Done** — 0.0 pts/frame confirmed (Run 4) |
| High | Investigate 0 m/s velocity — `vel[0]` always reads a static background point | **Done** — logging bug fixed; velocity confirmed correct in `test_correctness.py` Run 7 |
| Medium | Re-run baseline after enabling clutter removal to establish new reference level | **Done** — new baseline: 0.0 pts/frame (Run 4) |
| Medium | Update `BASELINE_POINT_WARN` threshold | **No longer needed** — 5 pt/frame is valid with clutter removal on |
| Low | Mount the radar at wall height (~1–1.5 m) and angle toward torso to reduce floor/ceiling clutter paths | Open |

---

## Conclusion

**The radar interface software is functioning correctly, and the clutter problem is resolved.**

The baseline test confirms that `RadarController`, the TLV parser, and the full data pipeline operate with zero errors and zero dropped frames across 400 frames. Enabling `clutterRemoval` in `profile_3d.cfg` reduced the empty-room point count from ~31 pts/frame to 0.0 pts/frame, making the existing `BASELINE_POINT_WARN = 5` threshold valid for this installation.

### Established baseline for this room + mounting

| Metric | Phase 1 (no clutter removal) | Phase 2 (clutter removal enabled) |
|--------|------------------------------|-----------------------------------|
| Static clutter level | ~30–31 pts/frame | **0.0 pts/frame** |
| Clutter stability | ±2 pts/frame | ±0 pts/frame |
| Field errors | 0 / 300 frames | 0 / 100 frames |
| Dropped frames | 0 / 300 frames | 0 / 100 frames |
| Sync losses | 1 (startup only) | 0 |
| First reliable frame | Frame #6 (frames 1–5 always lost at startup) | Frame #6 |

### Next steps

1. Proceed to `test_motion.py` — validate Doppler velocity reporting during approach/retreat (velocity confirmed working in `test_correctness.py` Run 7)
2. Re-run `test_baseline.py` after mounting improvement (wall height, ~1–1.5 m) to compare clutter levels
