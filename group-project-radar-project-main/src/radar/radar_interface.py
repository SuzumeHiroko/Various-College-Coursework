"""
IWR6843AOP EVM UART Interface for Raspberry Pi Zero 2 W

Reference: TI mmWave SDK xwr68xx mmw demo documentation (mmwavedemo.html)
"""

import glob
import struct
import serial
import time
import threading
import logging
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants from TI mmWave SDK (mmw_output.h)
# ---------------------------------------------------------------------------

# Magic word: {0x0102, 0x0304, 0x0506, 0x0708} stored little-endian
MAGIC_WORD = b"\x02\x01\x04\x03\x06\x05\x08\x07"

HEADER_SIZE = 40  # bytes (magic word + 8 x uint32)

# TLV type IDs
TLV_DETECTED_POINTS = 1  # MMWDEMO_OUTPUT_MSG_DETECTED_POINTS
TLV_RANGE_PROFILE = 2  # MMWDEMO_OUTPUT_MSG_RANGE_PROFILE
TLV_NOISE_PROFILE = 3  # MMWDEMO_OUTPUT_MSG_NOISE_PROFILE
TLV_AZIMUTH_HEATMAP = 4  # MMWDEMO_OUTPUT_MSG_AZIMUT_STATIC_HEAT_MAP
TLV_DOPPLER_HEATMAP = 5  # MMWDEMO_OUTPUT_MSG_RANGE_DOPPLER_HEAT_MAP
TLV_STATS = 6  # MMWDEMO_OUTPUT_MSG_STATS
TLV_SIDE_INFO = 7  # MMWDEMO_OUTPUT_MSG_DETECTED_POINTS_SIDE_INFO
TLV_TEMPERATURE = 9  # MMWDEMO_OUTPUT_MSG_TEMPERATURE_STATS

# Struct sizes
POINT_SIZE = 16  # DPIF_PointCloudCartesian_t: 4 floats (x, y, z, velocity)
SIDE_INFO_SIZE = 4  # DPIF_PointCloudSideInfo_t: 2 x uint16 (SNR, noise)
STATS_SIZE = 24  # MmwDemo_output_message_stats_t: 6 x uint32
TEMP_SIZE = 28  # MmwDemo_temperatureStats_t

# Configuration constants
MAGIC_WORD_SYNC_CHUNK_SIZE = 1024  # Read buffer size for sync optimization
MAGIC_WORD_SYNC_MAX_BYTES = 2 * 65536  # Max bytes to scan for sync
SENSOR_START_DELAY_SECONDS = 0.5  # Config processing delay
THREAD_JOIN_TIMEOUT_SECONDS = 3.0  # Thread shutdown timeout
PAYLOAD_SIZE_MAX = 65536  # Max valid payload size
POLL_RATE_SLEEP_SECONDS = 0.05  # Main loop poll interval
RECONNECT_STALE_SECONDS = 5.0  # Seconds with no frames before forcing reconnect
RECONNECT_RETRY_INTERVAL_SECONDS = 2.0  # Pause between reconnect attempts


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RadarFrame:
    """
    One complete radar output frame.

    Attributes:
        timestamp:    Local receive time (time.time()) when frame was parsed.
        point_cloud:  List of [x, y, z] coordinate lists (meters).
                      x = lateral, y = depth, z = height.
        velocities:   Radial velocity per point (m/s). Same length as point_cloud.
        snr:          Signal-to-noise ratio per point (dB). Same length as point_cloud.
        noise:        Noise variance per point (dB). Same length as point_cloud.
        frame_number: Sequence number from the radar (monotonically increasing).
        stats:        Per-frame DSP timing and CPU load from TLV 6, or None if
                      not present. Keys: inter_frame_processing_time_us,
                      transmit_output_time_us, inter_frame_processing_margin_us,
                      inter_chirp_processing_margin_us, active_frame_cpu_load_pct,
                      inter_frame_cpu_load_pct.
    """

    timestamp: float = 0.0
    point_cloud: List[List[float]] = field(default_factory=list)
    velocities: List[float] = field(default_factory=list)
    snr: List[float] = field(default_factory=list)
    noise: List[float] = field(default_factory=list)
    frame_number: int = 0
    stats: Optional[dict] = None


