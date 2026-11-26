"""
Exemple de pipeline branché sur le simulateur Iroise.

Le simulateur (navigateur) se connecte à ce serveur WebSocket et envoie, ~10 fois
par seconde, l'image de la caméra embarquée + la vérité terrain + l'AIS. Ce script
fait tourner une boucle complète : détection -> alerte -> approche -> maintien à
distance, et renvoie au simulateur les consignes de cap/vitesse, les alertes et
les boîtes détectées (affichées en bleu dans le HUD).

Lancement :
    pip install -r bridge/requirements.txt
    python bridge/pipeline_example.py              # détecteur simulé (vérité terrain bruitée)
    python bridge/pipeline_example.py --yolo yolov8n.pt   # vrai détecteur (ultralytics)

Puis dans le simulateur, cliquer sur l'icône « lien » (ou ouvrir /?bridge=1).
"""

import argparse
import asyncio
import io
import json
import math
import random
import struct
import time

import websockets

try:
    import numpy as np
    from PIL import Image
except ImportError:  # l'image reste disponible en JPEG brut
    np = None
    Image = None


def parse_frame(buf: bytes):
    n = struct.unpack_from("<I", buf, 0)[0]
    meta = json.loads(buf[4:4 + n].decode("utf-8"))
    jpeg = buf[4 + n:]
    return meta, jpeg


def camera_yaw_deg(q):
    """Cap (0 = nord, sens horaire) de l'axe optique, depuis le quaternion three.js."""
    x, y, z, w = q
    # vecteur avant de la caméra = q * (0, 0, -1)
    fx = -(2 * (x * z + w * y))
    fz = -(1 - 2 * (x * x + y * y))
    return (math.degrees(math.atan2(fx, -fz)) + 360) % 360


class SimulatedDetector:
    """Remplace un vrai réseau : vérité terrain + bruit, ratés et petites cibles perdues."""

    def __init__(self, min_px=6, miss=0.08):
        self.min_px, self.miss = min_px, miss

    def __call__(self, meta, jpeg):
        out = []
        for g in meta["ground_truth"]:
            x0, y0, x1, y1 = g["bbox"]
            w, h = x1 - x0, y1 - y0
            if w < self.min_px or random.random() < self.miss:
                continue
            j = 0.04
            out.append({
                "bbox": [x0 + random.gauss(0, w * j), y0 + random.gauss(0, h * j), x1 + random.gauss(0, w * j), y1 + random.gauss(0, h * j)],
                "label": "bateau", "score": max(0.3, min(0.99, 0.6 + w / 400 + random.gauss(0, 0.05))),
                "track_id": g["id"],
            })
        return out


class YoloDetector:
    def __init__(self, weights):
        from ultralytics import YOLO
        self.model = YOLO(weights)

    def __call__(self, meta, jpeg):
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        res = self.model(np.asarray(img), verbose=False)[0]
        out = []
        for b, c, s in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            if self.model.names[int(c)] == "boat":
                out.append({"bbox": b, "label": "bateau", "score": s})
        return out


class Pipeline:
    """Patrouille -> détection confirmée -> alerte -> approche -> maintien."""

    def __init__(self, detector, standoff=60.0):
        self.detector = detector
        self.state = "patrouille"
        self.hits = 0
        self.target_bearing = None
        self.standoff = standoff
        self.last_alert = 0

    def step(self, meta, jpeg):
        dets = self.detector(meta, jpeg)
        msgs = [{"type": "detections", "boxes": dets}]
        own = meta["own"]
        fx = meta["intrinsics"]["fx"]
        cx = meta["intrinsics"]["cx"]
        cam_yaw = camera_yaw_deg(meta["camera"]["quaternion"])

        if not dets:
            self.hits = max(0, self.hits - 1)
            if self.state == "approche" and self.hits == 0:
                self.state = "patrouille"
                msgs.append({"type": "alert", "text": "Cible perdue", "detail": "retour en patrouille"})
                msgs.append({"type": "heading", "heading_deg": own["heading_deg"], "speed_mps": 2.0})
            return msgs

        # cible = la plus grosse boîte (la plus proche en général)
        best = max(dets, key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]))
        u = 0.5 * (best["bbox"][0] + best["bbox"][2])
        bearing = (cam_yaw + math.degrees(math.atan2(u - cx, fx))) % 360
        self.target_bearing = bearing
        self.hits = min(self.hits + 1, 10)

        # distance estimée par la hauteur apparente (hypothèse ~12 m de tirant d'air)
        h_px = max(best["bbox"][3] - best["bbox"][1], 1)
        dist = 12.0 * fx / h_px

        if self.state == "patrouille" and self.hits >= 3:
            self.state = "approche"
            if time.time() - self.last_alert > 5:
                self.last_alert = time.time()
                msgs.append({"type": "alert", "text": "Navire détecté", "detail": f"relèvement {bearing:.0f}° · ~{dist:.0f} m"})

        if self.state == "approche":
            speed = max(0.0, min(5.5, (dist - self.standoff) * 0.03))
            msgs.append({"type": "heading", "heading_deg": bearing, "speed_mps": speed})
        return msgs


async def handler(ws, pipeline):
    print("simulateur connecté", flush=True)
    n = 0
    t0 = time.time()
    async for msg in ws:
        if isinstance(msg, str):
            continue
        meta, jpeg = parse_frame(msg)
        for out in pipeline.step(meta, jpeg):
            await ws.send(json.dumps(out))
        n += 1
        if n % 50 == 0:
            print(f"{n} images · {n / (time.time() - t0):.1f} img/s · état : {pipeline.state} · {len(meta['ground_truth'])} navires visibles", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--yolo", default=None, help="poids ultralytics (ex. yolov8n.pt) au lieu du détecteur simulé")
    ap.add_argument("--standoff", type=float, default=60.0)
    args = ap.parse_args()
    det = YoloDetector(args.yolo) if args.yolo else SimulatedDetector()
    pipeline = Pipeline(det, args.standoff)
    async with websockets.serve(lambda ws: handler(ws, pipeline), args.host, args.port, max_size=32 * 1024 * 1024):
        print(f"en attente du simulateur sur ws://{args.host}:{args.port}", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
