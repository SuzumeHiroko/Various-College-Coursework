# Stress Test Results — mmWave Radar Node

## Test Configuration

| Field | Value |
|-------|-------|
| Tool | `tests/radar_interface/test_performance.py` (custom benchmark) |
| Duration | 300 s (5 minutes) |
| Load | Sustained radar streaming at configured frame rate (10 Hz) |
| Target | `RadarController` UART reader → `PointCloudStreamer` TCP stream |
| Config file | `src/radar/profile_3d.cfg` |
| Data port | `/dev/tty.usbserial-011D1B5A1` @ 921600 baud |

**Hardware/IoT note:** This project has no HTTP endpoints or concurrent users. "Load" is defined as continuous high-throughput UART frame ingestion at 921600 baud sustained over 5 minutes (~3,000 frames). The bottleneck under test is the serial-to-frame parsing pipeline and TCP streaming layer, not a web server.

---

## Results

| Metric | Value |
|--------|-------|
| Frames emitted by radar | ~3,006 |
| Frames received by software | 2,999 |
| Measured frame rate | **10.00 Hz** |
| Mean inter-frame interval | 100.0 ms |
| Inter-frame jitter (std dev) | 5.9 ms |
| Min inter-frame interval | 80.8 ms |
| Max inter-frame interval | 190.0 ms (1 drop event) |
| Frame delivery rate | **99.97%** |
| Dropped frames | 1 (0.033%) |
| Sync losses | 1 (0.03%) |
| TLV corruption events | 1 (self-recovered < 1 frame period) |
| Time to recovery after drop | < 100 ms |

---

## Observations

### What we learned

- The radar interface sustains exactly 10.00 Hz over a 5-minute run with no drift. The frame rate is hardware-locked by `profile_3d.cfg` and does not degrade under continuous operation.
- 99.97% frame delivery rate confirms the parsing and TCP streaming pipeline can handle the full 921600 baud rate without falling behind.
- The single drop event at t≈60s was caused by a TLV stream misalignment (garbage bytes parsed as a 2.7 GB payload declaration). The parser detected the corruption, discarded the frame, re-acquired magic-word sync, and resumed normal operation within one frame period. Zero additional events occurred in the remaining 240 seconds (~2,400 frames).

### Where the bottlenecks are

- **USB-UART throughput:** The 921600 baud data port is the primary throughput constraint. On the development machine (Mac), this is handled comfortably. On the Raspberry Pi Zero 2W (single-core, 1 GHz), USB OTG throughput and Python global interpreter lock contention under the background reader thread are the expected bottlenecks, which have not been validated yet under full system load.
- **TLV corruption at startup:** One corruption event occurs per extended session, consistently in the first ~60 seconds. This is likely a serial buffer alignment issue at startup, not a sustained load problem.
- **TCP streaming:** `PointCloudStreamer` drops frames silently when no client is connected and uses non-blocking sends. Under the current single-client design, TCP could cause frame drops if the client's network or rendering falls behind. Not yet measured.

### What we would optimize

- Run the full benchmark on the Raspberry Pi Zero 2W to measure actual CPU headroom and validate that the Pi's USB-OTG path sustains 10 Hz under load.
- Instrument the TCP streaming layer to measure end-to-end latency (radar frame emitted → rendered on client).
- Add a startup flush (discard first 5 frames) to eliminate the startup TLV corruption events, as suggested by baseline and correctness test findings.

---

## Full Test Report

See [`docs/performance_test_summary.md`](../performance_test_summary.md) for the complete run log, jitter analysis, and frame count breakdown.
