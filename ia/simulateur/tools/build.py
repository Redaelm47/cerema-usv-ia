"""Build the terrain products in public/data/ from the raw downloads in tools/cache/.

Outputs: dem_far.bin, dem_near.bin (Int16 LE, decimetres), ortho_far.jpg, ortho_near.jpg,
terrain.json (metadata). Run tools/fetch.py first, then tools/places.py and tools/preview.py.

Per DEM grid:
  L  IGN LiDAR HD surface model (MNS: ground + buildings + trees), fetched on a grid of
     degree-square pixels (1/3 x 1/2 of the output pixel), no-data ring removed, then
     max-pooled 3x2 into the output pixel (keeps roofs, tree tops, lighthouses).
  R  IGN RGE ALTI terrain model (DTM) on the output grid (far: 5 m max-pooled 3x3). Its
     flattened water surfaces (constant -2.79 m sea band, flat estuaries) are discarded.
  P  water mask from the Plan IGN v2 rendering (sea / estuary fill colour).
Classification:
  firm ground  (R >= 1 m)                     -> L (R where LiDAR is masked, e.g. military sites)
  foreshore    (R < 1 m, not water in P)      -> min(L, R) (ground only: boats / bridge decks dropped)
  structures   (outside R, not water, LiDAR >= 1 m and rough) -> L (new port polder, rocks)
               except long narrow high decks over water (bridges) which become water
  water        (P & not firm ground) | (outside R & not structure), 4-connected to the open
               sea -> seabed: smooth-min of EMODnet (LAT -> IGN69) and a nearshore slope
               (0.05 .. 0.20 depending on the coast height) starting ~0.3 m below 0 at the
               shoreline; measured submerged foreshore (R < 0) is kept where shallower.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import (CACHE, FAR, FAR_LIDAR, FAR_ORTHO_RES, FAR_RGE_RES, LAT0, LON0, MX, MY, NEAR,  # noqa: E402
                 NEAR_LIDAR, NEAR_ORTHO_RES, NEAR_RGE_RES, OUT, Grid, local_to_ll)

Image.MAX_IMAGE_PIXELS = None

# Vertical datum: EMODnet DTM depths refer to Lowest Astronomical Tide. At Brest the
# chart datum (zero hydrographique ~ LAT) lies 3.64 m below the IGN69 (NGF) zero
# (SHOM "References Altimetriques Maritimes"). IGN elevations are IGN69.
LAT_TO_NGF = -3.64
D0 = 0.3            # depth (m) right at the shoreline
# max nearshore seabed slope (m depth per m distance from land), interpolated between
# K_GENTLE where the adjacent land is <= K_LOW_Z m high (beach, mudflat) and K_STEEP where
# it is >= K_HIGH_Z m (cliff, quay wall, breakwater)
K_GENTLE, K_STEEP = 0.05, 0.20
K_LOW_Z, K_HIGH_Z = 0.5, 4.0
COAST_RADIUS_M = 30.0
SMOOTH_H = 3.0      # smooth-min blending width (m)
SHORE_DEPTH_MAX = 10.0   # cap on the starting depth taken from a submerged foreshore
SHORE_SMOOTH_M = 40.0    # along-shore smoothing of that starting depth
FLOOR_DECAY_M = 150.0    # distance over which the foreshore depth stops constraining the bathymetry
SEA_SMOOTH_M = 30.0      # gaussian sigma of the final seabed smoothing (sea pixels only)

BUILD = CACHE / "build"


# ----------------------------------------------------------------------------- io
def load_manifest(layer_short: str, grid_name: str, res: float, res_y: float | None = None) -> dict:
    tag = f"{grid_name}_{res:g}m" if res_y is None else f"{grid_name}_{res:.4g}x{res_y:g}m"
    p = CACHE / "wms" / layer_short / tag / "manifest.json"
    return json.loads(p.read_text())


def mosaic_bil(m: dict) -> np.ndarray:
    a = np.empty((m["height"], m["width"]), np.float32)
    for t in m["tiles"]:
        h, w = t["r1"] - t["r0"], t["c1"] - t["c0"]
        a[t["r0"]:t["r1"], t["c0"]:t["c1"]] = np.fromfile(CACHE / t["file"], "<f4").reshape(h, w)
    return a


def mosaic_rgb(m: dict) -> Image.Image:
    im = Image.new("RGB", (m["width"], m["height"]))
    for t in m["tiles"]:
        tile = Image.open(CACHE / t["file"]).convert("RGB")
        assert tile.size == (t["c1"] - t["c0"], t["r1"] - t["r0"]), (t, tile.size)
        im.paste(tile, (t["c0"], t["r0"]))
    return im


def parse_emodnet(path: Path):
    """GeoTools text grid -> (lon_centres, lat_centres (N->S), values[row, col])."""
    txt = path.read_text()
    head, body = txt.split("Band 0:", 1)
    gr = re.search(r"GridEnvelope2D\[(\d+)\.\.(\d+), (\d+)\.\.(\d+)\]", head)
    w = int(gr.group(2)) - int(gr.group(1)) + 1
    h = int(gr.group(4)) - int(gr.group(3)) + 1

    def p(name):
        return float(re.search(rf'PARAMETER\["{name}", ([-0-9.Ee]+)\]', head).group(1))

    dx, x0, dy, y0 = p("elt_0_0"), p("elt_0_2"), p("elt_1_1"), p("elt_1_2")
    vals = np.array(body.split(), dtype=np.float64)
    assert vals.size == w * h, (vals.size, w, h)
    vals = vals.reshape(h, w)
    lons = x0 + dx * np.arange(w)   # GeoTools grid->world maps integer indices to pixel centres
    lats = y0 + dy * np.arange(h)
    return lons, lats, vals


# ----------------------------------------------------------------------------- helpers
def clean_nodata(a: np.ndarray, thresh: float, ring: int) -> np.ndarray:
    a = a.copy()
    bad = ~np.isfinite(a) | (a < thresh)
    if ring:
        bad = ndimage.binary_dilation(bad, iterations=ring)
    a[bad] = np.nan
    return a


def pool_max(a: np.ndarray, fy: int, fx: int) -> np.ndarray:
    """NaN-aware max over fy x fx blocks (all-NaN blocks stay NaN)."""
    h, w = a.shape
    assert h % fy == 0 and w % fx == 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(a.reshape(h // fy, fy, w // fx, fx), axis=(1, 3))


def fill_nearest(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if valid.all():
        return a
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return a[tuple(idx)]


def smooth_min(a, b, h):
    """Polynomial smooth minimum (C1), equals min(a, b) when |a-b| > h."""
    k = np.clip(0.5 + 0.5 * (b - a) / h, 0.0, 1.0)
    return b * (1 - k) + a * k - h * k * (1 - k)


class Bathy:
    def __init__(self):
        lons, lats, v = parse_emodnet(CACHE / "emodnet" / "emodnet_mean_brest.txt")
        self.lons, self.lats = lons, lats
        self.raw = v                                    # LAT-referenced elevation (land included)
        ngf = v + LAT_TO_NGF
        # cells that are land / above MSL or missing: replace by the nearest sea cell
        # (the nearshore profile is then driven by the distance-to-land slope).
        sea = np.isfinite(ngf) & (ngf < -D0)
        self.ngf = fill_nearest(np.where(sea, ngf, 0.0), sea)
        self.sea_cells = sea

    def sample(self, lon, lat, order=3):
        col = (np.asarray(lon) - self.lons[0]) / (self.lons[1] - self.lons[0])
        row = (np.asarray(lat) - self.lats[0]) / (self.lats[1] - self.lats[0])
        out = ndimage.map_coordinates(self.ngf, [row.ravel(), col.ravel()], order=order, mode="nearest")
        return np.minimum(out.reshape(np.shape(row)), -D0)


# ----------------------------------------------------------------------------- DEM
PLAN_SEA_RGB = (170, 213, 233)   # Plan IGN v2 sea / water fill colour
PLAN_FAR_RES = 5.0
PLAN_NEAR_RES = 4.0
LOW = 1.0            # m IGN69: RGE ground below this is "low" (foreshore, channels, port basins)
ROUGH_MIN = 0.03     # m: LiDAR roughness separating measured ground from TIN-interpolated water


def plan_sea_mask(grid: Grid, plan_res: float) -> np.ndarray:
    """Sea/water pixels of the Plan IGN v2 rendering, resampled to `grid` (block majority)."""
    im = np.asarray(mosaic_rgb(load_manifest("planign", grid.name, plan_res))).astype(np.int16)
    raw = np.abs(im - np.array(PLAN_SEA_RGB)).sum(-1) < 24
    # opening removes the isolated blue dots of the foreshore ("estran") hatching
    sea = ndimage.binary_opening(raw, structure=np.ones((3, 3)))
    f = int(round(grid.res / plan_res))
    if f > 1:
        h, w = sea.shape
        sea = sea.reshape(h // f, f, w // f, f).mean(axis=(1, 3)) >= 0.5
    assert sea.shape == (grid.height, grid.width), sea.shape
    return sea


RGE_SEA_FILL = -2.79   # value RGE ALTI stores on the flattened sea surface of its coastal band


def drop_rge_water_fill(R: np.ndarray) -> np.ndarray:
    """RGE ALTI flattens water: the coastal sea band is a constant -2.79 m and estuaries / ponds are
    perfectly flat. Those are not ground; turn them into no-data."""
    f = np.where(np.isfinite(R), R, 0.0).astype(np.float64)
    m1 = ndimage.uniform_filter(f, 5)
    sd = np.sqrt(np.maximum(ndimage.uniform_filter(f * f, 5) - m1 * m1, 0.0))
    fill = np.isfinite(R) & ((np.abs(R - RGE_SEA_FILL) < 0.02) | ((sd < 0.005) & (R < 0.5)))
    out = R.copy()
    out[fill] = np.nan
    return out


BRIDGE_MIN_Z = 10.0       # m: decks high above the water ...
BRIDGE_MIN_LEN = 150.0    # ... long ...
BRIDGE_MAX_WIDTH = 40.0   # ... and narrow are bridges (a heightfield would turn them into dams)


def bridge_decks(hi: np.ndarray, res: float) -> np.ndarray:
    """Long, narrow, high LiDAR structures standing over water (bridge decks)."""
    lab, n = ndimage.label(hi, structure=np.ones((3, 3)))
    out = np.zeros_like(hi)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        m = lab[sl] == i
        length = np.hypot(*(np.array(m.shape) * res))
        area = m.sum() * res * res
        if length >= BRIDGE_MIN_LEN and area / length <= BRIDGE_MAX_WIDTH:
            out[sl] |= m
    return out


def roughness(a: np.ndarray) -> np.ndarray:
    """RMS of the 3x3 high-pass of `a` over 5x5 windows (same grid as `a`)."""
    f = np.where(np.isfinite(a), a, 0.0).astype(np.float64)
    hp = f - ndimage.uniform_filter(f, 3)
    r = np.sqrt(np.maximum(ndimage.uniform_filter(hp * hp, 5), 0)).astype(np.float32)
    r[~np.isfinite(a)] = np.nan
    return r


def build_dem(grid: Grid, lidar: dict, rge_res: float, plan_res: float, bathy: Bathy, tag: str):
    print(f"[dem] {tag}: {grid.width}x{grid.height} @ {grid.res} m", flush=True)
    L2 = clean_nodata(mosaic_bil(load_manifest("lidarhd_mns", grid.name, lidar["res"], lidar["res_y"])),
                      -20.0, ring=1)
    fy, fx = int(round(grid.res / lidar["res_y"])), int(round(grid.res / lidar["res"]))
    L = pool_max(L2, fy, fx)
    rough = pool_max(roughness(L2), fy, fx)
    del L2
    assert L.shape == (grid.height, grid.width), L.shape
    R = clean_nodata(mosaic_bil(load_manifest("rgealti", grid.name, rge_res)), -50.0, ring=0)
    R = drop_rge_water_fill(R)
    f = int(round(grid.res / rge_res))
    if f > 1:
        R = pool_max(R, f, f)
    P = plan_sea_mask(grid, plan_res)
    Lv, Rv = np.isfinite(L), np.isfinite(R)

    # LiDAR seeing water / ground clearly below an RGE ALTI value near sea level means the RGE
    # surface there is interpolated or outdated (coves, eroded foreshore): trust the LiDAR.
    lower = Lv & Rv & (L < R - 0.5) & (L < LOW)
    solid = Rv & (R >= LOW) & ~lower             # firm ground in the RGE ALTI terrain model
    low = Rv & ~solid                            # foreshore / channels / basins (ground < 1 m)
    # LiDAR-measured structures outside the RGE ALTI domain and not mapped as water
    # (recent port polder, breakwaters, offshore rocks); TIN-interpolated water is smooth.
    struct = ~Rv & ~P & Lv & (L >= LOW) & (rough >= ROUGH_MIN)
    struct &= ~bridge_decks(struct & (L >= BRIDGE_MIN_Z), grid.res)
    z_low = np.where(Lv, np.minimum(L, R), R)   # foreshore ground (drops boats, bridge decks, water surface)
    # water candidates: mapped water that is not firm ground, and everything outside the RGE ALTI
    # domain (flattened RGE water surfaces already removed) that is not a measured structure
    water = (P & ~solid) | (~Rv & ~struct)
    lab, n = ndimage.label(water)
    seeds = np.bincount(lab[water & ~Rv & P], minlength=n + 1)
    keep = seeds >= 20
    keep[0] = False
    sea = keep[lab]
    land = ~sea

    z = np.full(L.shape, np.nan, np.float32)
    m = land & solid
    z[m] = np.where(Lv, L, R)[m]                 # LiDAR surface (buildings, trees) on firm ground
    m = land & low
    z[m] = z_low[m]                              # foreshore >= 0 m and isolated low pockets
    m = land & ~Rv & Lv
    z[m] = L[m]                                  # structures beyond RGE, isolated pockets
    still = land & ~np.isfinite(z)
    if still.any():
        ok = land & np.isfinite(z)
        z = np.where(still, fill_nearest(np.where(ok, z, 0), ok), z)
    dropped = sea & Lv & (L >= LOW)
    print(f"  LiDAR >= {LOW} m dropped as water (ships, TIN water, bridge decks): "
          f"{dropped.sum() * grid.res ** 2 / 1e4:.1f} ha; kept off-RGE structures "
          f"{(land & struct).sum() * grid.res ** 2 / 1e4:.1f} ha; "
          f"land without LiDAR (filled from RGE ALTI): {(land & solid & ~Lv).sum() * grid.res ** 2 / 1e4:.1f} ha; "
          f"nearest-filled: {int(still.sum())} px", flush=True)

    # --- sea depths: smooth-min of bathymetry and a nearshore slope that starts at the
    #     (along-shore smoothed) depth of the adjacent non-sea pixel, so a foreshore that is
    #     already at -2 m continues downwards instead of meeting a -0.3 m lip.
    boundary = land & ndimage.binary_dilation(sea, structure=np.ones((3, 3)))
    bd = np.where(boundary, np.clip(-z, D0, SHORE_DEPTH_MAX), 0.0).astype(np.float64)
    # nearshore slope: steep along cliffs / quays / breakwaters, gentle along low shores
    # coast height = highest land within COAST_RADIUS_M of the boundary pixel (resolution independent:
    # a cliff behind a strip of low rocks still counts as a steep coast)
    rpx = max(1, int(round(COAST_RADIUS_M / grid.res)))
    yy, xx = np.mgrid[-rpx:rpx + 1, -rpx:rpx + 1]
    coast_h = ndimage.maximum_filter(np.where(land, z, -1e3), footprint=(xx * xx + yy * yy) <= rpx * rpx)
    zb_land = np.where(boundary, np.clip((coast_h - K_LOW_Z) / (K_HIGH_Z - K_LOW_Z), 0.0, 1.0), 0.0)
    kb = np.where(boundary, K_GENTLE + (K_STEEP - K_GENTLE) * zb_land, 0.0)
    sig = max(1.0, SHORE_SMOOTH_M / grid.res)
    den = ndimage.gaussian_filter(boundary.astype(np.float64), sig)
    den = np.maximum(den, 1e-9)
    sd_field = ndimage.gaussian_filter(bd, sig) / den
    k_field = ndimage.gaussian_filter(kb, sig) / den
    dist, inds = ndimage.distance_transform_edt(sea, return_indices=True)
    dist = dist[sea] * grid.res
    shore_depth = sd_field[inds[0][sea], inds[1][sea]]
    k_slope = k_field[inds[0][sea], inds[1][sea]]
    floor = shore_depth * np.exp(-dist / FLOOR_DECAY_M)
    xs, ns = grid.centers()
    lon, lat = local_to_ll(xs[None, :], ns[:, None])
    lon = np.broadcast_to(lon, sea.shape)[sea]
    lat = np.broadcast_to(lat, sea.shape)[sea]
    d_bathy = -bathy.sample(lon, lat)
    d_slope = shore_depth + k_slope * dist
    depth = np.maximum(smooth_min(np.maximum(d_bathy, floor), d_slope, SMOOTH_H), D0)
    # light smoothing over sea pixels only (removes the medial-axis creases of the distance
    # field), faded in from the shoreline so the shore depth stays ~D0
    full = np.zeros(sea.shape, np.float64)
    full[sea] = depth
    sig = max(1.0, SEA_SMOOTH_M / grid.res)
    sm = ndimage.gaussian_filter(full, sig) / np.maximum(ndimage.gaussian_filter(sea.astype(np.float64), sig), 1e-6)
    w = np.clip(dist / (3.0 * SEA_SMOOTH_M), 0.0, 1.0)
    depth = np.maximum((1 - w) * depth + w * sm[sea], D0)
    z[sea] = -depth
    # keep measured submerged ground (reefs, shoals, mudflats surveyed at low tide in RGE ALTI / Litto3D)
    # where it is shallower than the blended seabed
    shoal = sea & low & (z_low < 0.0)
    z[shoal] = np.maximum(z[shoal], z_low[shoal])
    z = z.astype(np.float32)
    assert np.isfinite(z).all()
    print(f"  sea {sea.mean() * 100:.1f}%  land {land.mean() * 100:.1f}%  "
          f"z range {z.min():.1f} .. {z.max():.1f} m", flush=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BUILD / f"{tag}_masks.npz", sea=sea, plan_sea=P, lidar_valid=Lv, rge_valid=Rv,
                        struct=land & struct, dropped=dropped, low=land & low)
    return z, sea


def write_dem(z: np.ndarray, path: Path):
    q = np.clip(np.round(z * 10.0), -32768, 32767).astype("<i2")
    q.tofile(path)
    return q


def write_ortho(grid_name: str, res: float, path: Path):
    m = load_manifest("ortho", grid_name, res)
    im = mosaic_rgb(m)
    im.save(path, "JPEG", quality=85, optimize=True, progressive=True)
    print(f"[ortho] {path.name}: {im.size[0]}x{im.size[1]} @ {res} m", flush=True)
    return im.size


def consistency(z_far, z_near):
    """Compare dem_near with dem_far where they overlap (same datum, same sources).

    'box16': near box-averaged over 4x4 px (~16 m) vs far bilinear at the near pixel centres.
    'max15': far pixel vs the max of the near pixels whose centres fall inside it (like-for-like
             with the far DEM's max-pooling)."""
    xs, ns = NEAR.centers()
    r, c = FAR.local_to_pixel(xs[None, :], ns[:, None])
    r = np.broadcast_to(r, z_near.shape)
    c = np.broadcast_to(c, z_near.shape)
    zf = ndimage.map_coordinates(z_far, [r.ravel(), c.ravel()], order=1, mode="nearest").reshape(z_near.shape)
    zn = ndimage.uniform_filter(z_near, size=4)

    def stats(d):
        return dict(n=int(d.size), mean=round(float(d.mean()), 2), median=round(float(np.median(d)), 2),
                    p05=round(float(np.percentile(d, 5)), 2), p95=round(float(np.percentile(d, 95)), 2))

    out = {"land_box16": stats((zn - zf)[(zn > 2) & (zf > 2)]),
           "sea_box16": stats((zn - zf)[(zn < -5) & (zf < -5)])}
    ri = np.floor(r + 0.5).astype(int)
    ci = np.floor(c + 0.5).astype(int)
    mx = np.full(z_far.shape, -np.inf)
    np.maximum.at(mx, (ri.ravel(), ci.ravel()), z_near.ravel())
    cnt = np.zeros(z_far.shape, int)
    np.add.at(cnt, (ri.ravel(), ci.ravel()), 1)
    full = cnt >= 12
    m = full & (mx > 2) & (z_far > 2)
    out["land_max15"] = stats((mx - z_far)[m])
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bathy = Bathy()
    print(f"[bathy] EMODnet grid {bathy.raw.shape[1]}x{bathy.raw.shape[0]} cells, "
          f"sea cells {bathy.sea_cells.mean() * 100:.0f}%", flush=True)

    z_far, sea_far = build_dem(FAR, FAR_LIDAR, FAR_RGE_RES, PLAN_FAR_RES, bathy, "far")
    q_far = write_dem(z_far, OUT / "dem_far.bin")
    z_near, sea_near = build_dem(NEAR, NEAR_LIDAR, NEAR_RGE_RES, PLAN_NEAR_RES, bathy, "near")
    q_near = write_dem(z_near, OUT / "dem_near.bin")
    cons = consistency(z_far, z_near)
    print("[check] near - far (near box-averaged to ~16 m):", cons, flush=True)

    of = FAR.with_res(FAR_ORTHO_RES)
    on = NEAR.with_res(NEAR_ORTHO_RES)
    write_ortho("far", FAR_ORTHO_RES, OUT / "ortho_far.jpg")
    write_ortho("near", NEAR_ORTHO_RES, OUT / "ortho_near.jpg")

    def dem_entry(fname, grid: Grid, q, src, fetch_res):
        lon0, lat0, lon1, lat1 = grid.lonlat_bbox()
        return {
            "file": fname, "width": grid.width, "height": grid.height, "metresPerPixel": grid.res,
            "extent": grid.extent_dict(),
            "lonLatExtent": {"west": lon0, "south": lat0, "east": lon1, "north": lat1},
            "encoding": "Int16 little-endian, row-major, row 0 = north edge, column 0 = west edge; "
                        "height_m = value / 10 (decimetres). Heights relative to NGF/IGN69 "
                        "(~ mean sea level; water plane at 0). No no-data values.",
            "pixelRegistration": "area: extent = outer pixel edges; pixel (r,c) centre = "
                                 "(xWest + (c+0.5)*res, nNorth - (r+0.5)*res)",
            "minHeight": float(q.min()) / 10.0, "maxHeight": float(q.max()) / 10.0,
            "landSource": src,
            "lidarSamplingMetres": {"x": round(fetch_res["res"], 4), "y": fetch_res["res_y"]},
        }

    def ortho_entry(fname, grid: Grid):
        return {
            "file": fname, "width": grid.width, "height": grid.height, "metresPerPixel": grid.res,
            "extent": grid.extent_dict(),
            "lonLatExtent": dict(zip(("west", "south", "east", "north"), grid.lonlat_bbox())),
            "encoding": "JPEG quality 85 (progressive), sRGB, row 0 = north edge; exactly the same extent as "
                        "the matching DEM (pixel edges coincide every 120 m)",
        }

    meta = {
        "name": "Goulet & Rade de Brest terrain",
        "generated": __import__("datetime").date.today().isoformat(),
        "origin": {"lat0": LAT0, "lon0": LON0},
        "frame": "local north-aligned metric frame: x = (lon - lon0) * mx (metres east), "
                 "n = (lat - lat0) * my (metres north); constant scale factors at lat0 "
                 "(the grid is therefore regular in WGS84 lon/lat as well)",
        "scale": {
            "mx": MX, "my": MY,
            "mxFormula": "111412.84*cos(lat0) - 93.5*cos(3*lat0) + 0.118*cos(5*lat0)  [m per degree lon]",
            "myFormula": "111132.92 - 559.82*cos(2*lat0) + 1.175*cos(4*lat0)  [m per degree lat]",
        },
        "verticalDatum": "NGF-IGN69 (French levelling, ~ mean sea level; at Brest MSL is ~ +0.4 m IGN69). "
                         f"Bathymetry converted from LAT with LAT = {LAT_TO_NGF} m IGN69 (Brest chart datum).",
        "layers": {
            "demFar": dem_entry("dem_far.bin", FAR, q_far,
                                "IGN LiDAR HD MNS (surface model incl. buildings/trees), sampled 5 m x 7.5 m and "
                                "max-pooled 3x2; RGE ALTI where LiDAR is masked",
                                FAR_LIDAR),
            "demNear": dem_entry("dem_near.bin", NEAR, q_near,
                                 "IGN LiDAR HD MNS (surface model incl. buildings/trees), sampled 1.33 m x 2 m and "
                                 "max-pooled 3x2; RGE ALTI where LiDAR is masked",
                                 NEAR_LIDAR),
            "orthoFar": ortho_entry("ortho_far.jpg", of),
            "orthoNear": ortho_entry("ortho_near.jpg", on),
        },
        "processing": {
            "landSea": "Water = Plan IGN v2 water fill that is not firm RGE ALTI ground (>= 1 m), plus areas outside "
                       "the RGE ALTI domain without a LiDAR-measured structure; only water 4-connected to the open "
                       "sea becomes sea. RGE ALTI flattened water surfaces (constant -2.79 m sea band, flat "
                       "estuaries) are ignored. Firm ground: LiDAR HD MNS (buildings, trees), RGE ALTI where the "
                       "LiDAR is masked (military sites: Brest naval base, Ile Longue, Lanveoc-Poulmic, ...). "
                       "Foreshore (RGE ALTI < 1 m) not mapped as water: min(LiDAR, RGE ALTI) i.e. ground only. "
                       "Outside RGE ALTI and not water (recent port polder, breakwaters, rocks): LiDAR where the "
                       "surface is measured (rough), long narrow high decks over water (bridges) excluded. "
                       "Measured submerged foreshore (RGE ALTI < 0 m) is kept where shallower than the seabed blend.",
            "removedFromLidar": "objects standing on water (moored/anchored ships, buoys, pontoons, bridge decks over "
                                "water, TIN-interpolated water surfaces) are replaced by water/seabed",
            "seaDepth": f"smooth-min(max(EMODnet depth LAT->IGN69, shoreDepth*exp(-d/{FLOOR_DECAY_M:g})), "
                        f"shoreDepth + k * d), d = distance to the nearest non-sea pixel, blend width {SMOOTH_H} m; "
                        f"shoreDepth = max({D0} m, -elevation of the adjacent non-sea pixel) and k = {K_GENTLE}..{K_STEEP} "
                        f"(gentle next to low shores, steep next to cliffs/quays >= {K_HIGH_Z} m), both smoothed "
                        f"{SHORE_SMOOTH_M:g} m along the shore; then a {SEA_SMOOTH_M:g} m gaussian over sea pixels "
                        "faded in from the shoreline. Seabed is ~-0.3 m at a dry shoreline.",
            "lidarPooling": "the LiDAR HD WMS pyramid has degree-square pixels and nearest-neighbour "
                            "resampling, so it is fetched with x step = res/3 and y step = res/2 (square in "
                            "degrees) and max-pooled 3x2 into each output pixel; the far DEM is therefore a "
                            "15 m 'skyline' surface, slightly higher than an average of the near DEM",
            "nearFarConsistency_m": cons,
            "tideNote": "LiDAR HD was flown at various tide states (water surface -2.6..-0.2 m IGN69, sometimes higher "
                        "in port basins). The water plane of the simulator is 0 m IGN69 (~ mean sea level); "
                        "foreshore above 0 m appears as land, as at mid tide.",
        },
        "sources": [
            {"name": "IGN LiDAR HD - MNS (modele numerique de surface)",
             "service": "https://data.geopf.fr/wms-r/wms", "layer": "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G",
             "nativeResolution": "0.5 m", "usedFor": "land heights (dem_far, dem_near)",
             "licence": "Licence Ouverte / Open Licence Etalab 2.0", "attribution": "IGN - LiDAR HD"},
            {"name": "IGN RGE ALTI (MNT)", "service": "https://data.geopf.fr/wms-r/wms",
             "layer": "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES", "nativeResolution": "1 m (5 m in places)",
             "usedFor": "foreshore ground, land/sea reference, filling LiDAR gaps (military sites are masked in LiDAR HD)",
             "licence": "Licence Ouverte / Open Licence Etalab 2.0", "attribution": "IGN - RGE ALTI"},
            {"name": "IGN Plan IGN v2 (cartographic rendering of BD TOPO)", "service": "https://data.geopf.fr/wms-r/wms",
             "layer": "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "nativeResolution": "rendered at 4-5 m",
             "usedFor": "sea / water classification only (not shipped)",
             "licence": "Licence Ouverte / Open Licence Etalab 2.0", "attribution": "IGN - Plan IGN"},
            {"name": "IGN orthophotographies (BD ORTHO mosaic, most recent campaign)", "service": "https://data.geopf.fr/wms-r/wms",
             "layer": "ORTHOIMAGERY.ORTHOPHOTOS", "nativeResolution": "0.2-0.5 m",
             "usedFor": "ortho_far.jpg, ortho_near.jpg",
             "licence": "Licence Ouverte / Open Licence Etalab 2.0", "attribution": "IGN - BD ORTHO"},
            {"name": "EMODnet Digital Bathymetry (DTM 2024)", "service": "https://ows.emodnet-bathymetry.eu/wcs",
             "layer": "emodnet__mean", "nativeResolution": "1/16 arc-minute (~115 m)",
             "verticalReference": "LAT (Lowest Astronomical Tide)", "usedFor": "sea floor",
             "licence": "EMODnet data policy: free and open, re-use with attribution (CC BY 4.0). "
                        "Not to be used for navigation.",
             "attribution": "EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM 2024)"},
        ],
    }
    (OUT / "terrain.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print("[meta] terrain.json written", flush=True)


if __name__ == "__main__":
    main()
