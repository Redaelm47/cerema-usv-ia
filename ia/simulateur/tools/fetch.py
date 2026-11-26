"""Download raw data into tools/cache/ (idempotent: existing valid files are skipped).

Sources
  * IGN Geoplateforme WMS-R  https://data.geopf.fr/wms-r/wms
      - IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G  (LiDAR HD surface model, 0.5 m native)
      - ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES                     (RGE ALTI terrain model, 1-5 m native)
      - GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2                            (Plan IGN v2 map, used only to classify sea pixels)
      - ORTHOIMAGERY.ORTHOPHOTOS                                     (BD ORTHO / ortho mosaic, 0.2-0.5 m native, fetched as PNG)
    Requested in CRS:84 on the exact lon/lat bbox of each tile of the output grid
    (FORMAT=image/x-bil;bits=32 -> raw little-endian float32 for elevations).
  * EMODnet Bathymetry WCS 2.0.1  https://ows.emodnet-bathymetry.eu/wcs  coverage emodnet__mean
    (DTM 2024, 1/16 arc-minute, depths referred to LAT), as GeoTools text grid.

Usage:  python3 tools/fetch.py            (everything)
        python3 tools/fetch.py near far   (subset of jobs: far, near, mask, ortho, bathy)
Nothing downloaded is ever executed; files are parsed as raw numbers/images only.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import (CACHE, FAR, FAR_LIDAR, FAR_ORTHO_RES, FAR_RGE_RES, NEAR, NEAR_LIDAR,  # noqa: E402
                 NEAR_ORTHO_RES, NEAR_RGE_RES, Grid)

WMS_URL = "https://data.geopf.fr/wms-r/wms"
WCS_URL = "https://ows.emodnet-bathymetry.eu/wcs"
UA = "brest-maritime-sim-dataprep/0.1 (python-requests)"

LAYER_LIDAR_MNS = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G"
LAYER_RGEALTI = "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"
LAYER_ORTHO = "ORTHOIMAGERY.ORTHOPHOTOS"
LAYER_PLAN = "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
PLAN_FAR_RES = 5.0   # Plan IGN rendering used only as a land/sea classifier
PLAN_NEAR_RES = 4.0

# Bathymetry subset (wider than the far bbox so interpolation has margins)
BATHY_LAT = (48.15, 48.53)
BATHY_LON = (-4.92, -4.14)

MAX_TILE = 2500      # server MaxWidth/MaxHeight is 5010; stay well below
DELAY = 0.8          # seconds between successful requests
TRIES = 6

_session = requests.Session()
_session.headers["User-Agent"] = UA


def _download(url: str, params: dict, dest: Path, validate) -> Path:
    if dest.exists():
        try:
            if validate(dest.read_bytes(), None):
                return dest
        except Exception:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(TRIES):
        try:
            r = _session.get(url, params=params, timeout=300)
            ctype = r.headers.get("Content-Type", "")
            if r.status_code == 200 and validate(r.content, ctype):
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(dest)
                print(f"  ok  {dest.relative_to(CACHE)}  ({len(r.content) / 1e6:.1f} MB)", flush=True)
                time.sleep(DELAY)
                return dest
            last = f"HTTP {r.status_code} {ctype} {r.content[:300]!r}"
        except requests.RequestException as e:  # network error -> retry
            last = repr(e)
        wait = min(90, 3 * 2 ** attempt)
        print(f"  retry {attempt + 1}/{TRIES} for {dest.name} in {wait}s: {last}", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"failed to download {dest}: {last}")


def tile_plan(width: int, height: int, max_tile: int = MAX_TILE):
    nc = math.ceil(width / max_tile)
    nr = math.ceil(height / max_tile)
    cols = [round(i * width / nc) for i in range(nc + 1)]
    rows = [round(i * height / nr) for i in range(nr + 1)]
    return [(rows[i], rows[i + 1], cols[j], cols[j + 1]) for i in range(nr) for j in range(nc)]


def _short(layer: str) -> str:
    return {LAYER_LIDAR_MNS: "lidarhd_mns", LAYER_RGEALTI: "rgealti", LAYER_ORTHO: "ortho",
            LAYER_PLAN: "planign"}.get(layer, layer)


def wms_grid(layer: str, grid: Grid, fmt: str) -> dict:
    """Fetch `layer` over `grid` as tiles. Returns a manifest dict (also written to cache)."""
    is_bil = fmt.startswith("image/x-bil")
    ext = "bil" if is_bil else ("png" if fmt == "image/png" else "jpg")
    sub = CACHE / "wms" / _short(layer) / grid.tag
    tiles = []
    plan = tile_plan(grid.width, grid.height)
    print(f"[wms] {layer} {grid.tag}: {grid.width}x{grid.height} px in {len(plan)} tiles", flush=True)
    for (r0, r1, c0, c1) in plan:
        w, h = c1 - c0, r1 - r0
        lon0, lat0, lon1, lat1 = grid.window_lonlat(r0, r1, c0, c1)
        params = {
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
            "LAYERS": layer, "STYLES": "", "CRS": "CRS:84",
            "BBOX": f"{lon0:.10f},{lat0:.10f},{lon1:.10f},{lat1:.10f}",
            "WIDTH": str(w), "HEIGHT": str(h), "FORMAT": fmt,
        }
        if is_bil:
            def validate(b, ctype, n=w * h * 4):
                return len(b) == n and (ctype is None or ctype.startswith("image/x-bil"))
        elif fmt == "image/png":
            def validate(b, ctype):
                return len(b) > 1000 and b[:4] == b"\x89PNG" and (ctype is None or ctype.startswith("image/png"))
        else:
            def validate(b, ctype):
                return len(b) > 1000 and b[:2] == b"\xff\xd8" and (ctype is None or ctype.startswith("image/jpeg"))
        dest = sub / f"r{r0}-{r1}_c{c0}-{c1}.{ext}"
        _download(WMS_URL, params, dest, validate)
        tiles.append(dict(file=str(dest.relative_to(CACHE)), r0=r0, r1=r1, c0=c0, c1=c1, bbox=[lon0, lat0, lon1, lat1]))
    manifest = dict(layer=layer, grid=grid.name, res=grid.res, res_y=grid.ry, width=grid.width, height=grid.height,
                    extent=grid.extent_dict(), format=fmt, tiles=tiles)
    (sub / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def emodnet() -> Path:
    print("[wcs] EMODnet emodnet__mean", flush=True)
    params = [
        ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
        ("coverageId", "emodnet__mean"),
        ("subset", f"Lat({BATHY_LAT[0]},{BATHY_LAT[1]})"),
        ("subset", f"Long({BATHY_LON[0]},{BATHY_LON[1]})"),
        ("format", "text/plain"),
    ]

    def validate(b, ctype):
        return len(b) > 10000 and b"Band 0" in b[:5000] and (ctype is None or ctype.startswith("text/plain"))

    return _download(WCS_URL, params, CACHE / "emodnet" / "emodnet_mean_brest.txt", validate)


def main(jobs):
    if "far" in jobs:
        wms_grid(LAYER_LIDAR_MNS, FAR.with_res(**FAR_LIDAR), "image/x-bil;bits=32")
        wms_grid(LAYER_RGEALTI, FAR.with_res(FAR_RGE_RES, "far"), "image/x-bil;bits=32")
    if "near" in jobs:
        wms_grid(LAYER_LIDAR_MNS, NEAR.with_res(**NEAR_LIDAR), "image/x-bil;bits=32")
        wms_grid(LAYER_RGEALTI, NEAR.with_res(NEAR_RGE_RES, "near"), "image/x-bil;bits=32")
    if "mask" in jobs:
        wms_grid(LAYER_PLAN, FAR.with_res(PLAN_FAR_RES, "far"), "image/png")
        wms_grid(LAYER_PLAN, NEAR.with_res(PLAN_NEAR_RES, "near"), "image/png")
    if "bathy" in jobs:
        emodnet()
    if "ortho" in jobs:
        # PNG avoids a second lossy JPEG generation (server JPEG output is ~q60);
        # the final JPEG (q85) is encoded once in build.py.
        wms_grid(LAYER_ORTHO, FAR.with_res(FAR_ORTHO_RES, "far"), "image/png")
        wms_grid(LAYER_ORTHO, NEAR.with_res(NEAR_ORTHO_RES, "near"), "image/png")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or {"far", "near", "mask", "bathy", "ortho"})
