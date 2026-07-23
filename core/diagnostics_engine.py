"""
diagnostics_engine.py - Smart Predictive Diagnostics Engine
============================================================
Phan tich du lieu SYS_STATUS theo thoi gian thuc de:
  1. Phat hien qua tai dong co: so sanh dong dien thuc vs. du kien
  2. Tinh thoi gian lan con lai (dive time remaining)
  3. Phat hien xu huong xa pin nhanh bat thuong
  4. Canh bao nhiet do nuoc qua thap/cao
  5. Phat hien mat ket noi / heartbeat dropout

Tich hop:
  main.py goi:
    self._diag = DiagnosticsEngine(capacity_ah=15.6)
    self._mav_worker.sig_sys_status.connect(self._diag.on_sys_status)
    self._diag.sig_alert.connect(self._on_alert)
    self._diag.sig_dive_time.connect(self._on_dive_time)
    # Va trong _on_named_float:
    if name == 'TEMP': self._diag.on_water_temp(value)
    # Trong _send_mavlink_control:
    self._diag.on_throttle(throttle_pct)
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SECS: int = 60
"""Analysis sliding window in seconds."""

CAPACITY_AH_DEFAULT: float = 15.6
"""Default battery capacity: 4S 15.6 Ah pack."""

_ALERT_COOLDOWN_S: float = 30.0
"""Minimum seconds between identical alert emissions (rate-limiter)."""

_MOTOR_OVERLOAD_RATIO: float = 1.35
"""Current must exceed baseline * this ratio to trigger overload alert."""

_MOTOR_OVERLOAD_DURATION_S: float = 3.0
"""Sustained overload duration (seconds) before alert fires."""

_RAPID_DISCHARGE_SLOPE: float = -0.02
"""Voltage slope threshold (V/s); below this → Rapid Voltage Drop alert."""

_TEMP_WARN_C: float = 5.0
"""Water temperature WARN threshold (°C)."""

_TEMP_CRITICAL_C: float = 2.0
"""Water temperature CRITICAL threshold (°C)."""

_PCT_WARN: float = 20.0
"""Battery percentage WARN threshold (%)."""

_PCT_CRITICAL: float = 10.0
"""Battery percentage CRITICAL threshold (%)."""

_DIVE_TIME_CRITICAL_MIN: float = 5.0
"""Remaining dive time CRITICAL threshold (minutes)."""

_MIN_SAMPLES_FOR_STATS: int = 5
"""Minimum data points required before computing statistics."""


class DiagnosticsEngine(QObject):
    """
    Smart, predictive diagnostics engine for GCS ROV.

    Runs entirely in the main/GUI thread (inherits QObject, not QThread).
    Slots are connected to MAVLink worker signals and are called whenever
    new telemetry arrives.

    Parameters
    ----------
    capacity_ah : float
        Battery capacity in Amp-hours.  Defaults to ``CAPACITY_AH_DEFAULT``.
    parent : QObject | None
        Optional Qt parent object.
    """

    # ------------------------------------------------------------------
    # Qt Signals
    # ------------------------------------------------------------------

    sig_alert = pyqtSignal(str, str)
    """Emitted when a diagnostic alert fires.

    Arguments
    ---------
    level : str
        Severity level — one of ``'INFO'``, ``'WARN'``, ``'CRITICAL'``.
    message : str
        Human-readable description of the alert.
    """

    sig_dive_time = pyqtSignal(float)
    """Emitted on every SYS_STATUS update with estimated dive minutes remaining.

    A value of ``-1.0`` indicates insufficient data to compute an estimate.
    """

    sig_stats = pyqtSignal(dict)
    """Emitted on every SYS_STATUS update with a stats dict for PowerWidget."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        capacity_ah: float = CAPACITY_AH_DEFAULT,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._capacity_ah: float = capacity_ah

        # ---- Sliding-window history queues ----------------------------
        # Each entry is (timestamp, value)
        self._volt_hist: Deque[Tuple[float, float]] = deque()
        self._curr_hist: Deque[Tuple[float, float]] = deque()
        self._pct_hist: Deque[Tuple[float, float]] = deque()
        self._power_hist: Deque[Tuple[float, float]] = deque()

        # ---- Motor overload tracking ----------------------------------
        self._throttle: float = 0.0          # latest throttle (0.0-1.0)
        self._overload_since: Optional[float] = None  # epoch when overload started

        # ---- Alert rate-limiting: key → last emit epoch --------------
        self._alert_last_emit: Dict[str, float] = {}

        # ---- Alert counter (for get_summary) -------------------------
        self._alerts_count: int = 0

        # ---- Latest snapshot -----------------------------------------
        self._last_volt: float = 0.0
        self._last_curr: float = 0.0
        self._last_pct: float = 100.0

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def on_sys_status(self, volt: float, curr: float, pct: float) -> None:
        """
        Receive a new SYS_STATUS telemetry sample.

        Parameters
        ----------
        volt : float
            Battery voltage in Volts.
        curr : float
            Battery current draw in Amperes.
        pct : float
            Remaining battery percentage (0–100).
        """
        now = time.monotonic()

        self._last_volt = volt
        self._last_curr = curr
        self._last_pct = pct

        # Append to sliding windows
        self._volt_hist.append((now, volt))
        self._curr_hist.append((now, curr))
        self._pct_hist.append((now, pct))
        self._power_hist.append((now, volt * curr))

        # Prune samples older than WINDOW_SECS
        self._prune_history(now)

        # ---- Run diagnostics in order of severity --------------------
        self._check_battery_pct(pct)
        self._check_motor_overload(curr, now)
        self._check_rapid_discharge()
        dive_min = self._compute_dive_time(volt, pct)
        self._emit_stats(dive_min)

    def on_throttle(self, throttle_pct: float) -> None:
        """
        Receive the current throttle level.

        Parameters
        ----------
        throttle_pct : float
            Throttle as a fraction of full scale, range ``[0.0, 1.0]``.
        """
        self._throttle = float(np.clip(throttle_pct, 0.0, 1.0))

    def on_water_temp(self, temp_c: float) -> None:
        """
        Receive a water-temperature reading and apply threshold checks.

        Parameters
        ----------
        temp_c : float
            Water temperature in degrees Celsius.
        """
        if temp_c < _TEMP_CRITICAL_C:
            self._emit_alert(
                "CRITICAL",
                f"Extremely cold water: {temp_c:.1f}°C — risk of motor seizure!",
                key="cold_water",
            )
        elif temp_c < _TEMP_WARN_C:
            self._emit_alert(
                "WARN",
                f"Cold water detected: {temp_c:.1f}°C — monitor performance.",
                key="cold_water",
            )

    def on_heartbeat_lost(self) -> None:
        """
        Called by the MAVLink worker when the heartbeat timeout fires.

        Immediately emits a CRITICAL link-lost alert (bypasses rate limiter
        so each heartbeat loss is always reported once).
        """
        self._emit_alert(
            "CRITICAL",
            "Link Lost — no heartbeat received. Check cable / WiFi!",
            key="heartbeat_lost",
            force=True,
        )

    def reset(self) -> None:
        """
        Reset all history and diagnostic state.

        Call this when starting a new dive or re-connecting.
        """
        self._volt_hist.clear()
        self._curr_hist.clear()
        self._pct_hist.clear()
        self._power_hist.clear()

        self._throttle = 0.0
        self._overload_since = None
        self._alert_last_emit.clear()
        self._alerts_count = 0

        self._last_volt = 0.0
        self._last_curr = 0.0
        self._last_pct = 100.0

    def get_summary(self) -> dict:
        """
        Return a snapshot of current diagnostic statistics.

        Returns
        -------
        dict
            Keys: ``avg_power_w``, ``avg_current``, ``dive_time_min``,
            ``alerts_count``.
        """
        avg_power = self._mean_values(self._power_hist)
        avg_current = self._mean_values(self._curr_hist)
        dive_min = self._compute_dive_time(self._last_volt, self._last_pct)
        return {
            "avg_power_w": round(avg_power, 2),
            "avg_current": round(avg_current, 3),
            "dive_time_min": round(dive_min, 1),
            "alerts_count": self._alerts_count,
        }

    # ------------------------------------------------------------------
    # Private helpers — diagnostics logic
    # ------------------------------------------------------------------

    def _check_battery_pct(self, pct: float) -> None:
        """Emit battery-level alerts based on remaining percentage."""
        if pct < _PCT_CRITICAL:
            self._emit_alert(
                "CRITICAL",
                f"Battery critically low: {pct:.0f}% — surface immediately!",
                key="battery_pct",
            )
        elif pct < _PCT_WARN:
            self._emit_alert(
                "WARN",
                f"Low battery: {pct:.0f}% — begin return-to-surface.",
                key="battery_pct",
            )

    def _check_motor_overload(self, curr: float, now: float) -> None:
        """
        Compare measured current against T200 heuristic baseline.

        Baseline formula: ``baseline_i = 0.5 + throttle * 18.0``

        The alert fires only after sustained overload for
        ``_MOTOR_OVERLOAD_DURATION_S`` seconds.
        """
        baseline_i = 0.5 + self._throttle * 18.0
        overloaded = curr > baseline_i * _MOTOR_OVERLOAD_RATIO

        if overloaded:
            if self._overload_since is None:
                self._overload_since = now
            elif (now - self._overload_since) >= _MOTOR_OVERLOAD_DURATION_S:
                self._emit_alert(
                    "WARN",
                    (
                        f"Motor Overload — current {curr:.1f} A "
                        f"vs. expected ≤{baseline_i * _MOTOR_OVERLOAD_RATIO:.1f} A "
                        f"(throttle {self._throttle*100:.0f}%)"
                    ),
                    key="motor_overload",
                )
        else:
            self._overload_since = None

    def _check_rapid_discharge(self) -> None:
        """
        Detect anomalously fast voltage drop using numpy linear regression.

        Computes the linear slope (V/s) over the current sliding window.
        If fewer than ``_MIN_SAMPLES_FOR_STATS`` samples are available the
        check is skipped.
        """
        if len(self._volt_hist) < _MIN_SAMPLES_FOR_STATS:
            return

        times = np.array([t for t, _ in self._volt_hist], dtype=np.float64)
        volts = np.array([v for _, v in self._volt_hist], dtype=np.float64)

        # Normalise time to avoid numerical issues
        t0 = times[0]
        slope, _ = np.polyfit(times - t0, volts, 1)

        if slope < _RAPID_DISCHARGE_SLOPE:
            self._emit_alert(
                "WARN",
                (
                    f"Rapid Voltage Drop — slope {slope*1000:.2f} mV/s "
                    f"(threshold {_RAPID_DISCHARGE_SLOPE*1000:.0f} mV/s)"
                ),
                key="rapid_discharge",
            )

    def _compute_dive_time(self, volt: float, pct: float) -> float:
        """
        Estimate remaining dive time in minutes.

        Formula
        -------
        ``wh_remaining = volt * capacity_ah * (pct / 100)``
        ``avg_power    = mean(volt * curr)``  over the sliding window
        ``dive_min     = (wh_remaining / avg_power) * 60``

        Returns ``-1.0`` if insufficient data or power is zero.
        """
        if len(self._power_hist) < _MIN_SAMPLES_FOR_STATS:
            return -1.0

        avg_power = self._mean_values(self._power_hist)
        if avg_power <= 0.0:
            return -1.0

        wh_remaining = volt * self._capacity_ah * (pct / 100.0)
        dive_min = (wh_remaining / avg_power) * 60.0
        dive_min = max(0.0, dive_min)

        if dive_min < _DIVE_TIME_CRITICAL_MIN:
            self._emit_alert(
                "CRITICAL",
                f"Dive time critical: ~{dive_min:.1f} min remaining — surface now!",
                key="dive_time_critical",
            )

        self.sig_dive_time.emit(dive_min)
        return dive_min

    def _emit_stats(self, dive_min: float) -> None:
        """Build and emit the stats dict consumed by PowerWidget."""
        stats: dict = {
            "voltage_v": round(self._last_volt, 2),
            "current_a": round(self._last_curr, 3),
            "battery_pct": round(self._last_pct, 1),
            "avg_power_w": round(self._mean_values(self._power_hist), 2),
            "avg_current_a": round(self._mean_values(self._curr_hist), 3),
            "dive_time_min": round(dive_min, 1),
            "throttle_pct": round(self._throttle * 100.0, 1),
            "alerts_count": self._alerts_count,
            "window_samples": len(self._volt_hist),
        }
        self.sig_stats.emit(stats)

    # ------------------------------------------------------------------
    # Private helpers — infrastructure
    # ------------------------------------------------------------------

    def _prune_history(self, now: float) -> None:
        """Remove samples older than ``WINDOW_SECS`` from all deques."""
        cutoff = now - WINDOW_SECS
        for dq in (
            self._volt_hist,
            self._curr_hist,
            self._pct_hist,
            self._power_hist,
        ):
            while dq and dq[0][0] < cutoff:
                dq.popleft()

    @staticmethod
    def _mean_values(dq: Deque[Tuple[float, float]]) -> float:
        """Return the mean of the *value* component of a (timestamp, value) deque."""
        if not dq:
            return 0.0
        return float(np.mean([v for _, v in dq]))

    def _emit_alert(
        self,
        level: str,
        message: str,
        key: str,
        force: bool = False,
    ) -> None:
        """
        Emit ``sig_alert`` subject to per-key rate limiting.

        Parameters
        ----------
        level : str
            ``'INFO'``, ``'WARN'``, or ``'CRITICAL'``.
        message : str
            Human-readable alert text.
        key : str
            Unique identifier for this alert type — used for rate limiting.
        force : bool
            If ``True``, bypass the rate limiter (e.g. heartbeat loss).
        """
        now = time.monotonic()
        last = self._alert_last_emit.get(key, 0.0)

        if not force and (now - last) < _ALERT_COOLDOWN_S:
            return  # Too soon — suppress duplicate

        self._alert_last_emit[key] = now
        self._alerts_count += 1
        self.sig_alert.emit(level, message)