# ---------------------------------------------------------------------------
# TLV Parser (internal)
# ---------------------------------------------------------------------------


class _TLVParser:
    """
    Parses the binary TLV output packet from the IWR6843AOP mmWave demo.

    Internal to this module — RadarController uses this to convert raw UART
    bytes into RadarFrame objects.
    """

    @staticmethod
    def parse_header(data: bytes) -> Optional[dict]:
        """
        Parse the 40-byte frame header.

        Header layout (all little-endian uint32 after magic word):
            Offset  Field
            0       Magic word (8 bytes)
            8       Version
            12      Total packet length (bytes, including header)
            16      Platform
            20      Frame number
            24      Time (CPU cycles)
            28      Num detected objects
            32      Num TLVs
            36      Subframe number
        """
        if len(data) < HEADER_SIZE:
            return None

        if data[0:8] != MAGIC_WORD:
            return None

        (
            version,
            total_length,
            platform,
            frame_number,
            time_cpu_cycles,
            num_detected,
            num_tlvs,
            subframe_number,
        ) = struct.unpack_from("<8I", data, offset=8)

        return {
            "version": version,
            "total_length": total_length,
            "platform": platform,
            "frame_number": frame_number,
            "time_cpu_cycles": time_cpu_cycles,
            "num_detected": num_detected,
            "num_tlvs": num_tlvs,
            "subframe_number": subframe_number,
        }

    @staticmethod
    def parse_tlvs(data: bytes, num_tlvs: int, num_detected: int) -> dict:
        """
        Parse TLV blocks from the payload following the header.

        Returns dict with keys: 'points', 'side_info', 'stats'
        """
        result = {
            "points": [],
            "side_info": [],
            "stats": None,
        }

        offset = 0
        for _ in range(num_tlvs):
            if offset + 8 > len(data):
                logger.warning("TLV data truncated at offset %d", offset)
                break

            tlv_type, tlv_length = struct.unpack_from("<2I", data, offset)
            offset += 8

            if offset + tlv_length > len(data):
                logger.warning(
                    "TLV payload truncated: type=%d, declared=%d, available=%d",
                    tlv_type,
                    tlv_length,
                    len(data) - offset,
                )
                break

            payload = data[offset : offset + tlv_length]

            if tlv_type == TLV_DETECTED_POINTS:
                result["points"] = _TLVParser._parse_detected_points(payload, num_detected)

            elif tlv_type == TLV_SIDE_INFO:
                result["side_info"] = _TLVParser._parse_side_info(payload, num_detected)

            elif tlv_type == TLV_STATS:
                result["stats"] = _TLVParser._parse_stats(payload)

            # TLV types 2-5, 9: silently skip (disabled in our guiMonitor config)

            offset += tlv_length

        return result

    @staticmethod
    def _parse_detected_points(payload: bytes, num_points: int) -> list:
        """Parse TLV type 1: array of DPIF_PointCloudCartesian_t (16 bytes each)."""
        points = []
        for i in range(num_points):
            start = i * POINT_SIZE
            if start + POINT_SIZE > len(payload):
                break
            x, y, z, velocity = struct.unpack_from("<4f", payload, start)
            points.append((x, y, z, velocity))
        return points

    @staticmethod
    def _parse_side_info(payload: bytes, num_points: int) -> list:
        """Parse TLV type 7: array of DPIF_PointCloudSideInfo_t (4 bytes each)."""
        info = []
        for i in range(num_points):
            start = i * SIDE_INFO_SIZE
            if start + SIDE_INFO_SIZE > len(payload):
                break
            snr, noise = struct.unpack_from("<2H", payload, start)
            # Values are in 0.1 dB units per TI SDK
            info.append((snr * 0.1, noise * 0.1))
        return info

    @staticmethod
    def _parse_stats(payload: bytes) -> Optional[dict]:
        """Parse TLV type 6: MmwDemo_output_message_stats_t (24 bytes)."""
        if len(payload) < STATS_SIZE:
            return None
        ifp_time, tx_time, ifp_margin, icp_margin, active_cpu, interframe_cpu = struct.unpack_from(
            "<6I", payload
        )
        return {
            "inter_frame_processing_time_us": ifp_time,
            "transmit_output_time_us": tx_time,
            "inter_frame_processing_margin_us": ifp_margin,
            "inter_chirp_processing_margin_us": icp_margin,  # always 0
            "active_frame_cpu_load_pct": active_cpu,
            "inter_frame_cpu_load_pct": interframe_cpu,
        }


