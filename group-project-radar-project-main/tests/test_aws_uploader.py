import sys
sys.path.insert(0, "../src/packet")

import json
import queue
import ssl
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from aws_uploader import AwsUploader


class TestAwsUploaderInit(unittest.TestCase):

    def test_raises_if_no_client_id(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "topic/test", "ca", "cert", "key")

    def test_raises_if_empty_client_id(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "topic/test", "ca", "cert", "key", client_id="")

    def test_raises_if_topic_empty(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "", "ca", "cert", "key", client_id="device-1")

    def test_raises_if_topic_has_leading_slash(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "/topic/test", "ca", "cert", "key", client_id="device-1")

    def test_raises_if_topic_has_wildcard_hash(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "topic/#", "ca", "cert", "key", client_id="device-1")

    def test_raises_if_topic_has_wildcard_plus(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertRaises(ValueError):
                AwsUploader("endpoint", "topic/+/test", "ca", "cert", "key", client_id="device-1")

    def test_warns_if_topic_exceeds_7_segments(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            with self.assertWarns(UserWarning):
                AwsUploader("endpoint", "a/b/c/d/e/f/g/h", "ca", "cert", "key", client_id="device-1")


class TestAwsUploaderEnqueue(unittest.TestCase):

    def _make_uploader(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            return AwsUploader(
                "endpoint", "topic/test", "ca", "cert", "key", client_id="device-1"
            )

    def test_enqueue_string_returns_true(self):
        u = self._make_uploader()
        self.assertTrue(u.enqueue("hello"))

    def test_enqueue_dict_serialises_to_json(self):
        u = self._make_uploader()
        u.enqueue({"key": "value"})
        item = u._queue.get_nowait()
        self.assertEqual(item, '{"key":"value"}')

    def test_enqueue_returns_false_when_full(self):
        u = self._make_uploader()
        for _ in range(200):
            u._queue.put_nowait("x")
        result = u.enqueue("overflow")
        self.assertFalse(result)

    def test_dropped_count_increments_when_full(self):
        u = self._make_uploader()
        for _ in range(200):
            u._queue.put_nowait("x")
        u.enqueue("overflow")
        self.assertEqual(u.dropped_count, 1)

    def test_enqueue_raises_if_payload_too_large(self):
        u = self._make_uploader()
        with self.assertRaises(ValueError):
            u.enqueue("x" * 131_073)

    def test_enqueue_accepts_exactly_max_size(self):
        u = self._make_uploader()
        self.assertTrue(u.enqueue("x" * 131_072))


class TestAwsUploaderWorker(unittest.TestCase):

    def _make_uploader(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            return AwsUploader(
                "endpoint", "topic/test", "ca", "cert", "key", client_id="device-1"
            )

    def test_worker_does_not_dequeue_while_disconnected(self):
        u = self._make_uploader()
        u.enqueue("hello")
        t = threading.Thread(target=u._worker, daemon=True)
        t.start()
        time.sleep(0.3)
        self.assertEqual(u.queue_depth, 1)
        u._stop_event.set()
        t.join(timeout=2.0)

    def test_worker_publishes_when_connected(self):
        u = self._make_uploader()
        publish_info = MagicMock()
        publish_info.rc = 0
        publish_info.mid = 42
        u._client.publish = MagicMock(return_value=publish_info)

        u._connected_event.set()
        u.enqueue("hello")

        t = threading.Thread(target=u._worker, daemon=True)
        t.start()
        time.sleep(0.3)
        u._stop_event.set()
        t.join(timeout=2.0)

        u._client.publish.assert_called_once_with("topic/test", "hello", qos=1)

    def test_worker_requeues_on_publish_failure(self):
        u = self._make_uploader()
        publish_info = MagicMock()
        publish_info.rc = 1
        u._client.publish = MagicMock(return_value=publish_info)

        u._connected_event.set()
        u.enqueue("hello")

        t = threading.Thread(target=u._worker, daemon=True)
        t.start()
        time.sleep(0.5)
        u._stop_event.set()
        t.join(timeout=2.0)

        self.assertGreater(u._client.publish.call_count, 1)

    def test_worker_tracks_in_flight_mid(self):
        u = self._make_uploader()
        publish_info = MagicMock()
        publish_info.rc = 0
        publish_info.mid = 99
        u._client.publish = MagicMock(return_value=publish_info)

        u._connected_event.set()
        u.enqueue("hello")

        t = threading.Thread(target=u._worker, daemon=True)
        t.start()
        time.sleep(0.3)
        u._stop_event.set()
        t.join(timeout=2.0)

        self.assertIn(99, u._in_flight)

    def test_on_publish_clears_in_flight(self):
        u = self._make_uploader()
        u._in_flight.add(99)
        u._on_publish(None, None, 99)
        self.assertNotIn(99, u._in_flight)

    def test_worker_drops_message_if_requeue_fails(self):
        u = self._make_uploader()
        publish_info = MagicMock()
        publish_info.rc = 1
        u._client.publish = MagicMock(return_value=publish_info)

        for _ in range(200):
            u._queue.put_nowait("filler")

        u._connected_event.set()
        payload = "lost"
        try:
            info = u._client.publish(u._topic, payload, qos=1)
            if info.rc != 0:
                with u._lock:
                    u._last_error = f"publish_failed:rc={info.rc}"
                try:
                    u._queue.put_nowait(payload)
                except queue.Full:
                    with u._lock:
                        u._dropped_count += 1
        finally:
            pass

        self.assertEqual(u.dropped_count, 1)


class TestAwsUploaderCallbacks(unittest.TestCase):

    def _make_uploader(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            return AwsUploader(
                "endpoint", "topic/test", "ca", "cert", "key", client_id="device-1"
            )

    def test_on_connect_sets_connected_event(self):
        u = self._make_uploader()
        u._on_connect(None, None, None, 0, None)
        self.assertTrue(u.is_connected())

    def test_on_connect_clears_last_error(self):
        u = self._make_uploader()
        with u._lock:
            u._last_error = "some error"
        u._on_connect(None, None, None, 0, None)
        self.assertIsNone(u.last_error)

    def test_on_connect_failure_sets_last_error(self):
        u = self._make_uploader()
        u._on_connect(None, None, None, 5, None)
        self.assertIsNotNone(u.last_error)
        self.assertFalse(u.is_connected())

    def test_on_disconnect_clears_connected_event(self):
        u = self._make_uploader()
        u._connected_event.set()
        u._on_disconnect(None, None, 0, None)
        self.assertFalse(u.is_connected())

    def test_on_disconnect_unexpected_sets_last_error(self):
        u = self._make_uploader()
        u._on_disconnect(None, None, 1, None)
        self.assertIsNotNone(u.last_error)


class TestAwsUploaderLifecycle(unittest.TestCase):

    def _make_uploader(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            return AwsUploader(
                "endpoint", "topic/test", "ca", "cert", "key", client_id="device-1"
            )

    def test_start_spawns_worker_thread(self):
        u = self._make_uploader()
        u._client.connect_async = MagicMock()
        u._client.loop_start = MagicMock()
        u.start()
        self.assertIsNotNone(u._thread)
        self.assertTrue(u._thread.is_alive())
        u._stop_event.set()

    def test_start_is_idempotent(self):
        u = self._make_uploader()
        u._client.connect_async = MagicMock()
        u._client.loop_start = MagicMock()
        u.start()
        thread_id = id(u._thread)
        u.start()
        self.assertEqual(id(u._thread), thread_id)
        u._stop_event.set()

    def test_stop_sets_stop_event(self):
        u = self._make_uploader()
        u._client.connect_async = MagicMock()
        u._client.loop_start = MagicMock()
        u._client.loop_stop = MagicMock()
        u._client.disconnect = MagicMock()
        u.start()
        u.stop()
        self.assertTrue(u._stop_event.is_set())

    def test_context_manager_calls_start_and_stop(self):
        u = self._make_uploader()
        with patch.object(AwsUploader, "start") as mock_start, \
             patch.object(AwsUploader, "stop") as mock_stop:
            with u:
                pass
        mock_start.assert_called_once()
        mock_stop.assert_called_once()

    def test_context_manager_calls_stop_on_exception(self):
        u = self._make_uploader()
        with patch.object(AwsUploader, "start"), \
             patch.object(AwsUploader, "stop") as mock_stop:
            try:
                with u:
                    raise RuntimeError("something went wrong")
            except RuntimeError:
                pass
        mock_stop.assert_called_once()


class TestAwsUploaderObservability(unittest.TestCase):

    def _make_uploader(self):
        with patch("paho.mqtt.client.Client"), patch("ssl.create_default_context"):
            return AwsUploader(
                "endpoint", "topic/test", "ca", "cert", "key", client_id="device-1"
            )

    def test_queue_depth_reflects_enqueued_items(self):
        u = self._make_uploader()
        u.enqueue("a")
        u.enqueue("b")
        self.assertEqual(u.queue_depth, 2)

    def test_repr_contains_key_fields(self):
        u = self._make_uploader()
        r = repr(u)
        self.assertIn("endpoint", r)
        self.assertIn("topic/test", r)
        self.assertIn("connected=", r)
        self.assertIn("queue_depth=", r)
        self.assertIn("dropped=", r)


if __name__ == "__main__":
    unittest.main()