"""Place names for the map -> public/data/labels.json

Positions come from the IGN Geoplateforme geocoder (BD TOPO toponyms, Licence Ouverte
Etalab 2.0). Sea areas (Goulet, Rade, anses) have no point in BD TOPO: they are placed by
hand in the middle of the water body, like on a chart.

Run:  python3 tools/labels.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import FAR, OUT, ll_to_local  # noqa: E402
from places import _norm, geocode  # noqa: E402

# (label, query, index, must contain, class, rank)
#   class: city, town, locality, point, beach, port, landmark
#   rank : 1 always shown, 2 from a medium zoom, 3 only close up
QUERIES = [
    ("Brest", "Brest", "address", "brest", "city", 1),
    ("Plouzané", "Plouzané", "address", "plouzane", "town", 1),
    ("Locmaria-Plouzané", "Locmaria-Plouzané", "address", "locmaria", "town", 2),
    ("Plougonvelin", "Plougonvelin", "address", "plougonvelin", "town", 1),
    ("Le Conquet", "Le Conquet", "address", "conquet", "town", 2),
    ("Camaret-sur-Mer", "Camaret-sur-Mer", "address", "camaret", "town", 1),
    ("Roscanvel", "Roscanvel", "address", "roscanvel", "town", 2),
    ("Lanvéoc", "Lanvéoc", "address", "lanveoc", "town", 2),
    ("Plougastel-Daoulas", "Plougastel-Daoulas", "address", "plougastel", "town", 1),
    ("Le Relecq-Kerhuon", "Le Relecq-Kerhuon", "address", "relecq", "town", 2),
    ("Guipavas", "Guipavas", "address", "guipavas", "town", 2),
    ("Logonna-Daoulas", "Logonna-Daoulas", "address", "logonna", "town", 3),
    ("Landévennec", "Landévennec", "address", "landevennec", "town", 3),

    ("Le Dellec", "Le Dellec Plouzané", "poi", "dellec", "locality", 1),
    ("Le Minou", "Le Minou Plouzané", "poi", "minou", "locality", 2),
    ("Sainte-Anne-du-Portzic", "Sainte-Anne du Portzic", "poi", "sainte-anne", "locality", 2),
    ("Le Trez-Hir", "Trez Hir Plougonvelin", "poi", "trez", "locality", 2),
    ("Recouvrance", "Recouvrance Brest", "poi", "recouvrance", "locality", 3),
    ("Saint-Marc", "Saint-Marc Brest", "poi", "saint-marc", "locality", 3),
    ("Le Fret", "Le Fret Crozon", "poi", "fret", "locality", 3),
    ("Quélern", "Quélern Roscanvel", "poi", "quelern", "locality", 3),

    ("Pointe Saint-Mathieu", "Pointe de Saint-Mathieu", "poi", "saint-mathieu", "point", 1),
    ("Pointe du Petit Minou", "Pointe du Petit Minou", "poi", "petit minou", "point", 2),
    ("Pointe du Grand Minou", "Pointe du Grand Minou", "poi", "grand minou", "point", 3),
    ("Pointe du Diable", "Pointe du Diable Plouzané", "poi", "diable", "point", 3),
    ("Pointe du Portzic", "Pointe du Portzic", "poi", "portzic", "point", 2),
    ("Pointe des Espagnols", "Pointe des Espagnols", "poi", "espagnols", "point", 1),
    ("Pointe de Cornouaille", "Pointe de Cornouaille", "poi", "cornouaille", "point", 2),
    ("Pointe des Capucins", "Pointe des Capucins Roscanvel", "poi", "capucins", "point", 3),
    ("Pointe du Toulinguet", "Pointe du Toulinguet", "poi", "toulinguet", "point", 2),
    ("Pointe de l'Armorique", "Pointe de l'Armorique Plougastel", "poi", "armorique", "point", 3),
    ("Île Longue", "Île Longue Crozon", "poi", "ile longue", "point", 2),
    ("Plateau des Fillettes", "Plateau des Fillettes", "poi", "fillettes", "point", 3),
    ("Roche Mengant", "Mengant", "poi", "roche mengant", "point", 3),

    ("Plage du Dellec", "Plage du Dellec", "poi", "dellec", "beach", 2),
    ("Plage du Minou", "Plage du Minou", "poi", "minou", "beach", 3),
    ("Port de Sainte-Anne", "Plage de Sainte-Anne du Portzic", "poi", "sainte-anne", "port", 3),
    ("Plage du Trez-Hir", "Plage du Trez Hir", "poi", "trez", "beach", 3),
    ("Plage du Moulin Blanc", "Plage du Moulin Blanc", "poi", "moulin blanc", "beach", 3),

    ("Port du Moulin Blanc", "Port du Moulin Blanc", "poi", "moulin blanc", "port", 2),
    ("Port du Conquet", "Port du Conquet", "poi", "conquet", "port", 3),

    ("IMT Atlantique", "655 Avenue du Technopole 29280 Plouzané", "address", "655", "landmark", 1),
    ("Ifremer", "1625 Route de Sainte-Anne 29280 Plouzané", "address", "1625", "landmark", 2),
    ("Océanopolis", "Océanopolis Brest", "poi", "oceanopolis", "landmark", 2),
    ("Château de Brest", "Château de Brest", "poi", "chateau", "landmark", 3),
    ("Phare du Petit Minou", "Phare du Petit Minou", "poi", "petit minou", "landmark", 2),
    ("Fort du Portzic", "Phare du Portzic", "poi", "portzic", "landmark", 3),
    ("Phare de Saint-Mathieu", "Phare de Saint-Mathieu", "poi", "saint-mathieu", "landmark", 2),
    ("Fort de Bertheaume", "Fort de Bertheaume", "poi", "bertheaume", "landmark", 2),
    ("Fort du Dellec", "Fort du Dellec", "poi", "dellec", "landmark", 3),
    ("Fort du Mengant", "Fort du Mengant", "poi", "mengant", "landmark", 3),
    ("Fort de Cornouaille", "Fort de Cornouaille", "poi", "cornouaille", "landmark", 3),
    ("École navale", "École navale Lanvéoc", "poi", "navale", "landmark", 3),
    ("Base aéronavale", "Base navale Brest", "poi", "aeronautique", "landmark", 3),
    ("Pont de l'Iroise", "Pont de l'Iroise", "poi", "iroise", "landmark", 3),
    ("Pont Albert-Louppe", "Pont Albert Louppe", "poi", "louppe", "landmark", 3),
]

# not in the geocoder under a usable name: placed by hand on the orthophoto
MANUAL = [
    ("Port de commerce", -4.4660, 48.3825, "port", 1),
    ("Base navale", -4.5050, 48.3760, "port", 2),
    ("Port du Château", -4.4878, 48.3797, "port", 3),
    ("Port de Camaret", -4.5965, 48.2785, "port", 3),
]

# sea areas: (label, lon, lat, rank, angle in degrees counter-clockwise from east)
WATER = [
    ("Mer d'Iroise", -4.735, 48.300, 1, 0),
    ("Goulet de Brest", -4.585, 48.3415, 1, 14),
    ("Rade de Brest", -4.470, 48.335, 1, 0),
    ("Anse de Bertheaume", -4.690, 48.338, 2, 0),
    ("Anse de Camaret", -4.592, 48.286, 2, 0),
    ("Baie de Roscanvel", -4.535, 48.310, 3, 0),
    ("Anse du Fret", -4.505, 48.293, 3, 0),
    ("Anse de Poulmic", -4.448, 48.296, 3, 0),
    ("Élorn", -4.395, 48.400, 3, 20),
    ("Baie de Daoulas", -4.330, 48.340, 3, 0),
    ("Anse de Dinan", -4.610, 48.250, 3, 0),
]


def pick(query, index, must):
    data = geocode(query, index)
    lon_w, lat_s, lon_e, lat_n = FAR.lonlat_bbox()
    best = None
    for f in data.get("features", []):
        lon, lat = f["geometry"]["coordinates"]
        if not (lon_w < lon < lon_e and lat_s < lat < lat_n):
            continue
        p = f["properties"]
        names = [p.get("toponym") or "", p.get("label") or "", p.get("name") or "", p.get("city") or ""]
        names += p.get("name") if isinstance(p.get("name"), list) else []
        text = " ".join(n if isinstance(n, str) else " ".join(n) for n in names)
        if must not in _norm(text).replace("'", " "):
            continue
        if index == "address" and not must.isdigit() and p.get("type") not in (None, "municipality"):
            continue
        best = (lon, lat, text, p.get("category") or p.get("type"))
        break
    return best


def main():
    out = []
    for label, query, index, must, cls, rank in QUERIES:
        r = pick(query, index, must)
        if not r:
            print(f"  --  {label}: not found", flush=True)
            continue
        lon, lat, text, cat = r
        x, n = ll_to_local(lon, lat)
        out.append(dict(name=label, cls=cls, rank=rank, lon=round(lon, 6), lat=round(lat, 6),
                        x=round(float(x), 1), n=round(float(n), 1)))
        print(f"  ok  {label:28s} {lat:.5f} {lon:.5f}  <- {text[:60]!r} {cat}", flush=True)
    for label, lon, lat, cls, rank in MANUAL:
        x, n = ll_to_local(lon, lat)
        out.append(dict(name=label, cls=cls, rank=rank, lon=lon, lat=lat, x=round(float(x), 1), n=round(float(n), 1)))
    for label, lon, lat, rank, ang in WATER:
        x, n = ll_to_local(lon, lat)
        out.append(dict(name=label, cls="water", rank=rank, lon=lon, lat=lat, x=round(float(x), 1),
                        n=round(float(n), 1), angle=ang))
    doc = dict(source="IGN Geoplateforme geocoding (BD TOPO toponyms), Licence Ouverte Etalab 2.0; "
                      "sea areas placed by hand", frame="x metres east, n metres north (see terrain.json)",
               labels=out)
    (OUT / "labels.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(f"{len(out)} labels -> {OUT / 'labels.json'}")


if __name__ == "__main__":
    main()
