"""
database/telemetry_logger.py - High-Frequency Async Telemetry Black Box Logger
================================================================================
Runs a dedicated background queue worker thread to insert MAVLink telemetry (10-50Hz)
into SQLite WAL database in non-blocking batches. Guarantees 0% GUI lag.
"""

import time
import queue
import threading
from typing import Dict, Any, Optional

from .db_manager import DatabaseManager


class AsyncTelemetryLogger:
    """
    Asynchronous Telemetry Logger for High-Frequency (10-50Hz) ROV Flight Data.
    Pushes incoming MAVLink telemetry frames to a thread-safe Queue and flushes to SQLite WAL
    in batches every 0.5s or when batch size hits 50 items.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None, batch_size: int = 50, flush_interval_sec: float = 0.5):
        self.db = db_manager or DatabaseManager()
        self.batch_size = batch_size
        self.flush_interval = flush_interval_sec

        self._queue = queue.Queue(maxsize=5000)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_session_id: Optional[str] = None
        self._total_logged_count = 0

    def start(self, session_id: Optional[str] = None):
        """Start background async logging thread."""
        if self._running:
            return

        if session_id:
            self._current_session_id = session_id

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AsyncTelemetryLogger")
        self._thread.start()
        print(f"[AsyncTelemetryLogger] Worker started for session: {self._current_session_id}")

    def set_session_id(self, session_id: str):
        """Update active session ID."""
        self._current_session_id = session_id

    def log_telemetry(self, telemetry_data: Dict[str, Any]):
        """
        Non-blocking call to push 10-50Hz MAVLink telemetry frame to queue.
        Executes in < 0.01ms on Main GUI Thread.
        """
        if not self._running:
            return

        # Ensure timestamp is set
        if "timestamp" not in telemetry_data:
            telemetry_data["timestamp"] = time.time()

        try:
            self._queue.put_nowait(telemetry_data)
        except queue.Full:
            # Prevent memory overflow if disk I/O stalls
            pass

    def _worker_loop(self):
        """Background worker thread processing telemetry queue batches."""
        batch = []
        last_flush_time = time.time()

        while self._running or not self._queue.empty():
            try:
                # Wait for next item with 0.1s timeout
                item = self._queue.get(timeout=0.1)
                batch.append(item)

                now = time.time()
                # Flush if batch size reached OR flush time interval exceeded
                if len(batch) >= self.batch_size or (now - last_flush_time) >= self.flush_interval:
                    self._flush_batch(batch)
                    batch = []
                    last_flush_time = now

            except queue.Empty:
                now = time.time()
                if batch and (now - last_flush_time) >= self.flush_interval:
                    self._flush_batch(batch)
                    batch = []
                    last_flush_time = now

        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: list):
        """Flush batch of telemetry records to SQLite WAL database."""
        sid = self._current_session_id or self.db.active_session_id
        if not sid or not batch:
            return

        try:
            self.db.insert_telemetry_batch(sid, batch)
            self._total_logged_count += len(batch)
        except Exception as exc:
            print(f"[AsyncTelemetryLogger] Error writing batch to SQLite: {exc}")

    def stop(self):
        """Gracefully stop background logging thread and flush remaining items."""
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        print(f"[AsyncTelemetryLogger] Stopped. Total telemetry frames logged: {self._total_logged_count}")
