import json
import os
from typing import Dict, Any


class DataLogger:
    """JSONL logger for radar sensor data (one JSON object per line)."""

    def __init__(self):
        self.file_path = None
        self._file_handle = None
        self._is_open = False

    def create(self, name: str) -> "DataLogger":
        """Create/open a JSONL log file. Overwrites if exists."""
        if self._is_open:
            raise RuntimeError("Logger already open, call close() first")

        # Add .jsonl extension if needed
        if not name.endswith(".jsonl"):
            name += ".jsonl"

        # Ensure directory exists
        dir_path = os.path.dirname(name)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        self.file_path = name
        self._file_handle = open(name, "w")
        self._is_open = True

        return self

    def write(self, data: Dict[str, Any]) -> None:
        """Append a dict as a JSON line."""
        if not self._is_open:
            raise RuntimeError("Logger not open")

        # Write as single line JSON
        self._file_handle.write(json.dumps(data) + "\n")
        self._file_handle.flush()  # Ensure it's written immediately

    def close(self) -> None:
        """Close the log file."""
        if not self._is_open:
            return

        if self._file_handle:
            self._file_handle.close()

        self._is_open = False
        self.file_path = None
        self._file_handle = None

    def __enter__(self) -> "DataLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._is_open:
            self.close()
