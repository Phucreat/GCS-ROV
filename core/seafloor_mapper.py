"""
seafloor_mapper.py - 2.5D Seafloor Depth Map Builder
====================================================
Thu thap diem SLAM + do sau thuc te → xay dung luoi do sau 2.5D.

Thuat toan:
  1. Nhan diem SLAM (x,y,z) tu SLAMUDPReceiver
  2. Tu dieu chinh z voi do sau thuc (pressure sensor) tai vi tri ROV
  3. Tich luy diem trong KDTree-like grid
  4. Noi suy luoi deu bang scipy.griddata (cubic/linear fallback)
  5. Tao vertices + colors (depth colormap) cho OpenGL

Colormap:
  z=0m  → #FF4040 (do)
  z=5m  → #FFAA00 (vang)
  z=10m → #00AAFF (xanh cyan)
  z=20m → #001040 (xanh dam)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Optional PyQt6 import (graceful degradation for unit-test environments)
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import QObject, pyqtSignal
    _HAVE_QT = True
except ImportError:  # pragma: no cover
    # Provide stub so the file can be imported without PyQt6 installed
    class pyqtSignal:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            pass
        def emit(self, *a, **kw):
            pass
        def connect(self, *a, **kw):
            pass

    class QObject:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            pass

    _HAVE_QT = False

# ---------------------------------------------------------------------------
# Lazy-import scipy
# ---------------------------------------------------------------------------
try:
    from scipy.interpolate import griddata as _scipy_griddata
    _HAVE_SCIPY = True
except ImportError:  # pragma: no cover
    _scipy_griddata = None  # type: ignore[assignment]
    _HAVE_SCIPY = False

logger = logging.getLogger(__name__)


# ===========================================================================
# DepthColormap
# ===========================================================================

class DepthColormap:
    """
    Maps a depth value (metres, positive = deeper) to an RGB tuple.

    HSV interpolation:
      depth = 0   → hue = 0.00  (red,   H=0°)
      depth = max → hue = 0.67  (blue,  H=240°)
    Saturation = 1.0, Value = 1.0 (pure, vivid colours).
    """

    @staticmethod
    def depth_to_rgb(depth_m: float, max_depth: float = 30.0) -> Tuple[float, float, float]:
        """
        Convert a depth (m) to an RGB tuple with values in [0, 1].

        Parameters
        ----------
        depth_m   : depth in metres (clamped to [0, max_depth])
        max_depth : depth at which the colour is fully blue

        Returns
        -------
        (r, g, b) each in [0.0, 1.0]
        """
        if max_depth <= 0:
            raise ValueError("max_depth must be positive")

        t = float(np.clip(depth_m, 0.0, max_depth)) / max_depth  # [0, 1]
        hue = t * 0.6667  # 0.0 → 0.0 (red),  1.0 → 0.667 (blue)
        s = 1.0
        v = 1.0

        return DepthColormap._hsv_to_rgb(hue, s, v)

    @staticmethod
    def depth_to_rgba(depth_m: float, max_depth: float = 30.0, alpha: float = 1.0) -> Tuple[float, float, float, float]:
        """Same as depth_to_rgb but appends an alpha channel."""
        r, g, b = DepthColormap.depth_to_rgb(depth_m, max_depth)
        return (r, g, b, float(np.clip(alpha, 0.0, 1.0)))

    @staticmethod
    def _hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
        """Pure-python HSV → RGB (avoids colorsys import dependency)."""
        if s == 0.0:
            return (v, v, v)
        h6 = h * 6.0
        i = int(h6) % 6
        f = h6 - int(h6)
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        return [
            (v, t, p),  # 0
            (q, v, p),  # 1
            (p, v, t),  # 2
            (p, q, v),  # 3
            (t, p, v),  # 4
            (v, p, q),  # 5
        ][i]

    @staticmethod
    def depth_array_to_rgba(depths: np.ndarray, max_depth: float = 30.0) -> np.ndarray:
        """
        Vectorised version: depths shape (N,) → RGBA float32 array (N, 4).
        Far faster than calling depth_to_rgba in a loop.
        """
        depths = np.asarray(depths, dtype=np.float32)
        t = np.clip(depths, 0.0, max_depth) / max_depth  # [0, 1]
        h = t * 0.6667
        # HSV (h, 1, 1) → RGB
        h6 = h * 6.0
        i = np.floor(h6).astype(np.int32) % 6
        f = h6 - np.floor(h6)
        # p = 0 (s=1), q = 1-f, t_val = f
        q = 1.0 - f
        t_val = f

        r = np.where(i == 0, 1.0,
            np.where(i == 1, q,
            np.where(i == 2, 0.0,
            np.where(i == 3, 0.0,
            np.where(i == 4, t_val, 1.0)))))

        g = np.where(i == 0, t_val,
            np.where(i == 1, 1.0,
            np.where(i == 2, 1.0,
            np.where(i == 3, q,
            np.where(i == 4, 0.0, 0.0)))))

        b = np.where(i == 0, 0.0,
            np.where(i == 1, 0.0,
            np.where(i == 2, t_val,
            np.where(i == 3, 1.0,
            np.where(i == 4, 1.0, q)))))

        rgba = np.stack([r, g, b, np.ones_like(r)], axis=-1).astype(np.float32)
        return rgba


# ===========================================================================
# SeafloorMapper
# ===========================================================================

class SeafloorMapper(QObject):
    """
    2.5D Seafloor Depth Map Builder.

    Accumulates SLAM points (NED frame), applies real depth correction,
    interpolates a regular grid, and exposes OpenGL-ready vertices + colours.

    Signals
    -------
    sig_mesh_updated : emitted when a new mesh has been built (GUI should
                       call get_mesh() and refresh the OpenGL viewport).
    """

    if _HAVE_QT:
        sig_mesh_updated = pyqtSignal()

    # Minimum seconds between consecutive mesh rebuilds (throttle)
    _REBUILD_INTERVAL_S: float = 1.0

    def __init__(
        self,
        grid_resolution: float = 0.5,
        max_points: int = 5_000,
        grid_size_m: float = 50.0,
        max_depth: float = 30.0,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Parameters
        ----------
        grid_resolution : cell size of the output grid (metres)
        max_points      : rolling window — oldest points evicted first
        grid_size_m     : maximum map extent in X and Y (metres)
        max_depth       : colourmap saturation depth (metres)
        """
        super().__init__(parent)

        if grid_resolution <= 0:
            raise ValueError("grid_resolution must be positive")
        if max_points < 10:
            raise ValueError("max_points must be ≥ 10")
        if grid_size_m <= 0:
            raise ValueError("grid_size_m must be positive")

        self._grid_res = float(grid_resolution)
        self._max_points = int(max_points)
        self._grid_size = float(grid_size_m)
        self._max_depth = float(max_depth)

        # Rolling buffer — each row is [x, y, z_corrected]
        self._buffer: deque = deque(maxlen=self._max_points)

        # Cached mesh outputs
        self._vertices: Optional[np.ndarray] = None   # (N, 3) float32
        self._colors:   Optional[np.ndarray] = None   # (N, 4) float32 RGBA
        self._triangles: Optional[np.ndarray] = None  # (M, 3) uint32

        # Throttle: track last rebuild time
        self._last_rebuild_t: float = 0.0

        if not _HAVE_SCIPY:
            logger.warning(
                "scipy not available — falling back to numpy nearest-neighbour "
                "interpolation. Install scipy for better map quality."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_slam_scan(
        self,
        points_ned: np.ndarray,
        rov_depth_m: float,
        rov_pos_ned: np.ndarray,
    ) -> None:
        """
        Ingest a SLAM point cloud and apply real-depth correction.

        Parameters
        ----------
        points_ned  : (N, 3) array of SLAM points in NED frame [m]
        rov_depth_m : absolute depth of the ROV from pressure sensor [m]
        rov_pos_ned : (3,) ROV position in NED used to compute relative
                      Z offset between SLAM origin and real depth
        """
        points_ned = np.asarray(points_ned, dtype=np.float64)
        if points_ned.ndim != 2 or points_ned.shape[1] != 3:
            raise ValueError("points_ned must have shape (N, 3)")

        rov_pos_ned = np.asarray(rov_pos_ned, dtype=np.float64)
        if rov_pos_ned.shape != (3,):
            raise ValueError("rov_pos_ned must have shape (3,)")

        if len(points_ned) == 0:
            return

        # Z-correction: shift SLAM z so that ROV position aligns with
        # the pressure-sensor depth reading.
        # NED: positive-down; rov_depth_m is positive downward.
        slam_z_at_rov = float(rov_pos_ned[2])
        z_offset = rov_depth_m - slam_z_at_rov

        corrected = points_ned.copy()
        corrected[:, 2] = corrected[:, 2] + z_offset

        # Feed into rolling buffer
        for row in corrected:
            self._buffer.append(row)

        # Throttled rebuild
        now = time.monotonic()
        if now - self._last_rebuild_t >= self._REBUILD_INTERVAL_S:
            self._rebuild_mesh()
            self._last_rebuild_t = now

    def get_mesh(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Return the latest mesh.

        Returns
        -------
        vertices  : (V, 3) float32 — XYZ positions
        colors    : (V, 4) float32 — RGBA colours per vertex
        triangles : (T, 3) uint32  — triangle indices into vertices
        """
        return self._vertices, self._colors, self._triangles

    def clear(self) -> None:
        """Discard all accumulated points and cached mesh."""
        self._buffer.clear()
        self._vertices = None
        self._colors = None
        self._triangles = None
        logger.debug("SeafloorMapper cleared")

    def get_stats(self) -> dict:
        """
        Return runtime statistics.

        Keys
        ----
        n_points    : number of points currently in buffer
        coverage_m2 : approximate XY area covered (convex bounding box)
        depth_range : (min_depth, max_depth) in metres; None if no data
        """
        n = len(self._buffer)
        if n == 0:
            return {"n_points": 0, "coverage_m2": 0.0, "depth_range": None}

        pts = np.array(self._buffer)
        x_range = float(pts[:, 0].max() - pts[:, 0].min())
        y_range = float(pts[:, 1].max() - pts[:, 1].min())
        coverage = x_range * y_range
        depth_range = (float(pts[:, 2].min()), float(pts[:, 2].max()))
        return {
            "n_points": n,
            "coverage_m2": coverage,
            "depth_range": depth_range,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_mesh(self) -> None:
        """
        Interpolate buffered points onto a regular grid and build
        triangle mesh arrays ready for OpenGL.
        """
        n = len(self._buffer)
        if n < 10:
            logger.debug("SeafloorMapper: not enough points (%d < 10), skipping rebuild", n)
            return

        pts = np.array(self._buffer, dtype=np.float64)
        xy = pts[:, :2]          # (N, 2)
        z  = pts[:, 2]           # (N,)  depth (NED positive-down)

        # ---- Build uniform XY grid ----
        x_min, x_max = xy[:, 0].min(), xy[:, 0].max()
        y_min, y_max = xy[:, 1].min(), xy[:, 1].max()

        # Clamp to configured map size, centred on data
        x_span = min(x_max - x_min, self._grid_size)
        y_span = min(y_max - y_min, self._grid_size)

        # Avoid degenerate grid (all points collinear or identical)
        if x_span < self._grid_res:
            x_min -= self._grid_res
            x_max = x_min + self._grid_res
        if y_span < self._grid_res:
            y_min -= self._grid_res
            y_max = y_min + self._grid_res

        nx = max(2, int(np.ceil((x_max - x_min) / self._grid_res)) + 1)
        ny = max(2, int(np.ceil((y_max - y_min) / self._grid_res)) + 1)

        # Cap grid resolution to avoid huge allocations
        MAX_GRID_CELLS = 512
        if nx > MAX_GRID_CELLS:
            nx = MAX_GRID_CELLS
        if ny > MAX_GRID_CELLS:
            ny = MAX_GRID_CELLS

        gx = np.linspace(x_min, x_max, nx)
        gy = np.linspace(y_min, y_max, ny)
        grid_x, grid_y = np.meshgrid(gx, gy)  # both shape (ny, nx)

        # ---- Interpolate depths onto grid ----
        z_grid = self._interpolate(xy, z, grid_x, grid_y)

        if z_grid is None:
            logger.warning("SeafloorMapper: interpolation returned None, skipping mesh build")
            return

        # ---- Build vertices ----
        # grid_x, grid_y, z_grid all shape (ny, nx)
        vx = grid_x.ravel().astype(np.float32)
        vy = grid_y.ravel().astype(np.float32)
        vz = z_grid.ravel().astype(np.float32)

        # Fill NaN with nearest valid depth (simple approach)
        nan_mask = np.isnan(vz)
        if nan_mask.all():
            logger.warning("SeafloorMapper: all interpolated values are NaN")
            return
        if nan_mask.any():
            valid_z = vz[~nan_mask]
            # Replace NaN with nearest valid value using index trick
            valid_idx = np.where(~nan_mask)[0]
            nan_idx   = np.where(nan_mask)[0]
            nearest   = valid_idx[np.abs(nan_idx[:, None] - valid_idx[None, :]).argmin(axis=1)]
            vz[nan_mask] = vz[nearest]

        self._vertices = np.stack([vx, vy, vz], axis=-1)  # (V, 3)

        # ---- Build colours ----
        self._colors = DepthColormap.depth_array_to_rgba(vz, max_depth=self._max_depth)  # (V, 4)

        # ---- Build triangle indices (vectorised, no Python loops) ----
        self._triangles = self._build_triangles(ny, nx)

        # Notify listeners
        if _HAVE_QT:
            try:
                self.sig_mesh_updated.emit()
            except RuntimeError:
                # Object deleted on Qt side
                pass

        logger.debug(
            "SeafloorMapper: mesh rebuilt — %d vertices, %d triangles",
            len(self._vertices),
            len(self._triangles) if self._triangles is not None else 0,
        )

    def _interpolate(
        self,
        xy: np.ndarray,
        z: np.ndarray,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
    ) -> Optional[np.ndarray]:
        """
        Interpolate scattered (x,y) → z data onto the meshgrid.

        Uses scipy.griddata if available (linear with 'nearest' fallback),
        otherwise falls back to a pure-numpy nearest-neighbour approach.
        """
        points = (grid_x, grid_y)

        if _HAVE_SCIPY:
            try:
                z_grid = _scipy_griddata(xy, z, points, method='linear')
                # Fill remaining NaN (extrapolation zones) with nearest
                nan_mask = np.isnan(z_grid)
                if nan_mask.any():
                    z_near = _scipy_griddata(xy, z, points, method='nearest')
                    z_grid[nan_mask] = z_near[nan_mask]
                return z_grid
            except Exception as exc:
                logger.warning("scipy griddata failed (%s); falling back to nearest-neighbour", exc)

        # --- Pure-numpy nearest-neighbour fallback ---
        return self._numpy_nearest(xy, z, grid_x, grid_y)

    @staticmethod
    def _numpy_nearest(
        xy: np.ndarray,
        z: np.ndarray,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
    ) -> np.ndarray:
        """
        Nearest-neighbour interpolation using vectorised numpy broadcasting.
        O(V * N) memory; acceptable for small grids (≤ 512² with ≤ 5000 pts).
        """
        pts_flat_x = grid_x.ravel()          # (V,)
        pts_flat_y = grid_y.ravel()          # (V,)

        src_x = xy[:, 0]                     # (N,)
        src_y = xy[:, 1]                     # (N,)

        # Squared distances: (V, N)
        dx = pts_flat_x[:, None] - src_x[None, :]
        dy = pts_flat_y[:, None] - src_y[None, :]
        dist2 = dx * dx + dy * dy

        nearest_idx = dist2.argmin(axis=1)   # (V,)
        z_flat = z[nearest_idx]              # (V,)
        return z_flat.reshape(grid_x.shape)

    @staticmethod
    def _build_triangles(ny: int, nx: int) -> np.ndarray:
        """
        Build triangle index array for a (ny × nx) grid using pure numpy.

        Each grid cell becomes 2 triangles (CCW winding):
          v0 = (row,   col)
          v1 = (row,   col+1)
          v2 = (row+1, col)
          v3 = (row+1, col+1)
          tri0 = (v0, v1, v2)
          tri1 = (v1, v3, v2)

        Returns
        -------
        triangles : ((ny-1)*(nx-1)*2, 3) uint32
        """
        # Row and column indices for top-left corner of each cell
        row = np.arange(ny - 1, dtype=np.uint32)
        col = np.arange(nx - 1, dtype=np.uint32)
        row_idx, col_idx = np.meshgrid(row, col, indexing='ij')  # (ny-1, nx-1)

        v0 = row_idx * nx + col_idx           # top-left
        v1 = v0 + 1                           # top-right
        v2 = v0 + nx                          # bottom-left
        v3 = v0 + nx + 1                      # bottom-right

        # Flatten and stack two triangles per cell
        v0 = v0.ravel()
        v1 = v1.ravel()
        v2 = v2.ravel()
        v3 = v3.ravel()

        tri0 = np.stack([v0, v1, v2], axis=-1)
        tri1 = np.stack([v1, v3, v2], axis=-1)

        return np.concatenate([tri0, tri1], axis=0)  # (M, 3) uint32
