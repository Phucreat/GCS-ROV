"""
mission_uploader.py - MAVLink Mission Protocol Handler
=======================================================
Trien khai giao thuc upload mission MAVLink:
  MISSION_CLEAR_ALL (#45) → xoa mission hien tai tren ROV
  MISSION_COUNT     (#44) → bao so WP
  MISSION_REQUEST   (#40) → ROV yeu cau tung WP  (MAVLink v1)
  MISSION_REQUEST_INT (#51) → ROV yeu cau tung WP (MAVLink v2)
  MISSION_ITEM_INT  (#73) → gui WP dang int lat/lon
  MISSION_ACK       (#47) → xac nhan hoan tat

Chay trong QThread rieng de khong block GUI.

Sequence diagram:
  GCS                          ROV
   |  ─MISSION_CLEAR_ALL──────→ |
   |  ←MISSION_ACK────────────  |
   |  ─MISSION_COUNT(N)────────→ |
   |  ←MISSION_REQUEST(0)──────  |
   |  ─MISSION_ITEM_INT(0)─────→ |
   |  ←MISSION_REQUEST(1)──────  |
   |  ─MISSION_ITEM_INT(1)─────→ |
   |       ...                   |
   |  ─MISSION_ITEM_INT(N-1)───→ |
   |  ←MISSION_ACK(ACCEPTED)───  |
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

# ---------------------------------------------------------------------------
# Optional PyQt6 import
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import QThread, pyqtSignal
    _HAVE_QT = True
except ImportError:  # pragma: no cover
    class pyqtSignal:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            pass
        def emit(self, *a, **kw):
            pass
        def connect(self, *a, **kw):
            pass

    class QThread:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            pass
        def start(self, *a, **kw):
            pass
        def quit(self, *a, **kw):
            pass
        def run(self):
            pass
        def msleep(self, ms: int):
            time.sleep(ms / 1000.0)

    _HAVE_QT = False

# ---------------------------------------------------------------------------
# MAVLink message IDs and enums (defined locally to avoid hard dependency on
# specific pymavlink version — actual message objects are built via the
# mav_connection passed by the caller)
# ---------------------------------------------------------------------------
MAVLINK_MSG_ID_MISSION_REQUEST      = 40
MAVLINK_MSG_ID_MISSION_ITEM         = 39
MAVLINK_MSG_ID_MISSION_COUNT        = 44
MAVLINK_MSG_ID_MISSION_ACK          = 47
MAVLINK_MSG_ID_MISSION_ITEM_INT     = 73
MAVLINK_MSG_ID_MISSION_REQUEST_INT  = 51
MAVLINK_MSG_ID_MISSION_CLEAR_ALL    = 45

MAV_MISSION_ACCEPTED                = 0
MAV_MISSION_ERROR                   = 1

MAV_CMD_NAV_WAYPOINT                = 16
MAV_FRAME_GLOBAL_RELATIVE_ALT       = 3

# Default system / component IDs for the GCS
GCS_SYSTEM_ID    = 255
GCS_COMPONENT_ID = 190   # MAV_COMP_ID_MISSIONPLANNER

logger = logging.getLogger(__name__)


# ===========================================================================
# Waypoint dataclass
# ===========================================================================

@dataclass
class Waypoint:
    """
    A single mission waypoint in NED (North-East-Down) local frame.

    Attributes
    ----------
    ned_x, ned_y, ned_z : float
        Position in NED metres relative to the mission origin (GCS location).
    hold_time_s : float
        Loiter duration at the waypoint (seconds). MAVLink param1.
    acceptance_radius_m : float
        Sphere radius within which the WP is considered reached (metres).
        MAVLink param2.
    is_home : bool
        If True this is waypoint 0 (the home/rally point). The MAVLink
        command will be MAV_CMD_NAV_WAYPOINT; special home handling is done
        by the autopilot based on sequence index 0.
    """
    ned_x: float
    ned_y: float
    ned_z: float
    hold_time_s: float = 5.0
    acceptance_radius_m: float = 0.5
    is_home: bool = False

    def __post_init__(self) -> None:
        if self.hold_time_s < 0:
            raise ValueError("hold_time_s must be ≥ 0")
        if self.acceptance_radius_m < 0:
            raise ValueError("acceptance_radius_m must be ≥ 0")


# ===========================================================================
# MissionUploader
# ===========================================================================

class MissionUploader(QThread):
    """
    Upload a list of Waypoints to an ROV via the MAVLink Mission Protocol.

    Runs in a dedicated QThread so the GUI remains responsive.

    Signals
    -------
    sig_progress(current: int, total: int)
        Emitted after each MISSION_ITEM_INT is successfully acknowledged
        (i.e., after the ROV requests the next item).
    sig_done(success: bool, message: str)
        Emitted when the upload finishes (whether successful or not).
    """

    if _HAVE_QT:
        sig_progress = pyqtSignal(int, int)
        sig_done     = pyqtSignal(bool, str)

    # Protocol tunables
    _ITEM_TIMEOUT_S:   float = 5.0   # per-item request timeout
    _MAX_RETRIES:      int   = 3     # retries per item before giving up
    _ACK_TIMEOUT_S:    float = 10.0  # final MISSION_ACK timeout
    _POLL_INTERVAL_S:  float = 0.05  # busy-wait polling granularity

    def __init__(
        self,
        mav_connection,
        waypoints: List[Waypoint],
        gcs_lat: float = 0.0,
        gcs_lng: float = 0.0,
        target_system: int = 1,
        target_component: int = 1,
        parent=None,
    ) -> None:
        """
        Parameters
        ----------
        mav_connection   : pymavlink MAVLink connection object (already open)
        waypoints        : ordered list of Waypoint objects; index 0 is home
        gcs_lat          : GCS latitude in decimal degrees (mission origin)
        gcs_lng          : GCS longitude in decimal degrees (mission origin)
        target_system    : MAVLink system ID of the ROV
        target_component : MAVLink component ID of the ROV autopilot
        """
        super().__init__(parent)

        if not waypoints:
            raise ValueError("waypoints list must not be empty")

        self._mav          = mav_connection
        self._waypoints    = list(waypoints)
        self._gcs_lat      = float(gcs_lat)
        self._gcs_lng      = float(gcs_lng)
        self._target_sys   = int(target_system)
        self._target_comp  = int(target_component)

        self._abort = False   # set to True to cancel mid-upload

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def abort(self) -> None:
        """Request graceful abort (will emit sig_done with success=False)."""
        logger.info("MissionUploader: abort requested")
        self._abort = True

    # ------------------------------------------------------------------
    # QThread entry-point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the full MAVLink mission upload protocol."""
        total = len(self._waypoints)
        logger.info("MissionUploader: starting upload of %d waypoints", total)

        try:
            # Step 1 — clear existing mission
            if not self._send_mission_clear_all():
                self._emit_done(False, "MISSION_CLEAR_ALL timed out / rejected")
                return

            if self._abort:
                self._emit_done(False, "Aborted before MISSION_COUNT")
                return

            # Step 2 — announce count
            self._send_mission_count(total)
            logger.debug("MissionUploader: sent MISSION_COUNT=%d", total)

            # Step 3 — upload items on demand
            sent_indices = set()
            start_t = time.monotonic()
            UPLOAD_TIMEOUT = self._ITEM_TIMEOUT_S * self._MAX_RETRIES * total + 10.0

            while len(sent_indices) < total:
                if self._abort:
                    self._emit_done(False, "Upload aborted by user")
                    return

                if time.monotonic() - start_t > UPLOAD_TIMEOUT:
                    self._emit_done(False, f"Upload timed out overall ({UPLOAD_TIMEOUT:.0f}s)")
                    return

                msg = self._recv_with_timeout(
                    (MAVLINK_MSG_ID_MISSION_REQUEST, MAVLINK_MSG_ID_MISSION_REQUEST_INT),
                    timeout_s=self._ITEM_TIMEOUT_S,
                )
                if msg is None:
                    # Check if we already sent all items and are waiting for ACK
                    if len(sent_indices) == total:
                        break
                    self._emit_done(
                        False,
                        f"Timed out waiting for MISSION_REQUEST after {len(sent_indices)} items",
                    )
                    return

                seq = int(msg.seq)
                if seq < 0 or seq >= total:
                    logger.warning("MissionUploader: received invalid seq=%d, ignoring", seq)
                    continue

                retry = 0
                success = False
                while retry < self._MAX_RETRIES:
                    if self._abort:
                        self._emit_done(False, "Upload aborted by user")
                        return

                    try:
                        item_msg = self._build_mission_item_int(seq, self._waypoints[seq])
                        self._mav.mav.send(item_msg)
                        logger.debug("MissionUploader: sent MISSION_ITEM_INT seq=%d (attempt %d)", seq, retry + 1)
                        success = True
                        break
                    except Exception as exc:
                        logger.warning(
                            "MissionUploader: send failed for seq=%d attempt=%d: %s",
                            seq, retry + 1, exc,
                        )
                        retry += 1
                        time.sleep(0.5)

                if not success:
                    self._emit_done(False, f"Failed to send MISSION_ITEM_INT seq={seq} after {self._MAX_RETRIES} retries")
                    return

                sent_indices.add(seq)
                self._emit_progress(len(sent_indices), total)

            # Step 4 — wait for MISSION_ACK
            ack = self._recv_with_timeout(
                (MAVLINK_MSG_ID_MISSION_ACK,),
                timeout_s=self._ACK_TIMEOUT_S,
            )
            if ack is None:
                self._emit_done(False, f"No MISSION_ACK received within {self._ACK_TIMEOUT_S:.0f}s")
                return

            ack_type = int(getattr(ack, 'type', -1))
            if ack_type == MAV_MISSION_ACCEPTED:
                logger.info("MissionUploader: mission accepted by ROV ✓")
                self._emit_done(True, f"Mission uploaded successfully ({total} waypoints)")
            else:
                result_name = _mission_result_str(ack_type)
                logger.error("MissionUploader: mission rejected — %s (%d)", result_name, ack_type)
                self._emit_done(False, f"ROV rejected mission: {result_name} (code {ack_type})")

        except Exception as exc:
            logger.exception("MissionUploader: unexpected error")
            self._emit_done(False, f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Protocol helpers
    # ------------------------------------------------------------------

    def _send_mission_clear_all(self) -> bool:
        """
        Send MISSION_CLEAR_ALL and wait for MISSION_ACK.

        Returns True if the ROV acknowledged, False on timeout/error.
        """
        try:
            self._mav.mav.mission_clear_all_send(
                self._target_sys,
                self._target_comp,
            )
            logger.debug("MissionUploader: sent MISSION_CLEAR_ALL")
        except Exception as exc:
            logger.warning("MissionUploader: MISSION_CLEAR_ALL send failed: %s", exc)
            return False

        ack = self._recv_with_timeout(
            (MAVLINK_MSG_ID_MISSION_ACK,),
            timeout_s=self._ITEM_TIMEOUT_S,
        )
        if ack is None:
            logger.warning("MissionUploader: no ACK for MISSION_CLEAR_ALL")
            return False

        ack_type = int(getattr(ack, 'type', -1))
        if ack_type != MAV_MISSION_ACCEPTED:
            logger.warning(
                "MissionUploader: MISSION_CLEAR_ALL rejected with type=%d", ack_type
            )
            return False

        return True

    def _send_mission_count(self, count: int) -> None:
        """Send MISSION_COUNT to the ROV."""
        self._mav.mav.mission_count_send(
            self._target_sys,
            self._target_comp,
            count,
        )

    def _ned_to_mavlink_coord(self, wp: Waypoint):
        """
        Convert NED offset (metres) to a (lat_int, lon_int, alt_m) tuple
        suitable for MISSION_ITEM_INT.

        lat_int and lon_int are integer-encoded degrees × 1e7.
        alt_m is the depth expressed as negative altitude (NED z positive-down
        → MAVLink relative alt positive-up, so depth → negative alt).

        Uses utils.geo_utils.ned_to_gps if available, otherwise falls back to
        a self-contained haversine approximation.
        """
        try:
            from utils.geo_utils import ned_to_gps  # project-local utility
            lat_deg, lon_deg = ned_to_gps(
                self._gcs_lat,
                self._gcs_lng,
                north_m=wp.ned_x,
                east_m=wp.ned_y,
            )
        except ImportError:
            lat_deg, lon_deg = _ned_offset_to_gps_approx(
                self._gcs_lat, self._gcs_lng, wp.ned_x, wp.ned_y
            )

        lat_int = int(round(lat_deg * 1e7))
        lon_int = int(round(lon_deg * 1e7))

        # NED z positive-down → MAVLink relative alt positive-up
        # depth in water is positive z; we negate for MAVLink alt convention
        alt_m = -wp.ned_z  # e.g., NED z=10 → alt=-10 (10 m below surface)

        return lat_int, lon_int, alt_m

    def _build_mission_item_int(self, seq: int, wp: Waypoint):
        """
        Construct a pymavlink MISSION_ITEM_INT message object.

        Parameters
        ----------
        seq : zero-based sequence number
        wp  : Waypoint to encode

        Returns
        -------
        pymavlink MAVLink_mission_item_int_message ready to be sent.
        """
        lat_int, lon_int, alt_m = self._ned_to_mavlink_coord(wp)

        # param1 = hold_time (s), param2 = acceptance_radius (m)
        # param3 = pass_radius=0 (go through WP), param4 = yaw=NaN (don't change)
        msg = self._mav.mav.mission_item_int_encode(
            target_system    = self._target_sys,
            target_component = self._target_comp,
            seq              = seq,
            frame            = MAV_FRAME_GLOBAL_RELATIVE_ALT,
            command          = MAV_CMD_NAV_WAYPOINT,
            current          = 1 if seq == 0 else 0,
            autocontinue     = 1,
            param1           = float(wp.hold_time_s),
            param2           = float(wp.acceptance_radius_m),
            param3           = 0.0,          # pass radius (0 = must hit centre)
            param4           = float('nan'),  # desired yaw (NaN = unchanged)
            x                = lat_int,
            y                = lon_int,
            z                = float(alt_m),
        )
        return msg

    # ------------------------------------------------------------------
    # Receive helper
    # ------------------------------------------------------------------

    def _recv_with_timeout(self, expected_ids: tuple, timeout_s: float):
        """
        Blocking receive: polls the MAVLink connection until one of the
        ``expected_ids`` message types arrives or the timeout expires.

        Parameters
        ----------
        expected_ids : tuple of MAVLink message IDs to accept
        timeout_s    : maximum wait time in seconds

        Returns
        -------
        The first matching MAVLink message, or None on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._abort:
                return None
            try:
                msg = self._mav.recv_match(
                    type=None,
                    blocking=False,
                )
            except Exception as exc:
                logger.debug("MissionUploader: recv error: %s", exc)
                msg = None

            if msg is not None and msg.get_msgId() in expected_ids:
                return msg

            # Polite yield — avoid burning a whole CPU core
            time.sleep(self._POLL_INTERVAL_S)

        return None  # timeout

    # ------------------------------------------------------------------
    # Signal helpers (safe regardless of _HAVE_QT)
    # ------------------------------------------------------------------

    def _emit_progress(self, current: int, total: int) -> None:
        if _HAVE_QT:
            try:
                self.sig_progress.emit(current, total)
            except RuntimeError:
                pass
        else:
            logger.info("MissionUploader progress: %d / %d", current, total)

    def _emit_done(self, success: bool, message: str) -> None:
        logger.info("MissionUploader done — success=%s  msg='%s'", success, message)
        if _HAVE_QT:
            try:
                self.sig_done.emit(success, message)
            except RuntimeError:
                pass


# ===========================================================================
# Stand-alone geo utilities (fallback when utils.geo_utils not present)
# ===========================================================================

def _ned_offset_to_gps_approx(
    ref_lat_deg: float,
    ref_lon_deg: float,
    north_m: float,
    east_m: float,
) -> tuple:
    """
    Approximate NED (north_m, east_m) offset from a reference GPS point to
    a new GPS point.  Uses the flat-Earth (equirectangular) approximation,
    accurate to ~0.1% for offsets < 100 km.

    Parameters
    ----------
    ref_lat_deg, ref_lon_deg : reference (origin) latitude / longitude [deg]
    north_m, east_m          : NED offset in metres

    Returns
    -------
    (lat_deg, lon_deg) of the target point
    """
    import math

    EARTH_RADIUS_M = 6_378_137.0  # WGS-84 equatorial radius

    lat_rad = math.radians(ref_lat_deg)

    d_lat = north_m / EARTH_RADIUS_M
    d_lon = east_m  / (EARTH_RADIUS_M * math.cos(lat_rad))

    lat_out = ref_lat_deg + math.degrees(d_lat)
    lon_out = ref_lon_deg + math.degrees(d_lon)

    return lat_out, lon_out


# ===========================================================================
# MAVLink result code → human-readable string
# ===========================================================================

_MISSION_RESULT_NAMES = {
    0:  "MAV_MISSION_ACCEPTED",
    1:  "MAV_MISSION_ERROR",
    2:  "MAV_MISSION_UNSUPPORTED_FRAME",
    3:  "MAV_MISSION_UNSUPPORTED",
    4:  "MAV_MISSION_NO_SPACE",
    5:  "MAV_MISSION_INVALID",
    6:  "MAV_MISSION_INVALID_PARAM1",
    7:  "MAV_MISSION_INVALID_PARAM2",
    8:  "MAV_MISSION_INVALID_PARAM3",
    9:  "MAV_MISSION_INVALID_PARAM4",
    10: "MAV_MISSION_INVALID_PARAM5_X",
    11: "MAV_MISSION_INVALID_PARAM6_Y",
    12: "MAV_MISSION_INVALID_PARAM7",
    13: "MAV_MISSION_INVALID_SEQUENCE",
    14: "MAV_MISSION_DENIED",
    15: "MAV_MISSION_OPERATION_CANCELLED",
}


def _mission_result_str(code: int) -> str:
    return _MISSION_RESULT_NAMES.get(code, f"UNKNOWN({code})")
