"""Landmarks and shipping lanes -> public/data/places.json

Landmarks: IGN Geoplateforme geocoding (POI / address index, BD TOPO toponyms); harbour
entrances are taken at the light-structure heads drawn on Plan IGN and checked on the
orthophoto / DEM. Shipping lanes: least-cost path through the deep water of dem_far
(prefers depth, keeps clear of the shore), simplified with a depth-aware Douglas-Peucker;
every waypoint (and every 20 m along each leg) is checked against the DEMs.

Run after tools/build.py:  python3 tools/places.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import requests
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import CACHE, FAR, LAT0, LON0, MX, MY, NEAR, OUT, ll_to_local, local_to_ll  # noqa: E402

GEOCODE_URL = "https://data.geopf.fr/geocodage/search"
UA = "brest-maritime-sim-dataprep/0.1 (python-requests)"
LAT_TO_NGF = -3.64
MIN_DEPTH = 15.0        # m below the water plane (IGN69 0) required at every waypoint
PLAN_DEPTH = 18.0       # the path search keeps to water at least this deep (margin)
LOS_DEPTH = 22.0        # straightened legs keep to water at least this deep ...
LOS_CLEAR = 300.0       # ... and at least this far from the shore (relaxed near the harbours)

# (id, name, query, index, accept-substring in toponym/label, kind, note)
LANDMARKS = [
    ("phare_petit_minou", "Phare du Petit Minou", "Phare du Petit Minou", "poi", "Petit Minou", "lighthouse", None),
    ("phare_saint_mathieu", "Phare de la Pointe Saint-Mathieu", "Phare de Saint-Mathieu", "poi", "Saint-Mathieu",
     "lighthouse", None),
    ("pointe_des_espagnols", "Pointe des Espagnols", "Pointe des Espagnols", "poi", "Pointe des Espagnols", "cape",
     None),
    ("fort_du_mengant", "Fort du Mengant", "Fort du Mengant", "poi", "Mengant", "fort", None),
    ("roche_mengant", "Roche Mengant (reef, beacon)", "Mengant", "poi", "Roche Mengant", "reef", None),
    ("pointe_du_portzic", "Pointe du Portzic", "Pointe du Portzic", "poi", "Portzic", "cape", None),
    ("imt_atlantique", "IMT Atlantique campus (Technopole Brest-Iroise, Plouzane)",
     "655 Avenue du Technopole 29280 Plouzane", "address", "655", "campus",
     "655 avenue du Technopole, Plouzane (address point of the campus)"),
    ("camaret", "Camaret-sur-Mer", "Camaret-sur-Mer", "poi", "Camaret", "town", "village / harbour"),
    ("roscanvel", "Roscanvel", "Roscanvel", "poi", "Roscanvel", "town", "village"),
    ("lanveoc", "Lanveoc", "Lanveoc", "poi", "Lanv", "town", "village"),
    ("plateau_des_fillettes", "Plateau des Fillettes (shoal)", "Plateau des Fillettes", "poi", "Fillettes", "shoal",
     None),
]

# Harbour entrances: positions of the light structures at the heads of the jetties (Plan IGN,
# checked against the orthophoto and the DEM, see preview.png).
HARBOUR = [
    ("brest_commercial_port_approach", "Brest commercial port approach (east of the entrance)",
     -4.47329, 48.37944, "approach",
     "turning point ~150 m east-north-east of the entrance gap, clear of the Jetee Sud NE head"),
    ("brest_commercial_port_entrance", "Brest commercial port entrance (between Jetee Sud NE head and Quai de l'Est)",
     -4.47508, 48.37881, "entrance",
     "midpoint of the ~130 m gap between the NE head of the L-shaped Jetee Sud (-4.47467, 48.37828) "
     "and the head of the Quai de l'Est (-4.47550, 48.37934)"),
    ("brest_naval_outer_pass", "Brest naval port outer pass (between naval breakwater E head and Jetee Sud S head)",
     -4.48883, 48.36888, "entrance",
     "midpoint of the ~300 m pass between the east head of the naval-port breakwater (-4.49083, 48.36846) "
     "and the south head of the Jetee Sud (-4.48683, 48.36931)"),
    ("brest_naval_base_entrance_penfeld", "Brest naval base entrance (Penfeld river mouth)",
     -4.49457, 48.37840, "entrance", "mouth of the Penfeld between the naval quays and the Chateau de Brest"),
]

# Lanes: start in the open Iroise, end at the last deep-water point off the first harbour
# target; the harbour targets follow as "harbourApproach" legs (port water, may be shallower
# in the DEM because the 115 m bathymetry does not resolve dredged basins).
LANES = [
    ("iroise_west_to_commercial_port",
     "Iroise (off Saint-Mathieu) - Goulet - Rade - Brest commercial port",
     (-4.755, 48.305), ["brest_commercial_port_approach", "brest_commercial_port_entrance"]),
    ("iroise_west_to_naval_base",
     "Iroise (off Saint-Mathieu) - Goulet - Rade - Brest naval base (Penfeld)",
     (-4.755, 48.305), ["brest_naval_outer_pass", "brest_naval_base_entrance_penfeld"]),
    ("iroise_southwest_to_commercial_port",
     "Iroise south-west (Raz de Sein / Toulinguet approach) - Goulet - Brest commercial port",
     (-4.715, 48.262), ["brest_commercial_port_approach", "brest_commercial_port_entrance"]),
]

# Charted dangers that the 115 m bathymetry does not resolve: kept clear of by the lanes
# (radius in m around the IGN toponym point; the lanes then keep LOS_CLEAR from that disc).
HAZARDS = [("roche_mengant", 150.0), ("plateau_des_fillettes", 250.0)]

_session = requests.Session()
_session.headers["User-Agent"] = UA


def _slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def geocode(query, index):
    dest = CACHE / "geocode" / f"{index}_{_slug(query)}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    params = {"q": query, "index": index, "limit": 8, "lat": LAT0, "lon": LON0}
    for attempt in range(5):
        try:
            r = _session.get(GEOCODE_URL, params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(data))
                time.sleep(0.5)
                return data
        except requests.RequestException:
            pass
        time.sleep(2 * 2 ** attempt)
    raise RuntimeError(f"geocoding failed for {query!r}")


# ----------------------------------------------------------------------------- DEM access
class Dem:
    def __init__(self):
        self.far = np.fromfile(OUT / "dem_far.bin", "<i2").reshape(FAR.height, FAR.width) / 10.0
        self.near = np.fromfile(OUT / "dem_near.bin", "<i2").reshape(NEAR.height, NEAR.width) / 10.0

    def z(self, x, n):
        """Elevation (m IGN69) at local coordinates; near DEM where available."""
        x = np.atleast_1d(np.asarray(x, float))
        n = np.atleast_1d(np.asarray(n, float))
        r, c = FAR.local_to_pixel(x, n)
        out = ndimage.map_coordinates(self.far, [r, c], order=1, mode="nearest")
        inside = (x > NEAR.xWest + 8) & (x < NEAR.xEast - 8) & (n > NEAR.nSouth + 8) & (n < NEAR.nNorth - 8)
        if inside.any():
            r, c = NEAR.local_to_pixel(x[inside], n[inside])
            out[inside] = ndimage.map_coordinates(self.near, [r, c], order=1, mode="nearest")
        return out

    def min_depth_along(self, p, q, step=20.0):
        L = float(np.hypot(q[0] - p[0], q[1] - p[1]))
        k = max(2, int(np.ceil(L / step)) + 1)
        t = np.linspace(0, 1, k)
        return float((-self.z(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))).min())


# ----------------------------------------------------------------------------- routing
def cost_grid(dem: Dem, hazards, f=3):
    """Coarse (f x 15 m) routing grid. Depth = shallowest of the block (conservative). Charted
    hazards too small for the 115 m bathymetry (reefs) are burnt in as obstacles."""
    z = dem.far
    h, w = (z.shape[0] // f) * f, (z.shape[1] // f) * f
    zc = z[:h, :w].reshape(h // f, f, w // f, f).max(axis=(1, 3))
    depth = -zc
    res = FAR.res * f
    g = FAR.with_res(res, "coarse")
    xs, ns = g.centers()
    xs = xs[:depth.shape[1]]
    ns = ns[:depth.shape[0]]
    for hx, hn, rad in hazards:
        depth[(xs[None, :] - hx) ** 2 + (ns[:, None] - hn) ** 2 <= rad * rad] = 0.0
    land = depth <= 0.5
    dland = ndimage.distance_transform_edt(~land) * res
    ok = depth >= PLAN_DEPTH
    # cost per metre: prefer deep water and stay a few hundred metres off the shore
    c = 1.0 + 1.0 * np.exp(-(depth - PLAN_DEPTH) / 5.0) + 1.0 * np.exp(-dland / 250.0)
    c[~ok] = np.inf
    return c, res, f, depth, dland


def string_pull(path, depth, dland):
    """Replace the 8-connected grid path by straight legs (any-angle), keeping each leg in water at
    least as deep / as far from the shore as LOS_DEPTH / LOS_CLEAR (or as the grid path itself where
    that is less, e.g. close to the harbour)."""
    P = np.asarray(path, float)
    pd = depth[tuple(np.asarray(path).T)]
    pl = dland[tuple(np.asarray(path).T)]

    def ok(i, j):
        k = max(2, int(np.ceil(np.hypot(*(P[j] - P[i])) * 2)) + 1)
        t = np.linspace(0, 1, k)[:, None]
        q = np.rint(P[i] + t * (P[j] - P[i])).astype(int)
        d = depth[q[:, 0], q[:, 1]]
        lnd = dland[q[:, 0], q[:, 1]]
        return d.min() >= min(LOS_DEPTH, pd[i:j + 1].min()) and lnd.min() >= min(LOS_CLEAR, pl[i:j + 1].min())

    out = [0]
    i = 0
    while i < len(P) - 1:
        j = i + 1
        while j + 1 < len(P) and ok(i, j + 1):
            j += 1
        out.append(j)
        i = j
    return out


def route(c, res, start_rc, goal_rc):
    h, w = c.shape
    idx = np.arange(h * w).reshape(h, w)
    rows, cols, vals = [], [], []
    for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:   # 8-connectivity, each edge once (dr >= 0)
        a = idx[0:h - dr, max(0, -dc):w - max(0, dc)]
        b = idx[dr:h, max(0, dc):w - max(0, -dc)]
        ca = c.ravel()[a.ravel()]
        cb = c.ravel()[b.ravel()]
        wgt = 0.5 * (ca + cb) * res * np.hypot(dr, dc)
        good = np.isfinite(wgt)
        rows += [a.ravel()[good], b.ravel()[good]]
        cols += [b.ravel()[good], a.ravel()[good]]
        vals += [wgt[good], wgt[good]]
    G = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(h * w, h * w)).tocsr()
    s = idx[start_rc]
    g = idx[goal_rc]
    dist, pred = dijkstra(G, indices=s, return_predecessors=True)
    if not np.isfinite(dist[g]):
        raise RuntimeError("no deep-water route found")
    path = [g]
    while path[-1] != s:
        path.append(pred[path[-1]])
    path = path[::-1]
    return [divmod(int(p), w) for p in path]


def nearest_ok(c, rc, component=None):
    """Nearest routable cell to rc (optionally restricted to one connected component)."""
    ok = np.isfinite(c) if component is None else component
    if ok[rc]:
        return rc
    _, inds = ndimage.distance_transform_edt(~ok, return_indices=True)
    return int(inds[0][rc]), int(inds[1][rc])


def simplify(pts, dem: Dem, tol=150.0):
    """Douglas-Peucker that also refuses legs crossing water shallower than MIN_DEPTH + 1 m."""
    pts = np.asarray(pts, float)
    keep = {0, len(pts) - 1}

    def rec(i, j):
        if j <= i + 1:
            return
        p, q = pts[i], pts[j]
        d = q - p
        L = np.hypot(*d) or 1.0
        seg = pts[i + 1:j]
        dev = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / L
        k = int(np.argmax(dev)) + i + 1
        if dev.max() > tol or dem.min_depth_along(p, q) < MIN_DEPTH + 1.0:
            keep.add(k)
            rec(i, k)
            rec(k, j)

    rec(0, len(pts) - 1)
    return pts[sorted(keep)]


def polish(wps, dem: Dem, max_leg=1500.0):
    """Remove small zig-zags: drop a waypoint when the direct leg between its neighbours is short
    and stays in water at least as deep as the two legs it replaces (and > MIN_DEPTH + 1 m)."""
    wps = [tuple(map(float, w)) for w in wps]
    changed = True
    while changed and len(wps) > 2:
        changed = False
        for i in range(1, len(wps) - 1):
            a, b, c = wps[i - 1], wps[i], wps[i + 1]
            if np.hypot(c[0] - a[0], c[1] - a[1]) > max_leg:
                continue
            direct = dem.min_depth_along(a, c)
            if direct >= MIN_DEPTH + 1.0 and direct >= min(dem.min_depth_along(a, b), dem.min_depth_along(b, c)) - 0.5:
                del wps[i]
                changed = True
                break
    return wps


def main():
    dem = Dem()
    places = []
    for pid, name, q, idx, accept, kind, note in LANDMARKS:
        data = geocode(q, idx)
        feats = [f for f in data.get("features", [])
                 if _norm(accept) in _norm(f["properties"].get("toponym") or f["properties"].get("label")
                                           or f["properties"].get("name"))]
        if not feats:
            raise RuntimeError(f"no geocoding match for {name}")
        f = feats[0]
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        x, n = ll_to_local(lon, lat)
        entry = dict(id=pid, name=name, kind=kind, lat=round(lat, 6), lon=round(lon, 6),
                     x=round(float(x), 1), n=round(float(n), 1),
                     groundElevation=round(float(dem.z(x, n)[0]), 1),
                     source=f"IGN geocoding ({idx}): {p.get('toponym') or p.get('label')}")
        if note:
            entry["note"] = note
        places.append(entry)
    for pid, name, lon, lat, kind, note in HARBOUR:
        x, n = ll_to_local(lon, lat)
        places.append(dict(id=pid, name=name, kind=kind, lat=lat, lon=lon, x=round(float(x), 1),
                           n=round(float(n), 1), depth=round(float(-dem.z(x, n)[0]), 1),
                           source="Plan IGN v2 light structures / orthophoto", note=note))
    by_id = {p["id"]: p for p in places}

    hazards = [(by_id[h]["x"], by_id[h]["n"], r) for h, r in HAZARDS]
    c, res, f, depth_c, dland_c = cost_grid(dem, hazards)
    coarse = FAR.with_res(res, "coarse")

    def to_rc(x, n):
        r, cc = coarse.local_to_pixel(x, n)
        return int(round(float(r))), int(round(float(cc)))

    def to_xn(rc):
        xs, ns = coarse.centers()
        return float(xs[rc[1]]), float(ns[rc[0]])

    lanes = []
    for lid, name, (slon, slat), targets in LANES:
        sx, sn = ll_to_local(slon, slat)
        tgt = by_id[targets[0]]
        s_rc = nearest_ok(c, to_rc(sx, sn))
        lab, _ = ndimage.label(np.isfinite(c), structure=np.ones((3, 3)))
        g_rc = nearest_ok(c, to_rc(tgt["x"], tgt["n"]), component=lab == lab[s_rc])
        path = route(c, res, s_rc, g_rc)
        pts = [to_xn(rc) for rc in path]
        pts[0] = (float(sx), float(sn)) if -dem.z(sx, sn)[0] >= MIN_DEPTH else pts[0]
        keep = string_pull(path, depth_c, dland_c)
        wps = [pts[keep[0]]]
        for a, b in zip(keep[:-1], keep[1:]):
            if dem.min_depth_along(pts[a], pts[b]) >= MIN_DEPTH + 1.0:
                wps.append(pts[b])
            else:   # full-resolution DEM disagrees with the coarse grid: refine this leg
                wps.extend([tuple(q) for q in simplify(pts[a:b + 1], dem)[1:]])
        wps = polish(wps, dem)
        out = []
        for (x, n) in wps:
            depth = float(-dem.z(x, n)[0])
            lon, lat = local_to_ll(x, n)
            out.append(dict(x=round(x, 1), n=round(n, 1), lat=round(float(lat), 6), lon=round(float(lon), 6),
                            depth=round(depth, 1), depthBelowChartDatum=round(depth + LAT_TO_NGF, 1)))
        legs_min = [dem.min_depth_along((a["x"], a["n"]), (b["x"], b["n"])) for a, b in zip(out[:-1], out[1:])]
        assert all(w["depth"] > MIN_DEPTH for w in out), (lid, [w["depth"] for w in out])
        length = float(sum(np.hypot(b["x"] - a["x"], b["n"] - a["n"]) for a, b in zip(out[:-1], out[1:])))
        approach = [dict(id=by_id[t]["id"], x=by_id[t]["x"], n=by_id[t]["n"], lat=by_id[t]["lat"],
                         lon=by_id[t]["lon"], depth=by_id[t]["depth"]) for t in targets]
        chain = [(out[-1]["x"], out[-1]["n"])] + [(a["x"], a["n"]) for a in approach]
        app_min = min(dem.min_depth_along(a, b) for a, b in zip(chain[:-1], chain[1:]))
        lanes.append(dict(id=lid, name=name, waypoints=out, lengthMetres=round(length),
                          minDepthAlongLegs=round(min(legs_min), 1), harbourApproach=approach,
                          harbourApproachMinDepth=round(app_min, 1),
                          note="all waypoints and legs are in > 15 m of water in the DEM (below the 0 m IGN69 "
                               "water plane); the harbourApproach legs continue from the last waypoint into port "
                               "water whose DEM depth is unreliable (dredged basins not resolved by the 115 m "
                               "bathymetry)"))
        print(f"[lane] {lid}: {len(out)} waypoints, {length / 1000:.1f} km, min waypoint depth "
              f"{min(w['depth'] for w in out):.1f} m, min along legs {min(legs_min):.1f} m, "
              f"harbour approach min depth {app_min:.1f} m")

    doc = dict(
        origin=dict(lat0=LAT0, lon0=LON0), scale=dict(mx=MX, my=MY),
        frame="x = (lon - lon0) * mx metres east, n = (lat - lat0) * my metres north",
        depthConvention="depth = metres below the 0 m IGN69 water plane in dem_*.bin; depthBelowChartDatum = "
                        f"depth {LAT_TO_NGF:+} m (Brest chart datum ~ LAT is 3.64 m below IGN69)",
        places=places, lanes=lanes,
        sources=["IGN Geoplateforme geocoding (BD TOPO toponyms), Licence Ouverte Etalab 2.0",
                 "lanes computed on dem_far/dem_near (EMODnet bathymetry DTM 2024 + IGN); illustrative, "
                 "NOT for navigation"],
    )
    (OUT / "places.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    for p in places:
        extra = f"depth {p['depth']} m" if "depth" in p else f"ground {p['groundElevation']} m"
        print(f"  {p['id']:36s} x={p['x']:9.1f} n={p['n']:9.1f}  {extra}")


if __name__ == "__main__":
    main()