# ---------------------------------------------------------------------------
# Port auto-detection
# ---------------------------------------------------------------------------


def detect_radar_ports() -> Tuple[str, str]:
    """
    Auto-detect /dev/ttyUSB* ports for the IWR6843AOP EVM.

    Scans available /dev/ttyUSB* devices, sorts by numeric suffix, and picks
    the two with the lowest numbers. Per TI EVM wiring: the lower-numbered
    port is the config (CLI) port and the higher-numbered port is the data port.

    Returns:
        (config_port, data_port) — e.g. ('/dev/ttyUSB0', '/dev/ttyUSB1')

    Raises:
        RuntimeError: if fewer than 2 /dev/ttyUSB* ports are found.
    """
    ports = sorted(
        glob.glob("/dev/ttyUSB*"),
        key=lambda p: int(p[len("/dev/ttyUSB"):]),
    )
    if len(ports) < 2:
        raise RuntimeError(
            f"Auto-detection requires at least 2 /dev/ttyUSB* ports; found: {ports or 'none'}"
        )
    config_port, data_port = ports[0], ports[1]
    logger.info("Auto-detected radar ports: config=%s, data=%s", config_port, data_port)
    return config_port, data_port


# ---------------------------------------------------------------------------
# Radar Controller
# ---------------------------------------------------------------------------


