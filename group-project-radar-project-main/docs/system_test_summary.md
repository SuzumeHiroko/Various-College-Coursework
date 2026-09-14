# System-Level Hardware Test Summary — mmWave Radar Node

**Sprint:** 6
**Tester:** Daniel Gebran
**Date:** 2026-04-17
**Hardware under test:** IWR6843AOP EVM + Raspberry Pi Zero 2W + TP4056 module + 18650 Li-ion cell
**Software:** `src/radar/radar_interface.py` (`__main__` block), `src/radar/profile_3d.cfg`

---

## Overview

This document records the four system-level hardware acceptance tests required to close Sprint 6 Task D3. Tests validate the integrated node — radar, Pi, OTG cable, and battery — as a working unit. Each test is independent and recorded as it is run.

| Test | Description | Status |
|------|-------------|--------|
| T1 | Radar ↔ Pi OTG communication | **PASS** |
| T2 | Battery provides stable power to Pi | Pending |
| T3 | Battery charges via TP4056 while Pi+EVM running | Pending |
| T4 | Pi connects to external display without issue | Pending |

**Done when:** All four tests pass.

---

## T1 — Radar OTG Communication

**Date/time:** 2026-04-17 ~00:46
**Command:**
```
python src/radar/radar_interface.py \
    --data-port <data port> \
    --config-port <config port> \
    --cfg-file src/radar/profile_3d.cfg
```

**Result: PASS**

### Observations

Frames arrived steadily at 10 Hz over the OTG connection. `is_healthy()` returned `True` on all frames after the startup window cleared.

| Metric | Value |
|--------|-------|
| First healthy frame observed | Frame 52 |
| Startup "not healthy" window | ~0.4 s (00:46:35.801 – 00:46:36.260) |
| Not-healthy warnings at startup | ~9 |
| `is_healthy()` after startup | `True` on all subsequent frames |
| Points per frame | 0 (expected — empty room, `clutterRemoval` enabled) |
| Frame interval | ~100 ms (10 Hz, consistent with `profile_3d.cfg`) |
| `sync_losses` at first healthy frame | 5 |
| `sync_losses` trend | Stable at 5 across all visible frames — no new losses after startup |

### Startup behavior

The radar reported `Radar not healthy — no fresh data` for ~0.4 s after `run()` was called. This is normal: the controller sends the `.cfg` commands, the radar reinitializes, and the data UART begins outputting frames after a brief startup window. First frame (frame 52) arrived at 00:46:36.260 and `is_healthy()` became `True` immediately.

Frame 52 (rather than frame 1) indicates the radar firmware had already been running and counting frames before the software connected — consistent with prior test sessions.

### sync_losses note

`sync_losses=5` at startup is slightly elevated compared to the dev-machine USB path (0–1 sync losses per session observed in prior tests). All 5 losses occurred during the startup/config window before frame 52. No new sync losses were observed across frames 52–66 (the visible window), indicating the OTG UART path is stable once initialized.

This is consistent with the startup TLV truncation events documented in `baseline_test_summary.md` and `performance_test_summary.md` — rare stream misalignments during the initialization window that self-recover without data loss.

### Pass criteria

- [x] Frames arrive over OTG connection
- [x] `is_healthy()` returns `True` after startup
- [x] No sync losses after startup window
- [x] Frame rate consistent with 10 Hz profile

---

## T2 — Battery Power Stability

**Date/time:** _pending_
**Procedure:** Boot Pi from battery only (TP4056 VOUT, set to 5.0 V). Run radar interface for ≥5 minutes. Pi must not reset; frames must flow continuously.

**Result: PENDING**

| Metric | Value |
|--------|-------|
| VOUT measured before connecting | — |
| Run duration | — |
| Frames received | — |
| Resets / power interruptions | — |
| Outcome | — |

---

## T3 — Battery Charging Under Load

**Date/time:** _pending_
**Procedure:** With Pi + EVM running on battery, plug charging cable into TP4056 IN+/IN−. Observe: Pi does not reset, TP4056 charge LED indicates charging, radar continues producing frames.

**Result: PENDING**

| Metric | Value |
|--------|-------|
| Pi reset on charger plug-in | — |
| TP4056 charge LED active | — |
| Radar frames continue during charging | — |
| Outcome | — |

---

## T4 — External Display

**Date/time:** _pending_
**Procedure:** Connect micro-HDMI adapter + monitor to Pi while running. Verify display output.

**Result: PENDING**

| Metric | Value |
|--------|-------|
| Display output present | — |
| Artifacts / blank screen | — |
| Outcome | — |

---

## Conclusion

_To be completed when all four tests pass._
