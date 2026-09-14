import json
import queue
import ssl
import threading
import time
from typing import Any, Optional, Union

import paho.mqtt.client as mqtt


class AwsUploader:
    __slots__ = (
        "_endpoint",
        "_topic",
        "_ca_path",
        "_cert_path",
        "_key_path",
        "_client",
        "_queue",
        "_stop_event",
        "_thread",
        "_connected_event",
        "_last_error",
        "_dropped_count",
    )

    def __init__(
        self,
        endpoint: str,
        topic: str,
        ca_path: str,
        cert_path: str,
        key_path: str,
        queue_size: int = 200,
        client_id: Optional[str] = None,
    ):
        self._endpoint = endpoint
        self._topic = topic
        self._ca_path = ca_path
        self._cert_path = cert_path
        self._key_path = key_path

        self._last_error: Optional[str] = None
        self._dropped_count = 0

        self._connected_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=int(queue_size))

        self._client = mqtt.Client(
            client_id=client_id or "",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )

        self._client.tls_set(
            ca_certs=self._ca_path,
            certfile=self._cert_path,
            keyfile=self._key_path,
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    def start(self) -> None:
        self._stop_event.clear()
        self._client.connect_async(self._endpoint, 8883, keepalive=60)
        self._client.loop_start()

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        try:
            self._client.loop_stop(force=True)
        except TypeError:
            self._client.loop_stop()

        try:
            self._client.disconnect()
        except Exception:
            pass

        if self._thread:
            self._thread.join(timeout=3.0)

    def enqueue(self, payload: Union[str, dict]) -> None:
        if isinstance(payload, dict):
            payload = json.dumps(payload, separators=(",", ":"))

        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._dropped_count += 1

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            try:
                info = self._client.publish(self._topic, payload, qos=1)

                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    self._last_error = f"publish_failed:rc={info.rc}"
                    time.sleep(0.25)
                else:
                    info.wait_for_publish(timeout=2.0)
            except Exception as e:
                self._last_error = f"publish_failed:{e}"
                time.sleep(0.25)
            finally:
                self._queue.task_done()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code == 0 or str(reason_code) == "Success":
            self._connected_event.set()
            self._last_error = None
        else:
            self._connected_event.clear()
            self._last_error = f"connect_failed:{reason_code}"

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        self._connected_event.clear()
        if reason_code != 0 and str(reason_code) != "NormalDisconnection":
            self._last_error = f"unexpected_disconnect:{reason_code}"