class RadarController:
    """
    Non-blocking interface between Raspberry Pi and IWR6843AOP EVM.

    A background thread continuously reads UART frames from the radar and
    caches the latest one. The main thread can poll for new data without
    ever blocking on serial I/O.

    The EVM exposes two USB-UART ports:
      - Config port (first/lower):  CLI commands at 115200 baud
      - Data port (second/higher):  binary TLV output at 921600 baud

    Usage:
        radar = RadarController(
            data_port='/dev/ttyUSB1',
            config_port='/dev/ttyUSB0',
            cfg_file='profile_3d.cfg',
        )
        radar.run()

        while True:
            if radar.is_available():
                frame = radar.read()
                print(f"{len(frame.point_cloud)} points at t={frame.timestamp:.3f}")

            if not radar.is_healthy():
                print("WARNING: no new frame in >0.5s")
    """

    def __init__(
        self,
        data_port: str = None,
        config_port: str = None,
        cfg_file: str = None,
        data_baud: int = 921600,
        config_baud: int = 115200,
        stale_threshold: float = 0.5,
    ):
        """
        Args:
            data_port:        Serial device for radar data output. If None,
                              auto-detected from /dev/ttyUSB* (higher number).
            config_port:      Serial device for CLI commands. If None and
                              data_port is also None, auto-detected (lower number).
                              Pass None explicitly with a data_port to skip config.
            cfg_file:         Path to .cfg file to send at startup. None to skip.
            data_baud:        Baud rate for data port (921600 recommended).
            config_baud:      Baud rate for config port (always 115200 per TI SDK).
            stale_threshold:  Seconds before is_healthy() returns False.
        """
        self._data_port = data_port
        self._config_port = config_port
        self._cfg_file = cfg_file
        self._data_baud = data_baud
        self._config_baud = config_baud
        self._stale_threshold = stale_threshold

        self._parser = _TLVParser()

        # Shared state between reader thread and main thread
        self._lock = threading.Lock()
        self._latest_frame: Optional[RadarFrame] = None
        self._new_frame_available = False
        self._frame_count = 0
        self._sync_loss_count = 0

        self._stop_event = threading.Event()  # Thread-safe shutdown signal
        self._thread: Optional[threading.Thread] = None
        self._data_serial: Optional[serial.Serial] = None
        self._config_serial: Optional[serial.Serial] = None
        self._leftover: bytes = b""  # Bytes already pulled from serial, not yet consumed

    # -- Public API ----------------------------------------------------------

    def run(self):
        """
        Open serial ports, send config, and start the background reader thread.

        Call this once. The background thread will run until stop() is called.
        """
        try:
            # Auto-detect ports if not explicitly provided
            if self._data_port is None:
                self._config_port, self._data_port = detect_radar_ports()

            # Open data port
            self._data_serial = serial.Serial(
                port=self._data_port,
                baudrate=self._data_baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
            )

            # Open config port and send .cfg file if provided
            if self._config_port:
                self._config_serial = serial.Serial(
                    port=self._config_port,
                    baudrate=self._config_baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.0,
                )

            if self._cfg_file and self._config_serial:
                self._send_config(self._cfg_file)
                time.sleep(SENSOR_START_DELAY_SECONDS)  # let radar process sensorStart

            # Launch background reader
            self._stop_event.clear()  # Start running
            self._thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._thread.start()
            logger.info(
                "RadarController started (data=%s, baud=%d)", self._data_port, self._data_baud
            )
        except Exception:
            # Cleanup on failure
            if self._data_serial:
                self._data_serial.close()
                self._data_serial = None
            if self._config_serial:
                self._config_serial.close()
                self._config_serial = None
            raise  # Re-raise original exception

    def read(self) -> Optional[RadarFrame]:
        """
        Return the latest radar frame and clear the new-frame flag.

        Does not block. Returns None if no frame has been received yet.
        """
        with self._lock:
            self._new_frame_available = False
            return self._latest_frame

    def is_available(self) -> bool:
        """True if a new frame has arrived since the last read() call."""
        with self._lock:
            return self._new_frame_available

    def is_healthy(self) -> bool:
        """
        True if the radar is producing fresh data.

        Returns False if no frame has ever been received, or if the latest
        frame timestamp is older than stale_threshold (default 0.5s).
        """
        with self._lock:
            if self._latest_frame is None:
                return False
            age = time.time() - self._latest_frame.timestamp
            return age < self._stale_threshold

    def dimensions(self) -> Optional[dict]:
        """
        Return the spatial extent of the latest point cloud.

        Returns dict with min/max for each axis, or None if no points.
        Useful for understanding the 3D bounding box of current detections.
        """
        with self._lock:
            if self._latest_frame is None or not self._latest_frame.point_cloud:
                return None
            # Explicit copy for thread safety
            cloud = list(self._latest_frame.point_cloud)

        # Defensive check
        if not cloud:
            return None

        # Single-pass transpose instead of three iterations
        xs, ys, zs = zip(*cloud)

        return {
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
            "z_min": min(zs),
            "z_max": max(zs),
            "num_points": len(cloud),
        }

    def stop(self):
        """Stop the background reader thread and close serial ports."""
        self._stop_event.set()  # Signal thread to stop
        if self._thread:
            self._thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            if self._thread.is_alive():
                logger.warning(
                    "Background thread did not stop within %d seconds", THREAD_JOIN_TIMEOUT_SECONDS
                )
        if self._data_serial:
            self._data_serial.close()
        if self._config_serial:
            self._config_serial.close()
        logger.info(
            "RadarController stopped (frames=%d, sync_losses=%d)",
            self._frame_count,
            self._sync_loss_count,
        )

    @property
    def frame_count(self) -> int:
        """Total number of frames successfully parsed since run()."""
        with self._lock:
            return self._frame_count

    @property
    def sync_loss_count(self) -> int:
        """Number of times the parser had to re-sync to the magic word."""
        with self._lock:
            return self._sync_loss_count

    # -- Background reader thread --------------------------------------------

    def _reader_loop(self):
        """Continuously read and parse UART frames. Runs in background thread."""
        last_frame_time = time.time()
        while not self._stop_event.is_set():
            try:
                frame = self._read_one_frame()
                if frame is not None:
                    last_frame_time = time.time()
                    with self._lock:
                        self._latest_frame = frame
                        self._new_frame_available = True
                        self._frame_count += 1
                elif time.time() - last_frame_time > RECONNECT_STALE_SECONDS:
                    logger.warning(
                        "No radar frames for %.1fs — reconnecting",
                        time.time() - last_frame_time,
                    )
                    self._reconnect()
                    last_frame_time = time.time()
            except serial.SerialException as e:
                logger.error("Serial error: %s — reconnecting", e)
                self._reconnect()
                last_frame_time = time.time()
            except Exception as e:
                logger.error("Unexpected error in reader thread: %s", e)
                time.sleep(0.1)

    def _reconnect(self):
        """Close serial ports, rescan /dev/ttyUSB*, and reopen with config."""
        logger.info("Radar reconnect: closing ports")
        for ser in (self._data_serial, self._config_serial):
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
        self._data_serial = None
        self._config_serial = None
        self._leftover = b""

        while not self._stop_event.is_set():
            time.sleep(RECONNECT_RETRY_INTERVAL_SECONDS)
            try:
                config_port, data_port = detect_radar_ports()
                self._data_serial = serial.Serial(
                    port=data_port,
                    baudrate=self._data_baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.0,
                )
                self._config_serial = serial.Serial(
                    port=config_port,
                    baudrate=self._config_baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.0,
                )
                if self._cfg_file:
                    self._send_config(self._cfg_file)
                    time.sleep(SENSOR_START_DELAY_SECONDS)
                self._data_port = data_port
                self._config_port = config_port
                logger.info("Radar reconnected: config=%s  data=%s", config_port, data_port)
                return
            except Exception as e:
                logger.warning(
                    "Reconnect attempt failed (%s) — retrying in %.0fs",
                    e,
                    RECONNECT_RETRY_INTERVAL_SECONDS,
                )

    def _sync_to_magic_word(self, ser, initial_buf: bytes) -> Optional[tuple]:
        """
        Find MAGIC_WORD in serial stream using optimized chunked reading.

        Reads MAGIC_WORD_SYNC_CHUNK_SIZE bytes at a time and searches within
        each chunk using bytes.find(). Handles magic word split across chunk
        boundaries by keeping last 7 bytes from each chunk.

        Args:
            ser: Serial port object
            initial_buf: Initial 8 bytes already read (known NOT to be magic word)

        Returns:
            (MAGIC_WORD, bytes_discarded, timestamp) if found
            None if not found within MAGIC_WORD_SYNC_MAX_BYTES or timeout
        """
        max_bytes = MAGIC_WORD_SYNC_MAX_BYTES

        # Accumulator buffer for searching
        search_buf = initial_buf
        bytes_already_discarded = 0

        while bytes_already_discarded < max_bytes:
            # Search for magic word in current buffer
            pos = search_buf.find(MAGIC_WORD)

            if pos != -1:
                # Found it!
                total_discarded = bytes_already_discarded + pos
                receive_time = time.time()
                return (MAGIC_WORD, total_discarded, receive_time, search_buf[pos + 8 :])

            # Not found - discard all but last 7 bytes (for boundary case)
            if len(search_buf) > 7:
                bytes_to_discard = len(search_buf) - 7
                search_buf = search_buf[-7:]
                bytes_already_discarded += bytes_to_discard

            # Read next chunk
            chunk = ser.read(MAGIC_WORD_SYNC_CHUNK_SIZE)
            if not chunk:
                # Serial timeout
                return None

            search_buf = search_buf + chunk

        # Exceeded max bytes
        logger.error("Could not find magic word after %d bytes", bytes_already_discarded)
        with self._lock:
            self._sync_loss_count += 1
        return None

    def _buf_read(self, ser, n: int) -> bytes:
        """Read n bytes, draining self._leftover before the serial port."""
        if len(self._leftover) >= n:
            data = self._leftover[:n]
            self._leftover = self._leftover[n:]
            return data
        data = self._leftover
        self._leftover = b""
        data += ser.read(n - len(data))
        return data

    def _read_one_frame(self) -> Optional[RadarFrame]:
        """
        Read and parse one complete radar frame from the data port.

        Scans the UART stream for the 8-byte magic word, reads the header,
        then reads the TLV payload. Returns None on timeout or parse error.
        """
        ser = self._data_serial

        # Fast path: read 8 bytes and check if it's magic word
        buf = self._buf_read(ser, 8)
        if len(buf) < 8:
            return None

        if buf == MAGIC_WORD:
            # Already aligned - common case
            receive_time = time.time()
            bytes_scanned = 0
        else:
            # Need to sync
            sync_result = self._sync_to_magic_word(ser, buf)
            if sync_result is None:
                return None
            magic_buf, bytes_scanned, receive_time, leftover = sync_result
            buf = magic_buf
            self._leftover = leftover  # persist bytes after magic word for subsequent reads

            # Track sync event
            logger.debug("Re-synced after %d bytes", bytes_scanned)
            with self._lock:
                self._sync_loss_count += 1

        # Read remaining header (32 bytes after magic)
        header_rest = self._buf_read(ser, HEADER_SIZE - 8)
        if len(header_rest) < HEADER_SIZE - 8:
            return None

        header = self._parser.parse_header(MAGIC_WORD + header_rest)
        if header is None:
            return None

        # Read TLV payload
        payload_size = header["total_length"] - HEADER_SIZE
        if payload_size < 0 or payload_size > PAYLOAD_SIZE_MAX:
            logger.warning("Invalid payload size: %d", payload_size)
            return None

        payload = b""
        if payload_size > 0:
            payload = self._buf_read(ser, payload_size)
            if len(payload) < payload_size:
                logger.warning("Payload truncated: expected %d, got %d", payload_size, len(payload))
                return None

        # Parse TLVs
        tlv_data = self._parser.parse_tlvs(payload, header["num_tlvs"], header["num_detected"])

        # Build RadarFrame with point_cloud as List[List[float]]
        point_cloud = []
        velocities = []
        snr_list = []
        noise_list = []

        for (x, y, z, vel), side in zip_longest(
            tlv_data["points"], tlv_data["side_info"], fillvalue=(0.0, 0.0)
        ):
            point_cloud.append([x, y, z])
            velocities.append(vel)
            snr_list.append(side[0])  # SNR in dB (0.0 if side_info shorter)
            noise_list.append(side[1])  # Noise variance in dB (0.0 if side_info shorter)

        return RadarFrame(
            timestamp=receive_time,
            point_cloud=point_cloud,
            velocities=velocities,
            snr=snr_list,
            noise=noise_list,
            frame_number=header["frame_number"],
            stats=tlv_data["stats"],
        )

    # -- Config sender -------------------------------------------------------

    def _send_config(self, cfg_path: str, delay: float = 0.03):
        """Send a .cfg file line-by-line to the radar config port."""
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("%"):
                    continue
                self._config_serial.write((line + "\n").encode("ascii"))
                logger.debug("Sent config: %s", line)
                time.sleep(delay)
        logger.info("Configuration sent from %s", cfg_path)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="IWR6843AOP radar UART reader")
    ap.add_argument("--data-port", required=True, help="Data UART (e.g. /dev/ttyUSB1)")
    ap.add_argument("--config-port", default=None, help="Config UART (e.g. /dev/ttyUSB0)")
    ap.add_argument("--cfg-file", default=None, help=".cfg file to send at startup")
    ap.add_argument("--data-baud", type=int, default=921600)
    ap.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0=run forever)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    radar = RadarController(
        data_port=args.data_port,
        config_port=args.config_port,
        cfg_file=args.cfg_file,
        data_baud=args.data_baud,
    )
    radar.run()

    try:
        while True:
            if radar.is_available():
                frame = radar.read()
                n = len(frame.point_cloud)
                logger.info(
                    "Frame %5d | %3d points | healthy=%s | sync_losses=%d",
                    frame.frame_number,
                    n,
                    radar.is_healthy(),
                    radar.sync_loss_count,
                )

                for pt in frame.point_cloud[:3]:
                    logger.info("  x=%+6.2f  y=%+6.2f  z=%+6.2f", pt[0], pt[1], pt[2])
                if n > 3:
                    logger.info("  ... and %d more", n - 3)

                dims = radar.dimensions()
                if dims:
                    logger.info(
                        "  bounds: x=[%.2f, %.2f] y=[%.2f, %.2f] z=[%.2f, %.2f]",
                        dims["x_min"],
                        dims["x_max"],
                        dims["y_min"],
                        dims["y_max"],
                        dims["z_min"],
                        dims["z_max"],
                    )

                if args.max_frames and radar.frame_count >= args.max_frames:
                    break

            elif not radar.is_healthy():
                logger.warning("Radar not healthy — no fresh data")

            time.sleep(POLL_RATE_SLEEP_SECONDS)  # 20 Hz poll rate, avoids busy-waiting

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        radar.stop()
