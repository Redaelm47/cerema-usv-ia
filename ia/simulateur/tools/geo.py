"""Shared geographic frame and grid definitions for the Goulet / Rade de Brest data.

Local metric frame (north-aligned, "equirectangular" around the origin):
    x = (lon - LON0) * MX      metres east
    n = (lat - LAT0) * MY      metres north
with constant scale factors evaluated at LAT0. Because MX and MY are constants,
a regular grid in (x, n) is also a regular grid in (lon, lat), so WMS/WCS
requests in CRS:84 with the exact lon/lat bbox return pixel-aligned rasters.

Grid convention used for every output raster:
    row 0 = north edge, column 0 = west edge,
    extents {xWest, xEast, nSouth, nNorth} are the OUTER pixel edges,
    pixel (r, c) centre = (xWest + (c + 0.5) * res, nNorth - (r + 0.5) * res).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
CACHE = TOOLS / "cache"
OUT = ROOT / "public" / "data"

LAT0 = 48.345
LON0 = -4.56
_PHI = math.radians(LAT0)
MX = 111412.84 * math.cos(_PHI) - 93.5 * math.cos(3 * _PHI) + 0.118 * math.cos(5 * _PHI)  # m / deg lon
MY = 111132.92 - 559.82 * math.cos(2 * _PHI) + 1.175 * math.cos(4 * _PHI)  # m / deg lat

# Requested areas (lon_min, lon_max, lat_min, lat_max)
FAR_BBOX = (-4.78, -4.28, 48.25, 48.43)
NEAR_BBOX = (-4.66, -4.415, 48.315, 48.40)  # Goulet + Brest waterfront (Penfeld, port de commerce, Moulin Blanc)

# Extents are snapped outward to a multiple of SNAP metres so that 15 m, 8 m,
# 4 m and 2 m grids all divide them exactly and near-grid pixel edges fall on
# far-grid pixel edges.
SNAP = 120.0


def ll_to_local(lon, lat):
    return (np.asarray(lon) - LON0) * MX, (np.asarray(lat) - LAT0) * MY


def local_to_ll(x, n):
    return LON0 + np.asarray(x) / MX, LAT0 + np.asarray(n) / MY


def snapped_extent(bbox, snap=SNAP):
    lon_min, lon_max, lat_min, lat_max = bbox
    xw, ns = ll_to_local(lon_min, lat_min)
    xe, nn = ll_to_local(lon_max, lat_max)
    eps = 1e-6
    return dict(
        xWest=math.floor(float(xw) / snap + eps) * snap,
        xEast=math.ceil(float(xe) / snap - eps) * snap,
        nSouth=math.floor(float(ns) / snap + eps) * snap,
        nNorth=math.ceil(float(nn) / snap - eps) * snap,
    )


@dataclass(frozen=True)
class Grid:
    name: str
    xWest: float
    xEast: float
    nSouth: float
    nNorth: float
    res: float                      # pixel size east-west (m)
    res_y: float | None = None      # pixel size north-south (m); defaults to res

    @property
    def ry(self) -> float:
        return self.res_y if self.res_y is not None else self.res

    @property
    def width(self) -> int:
        return int(round((self.xEast - self.xWest) / self.res))

    @property
    def height(self) -> int:
        return int(round((self.nNorth - self.nSouth) / self.ry))

    def with_res(self, res: float, name: str | None = None, res_y: float | None = None) -> "Grid":
        g = Grid(name or self.name, self.xWest, self.xEast, self.nSouth, self.nNorth, res, res_y)
        assert abs(g.width * g.res - (self.xEast - self.xWest)) < 1e-6, "extent not divisible by res"
        assert abs(g.height * g.ry - (self.nNorth - self.nSouth)) < 1e-6, "extent not divisible by res"
        return g

    @property
    def tag(self) -> str:
        return f"{self.name}_{self.res:g}m" if self.res_y is None else f"{self.name}_{self.res:.4g}x{self.ry:g}m"

    def window_lonlat(self, r0: int, r1: int, c0: int, c1: int):
        """lon/lat bbox (outer edges) of rows [r0, r1) and columns [c0, c1)."""
        x0 = self.xWest + c0 * self.res
        x1 = self.xWest + c1 * self.res
        n1 = self.nNorth - r0 * self.ry
        n0 = self.nNorth - r1 * self.ry
        lon0, lat0 = local_to_ll(x0, n0)
        lon1, lat1 = local_to_ll(x1, n1)
        return float(lon0), float(lat0), float(lon1), float(lat1)

    def lonlat_bbox(self):
        return self.window_lonlat(0, self.height, 0, self.width)

    def centers(self):
        """1-D arrays of pixel-centre x (per column) and n (per row)."""
        xs = self.xWest + (np.arange(self.width) + 0.5) * self.res
        ns = self.nNorth - (np.arange(self.height) + 0.5) * self.ry
        return xs, ns

    def extent_dict(self):
        return dict(xWest=self.xWest, xEast=self.xEast, nSouth=self.nSouth, nNorth=self.nNorth)

    def local_to_pixel(self, x, n):
        """Fractional (row, col) index of local coordinates (pixel centres at integers)."""
        col = (np.asarray(x) - self.xWest) / self.res - 0.5
        row = (self.nNorth - np.asarray(n)) / self.ry - 0.5
        return row, col


FAR = Grid("far", res=15.0, **snapped_extent(FAR_BBOX))
NEAR = Grid("near", res=4.0, **snapped_extent(NEAR_BBOX))

# Resolutions
FAR_DEM_RES = 15.0
NEAR_DEM_RES = 4.0
FAR_ORTHO_RES = 8.0
NEAR_ORTHO_RES = 2.5  # 2.5 m keeps the GPU texture size of the former 2 m tile
# The LiDAR HD WMS layer is served from a pyramid with square pixels in DEGREES and
# nearest-neighbour resampling; requesting square-metre pixels duplicates rows.
# So the LiDAR is fetched on a grid whose pixels are (almost exactly) square in degrees
# (x step = 1/3 of the output pixel, y step = 1/2; MY/MX = 1.5001) and then max-pooled
# 3 (x) by 2 (y) into the output pixel (keeps roofs, tree tops, lighthouses in the skyline).
LIDAR_POOL = (2, 3)  # (rows, cols)
# RGE ALTI: far grid fetched at 5 m and max-pooled 3x3 (keeps thin breakwaters / jetties)
FAR_RGE_RES = 5.0
NEAR_RGE_RES = 4.0
FAR_LIDAR = dict(res=FAR_DEM_RES / 3, res_y=FAR_DEM_RES / 2)     # 5 m x 7.5 m
NEAR_LIDAR = dict(res=NEAR_DEM_RES / 3, res_y=NEAR_DEM_RES / 2)  # 1.333 m x 2 m


if __name__ == "__main__":
    print(f"MX = {MX:.4f} m/deg lon, MY = {MY:.4f} m/deg lat")
    for g in (FAR, NEAR):
        print(g.name, g.extent_dict(), g.width, "x", g.height, "@", g.res, "m;  lonlat bbox", g.lonlat_bbox())
    print("far ortho", FAR.with_res(FAR_ORTHO_RES).width, FAR.with_res(FAR_ORTHO_RES).height)
    print("near ortho", NEAR.with_res(NEAR_ORTHO_RES).width, NEAR.with_res(NEAR_ORTHO_RES).height)
