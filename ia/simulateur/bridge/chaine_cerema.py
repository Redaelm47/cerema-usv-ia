"""
Branche la chaîne IA du projet (ia/suivi et ia/chaine) sur le simulateur.

    simulateur (image de la caméra du drone, ~10 img/s)
        -> détecteur YOLO (best4_2.pt de Guillaume par défaut, ou yolo11n.pt comme l'IMX500)
        -> suivi : ia/suivi (associateur, numéros de pistes)            contrat 1
        -> décision et experts : ia/chaine (qualité, type DINOv2, OCR, approche, garde-fous)
        -> messages du contrat 3 : alertes, décisions, état              contrat 3
    et en retour vers le simulateur : boîtes de la chaîne (en bleu), alertes, et consignes de cap et de
    vitesse quand la chaîne décide une approche. Journaux dans bridge/runs/ (ignoré par git).

Lancer depuis la racine du dépôt, avec le Python du dépôt (ultralytics, OpenCV, ONNX Runtime) :

    .venv/bin/python ia/simulateur/bridge/chaine_cerema.py
    # option : --depot ../autre-copie        pour tester la chaîne d'une autre copie du dépôt (worktree)
    # option : --station http://localhost:8000  pour alimenter aussi la page de la station sol
    # option : --detecteur yolo11n             pour le modèle COCO de la caméra IMX500

Puis ouvrir le simulateur avec /?bridge=1 (ou cliquer sur l'icône « lien »).
"""
import argparse
import asyncio
import json
import math
import struct
import subprocess
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
DEPOT = ICI.parents[2]  # ia/simulateur/bridge -> racine du dépôt


def preparer_chemins(depot: Path) -> None:
    sys.path.insert(0, str(depot / "ia"))
    try:
        import websockets  # noqa: F401
    except ImportError:
        # websockets n'est pas dans l'environnement du dépôt : on prend celui du simulateur, sans rien installer
        for sp in sorted((ICI / ".venv" / "lib").glob("python3*/site-packages")):
            sys.path.append(str(sp))


def modele_detecteur(choix: str, depot: Path) -> tuple[Path, tuple[int, ...]]:
    """Chemin des poids et classes à garder. best4_2 : une classe « boat ». yolo11n : COCO, classe 8."""
    if choix == "yolo11n":
        return depot / "ia" / "chaine" / "modeles" / "yolo11n.pt", (8,)
    if choix in ("best4_2", "best4"):
        for racine in (DEPOT, depot):
            ici = racine / "ia" / "detection" / "best4" / f"{choix}.pt"
            if ici.exists():
                return ici, (0,)
        dest = ICI / "modeles" / f"{choix}.pt"
        if not dest.exists():
            # les poids sont sur main : on les lit dans git sans toucher à la copie de travail
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = subprocess.run(["git", "-C", str(depot), "show", f"origin/main:ia/detection/best4/{choix}.pt"],
                                  check=True, capture_output=True).stdout
            dest.write_bytes(data)
        return dest, (0,)
    return Path(choix).expanduser(), (0,)


def lacet_camera_deg(q) -> float:
    """Cap (0 = nord, sens horaire) de l'axe optique, depuis le quaternion three.js (x est, y haut, z sud)."""
    x, y, z, w = q
    fx = -(2 * (x * z + w * y))
    fz = -(1 - 2 * (x * x + y * y))
    return (math.degrees(math.atan2(fx, -fz)) + 360) % 360


class EmetteurSimulateur:
    """Garde les messages du contrat 3 pour les traduire en messages du simulateur."""

    def __init__(self):
        self.nouveaux = []

    def envoyer(self, message):
        self.nouveaux.append(message)

    def fermer(self):
        pass


class Pont:
    def __init__(self, args):
        import cv2
        import numpy as np
        from chaine.chaine import Chaine
        from chaine.experts import DroneSimule, ExpertApprocheSimulee
        from chaine.experts.ocr import ExpertOCR
        from chaine.experts.qualite import FiltreQualite
        from chaine.experts.type import ExpertType
        from chaine.journal import Journal
        from chaine.messages import Emetteurs, creer_emetteur
        from chaine.reglages import Reglages
        from suivi.associateur import Associateur
        from suivi.detecteur import DetecteurYolo
        from suivi.suivi import observations

        self.cv2, self.np, self.observations = cv2, np, observations
        poids, classes = modele_detecteur(args.detecteur, args.depot)
        print(f"détecteur : {poids.name} (classes {list(classes)})", flush=True)
        self.detecteur = DetecteurYolo(poids, taille=640, classes=classes)
        self.associateur = Associateur()
        self.reglages = Reglages()
        # le drone du simulateur va au plus à 5 nœuds : le drone simulé de la chaîne avance au même pas
        self.drone = DroneSimule(vitesse_m_s=2.5)
        experts = [ExpertApprocheSimulee(self.drone, self.reglages), FiltreQualite(self.reglages),
                   ExpertType(fils=args.fils, reseau=args.reseau_type), ExpertOCR(self.reglages, fils=args.fils)]
        runs = ICI / "runs"
        runs.mkdir(exist_ok=True)
        self.journal = Journal(runs / "journal.jsonl")
        self.sortie = EmetteurSimulateur()
        emetteurs = [creer_emetteur(str(runs / "messages.jsonl")), self.sortie]
        if args.station:
            emetteurs.append(creer_emetteur(args.station.rstrip("/") + "/message"))
        self.chaine = Chaine(experts, self.reglages, self.journal, Emetteurs(emetteurs), self.drone)
        self.cible_precedente = None
        self.t = 0.0
        self.images = 0
        self.debut = time.perf_counter()
        self.premiere = True
        self.taille_image = None

    def adapter_a_l_image(self, meta):
        """Les seuils de la chaîne sont pensés pour l'image de 4056 px de l'IMX500 : on garde la même part."""
        w = meta["width"]
        fx = meta["intrinsics"]["fx"]
        self.reglages.champ_horizontal_deg = math.degrees(2 * math.atan(w / 2 / fx))
        self.reglages.seuil_ocr_px = 600.0 * w / 4056
        self.reglages.largeur_image_px = w
        print(f"image {w}x{meta['height']}, champ horizontal {self.reglages.champ_horizontal_deg:.0f}°, "
              f"seuil OCR {self.reglages.seuil_ocr_px:.0f} px", flush=True)

    def traiter(self, buf: bytes):
        n = struct.unpack_from("<I", buf, 0)[0]
        meta = json.loads(buf[4:4 + n].decode("utf-8"))
        image = self.cv2.imdecode(self.np.frombuffer(buf[4 + n:], self.np.uint8), self.cv2.IMREAD_COLOR)
        if image is None:
            return []
        if self.premiere or (meta["width"], meta["height"]) != self.taille_image:
            self.adapter_a_l_image(meta)
            self.taille_image = (meta["width"], meta["height"])
            self.premiere = False
        t = float(meta["t"])
        self.t = t
        # contrat 1 : détection + suivi, puis un pas de la chaîne
        detections = self.detecteur.detecter(image)
        obs = self.observations(t, self.associateur.mettre_a_jour(detections, t))
        t = obs["t"]  # le contrat 1 arrondit le temps : on compare avec la même valeur que les fiches
        self.t = t
        self.chaine.pas(obs, image)
        self.images += 1
        if self.images % 10 == 0:
            self.ecrire_apercu(image, t)
        sortie = [self.boites(t)]
        sortie += self.traduire_messages()
        sortie += self.piloter(meta, t, image.shape[1])
        if self.images % 50 == 0:
            ips = self.images / (time.perf_counter() - self.debut)
            print(f"{self.images} images · {ips:.1f} img/s · {len(obs['pistes'])} pistes · mode {self.drone.mode}", flush=True)
        return sortie

    def ecrire_apercu(self, image, t):
        """runs/apercu.jpg : la dernière image reçue, avec ce que voit la chaîne (pour contrôle)."""
        cv2 = self.cv2
        vue = image.copy()
        for f in self.chaine.fiches.values():
            if f.suivi.derniere_vue != t:
                continue
            x, y, w, h = (int(v) for v in f.suivi.boite)
            cv2.rectangle(vue, (x, y), (x + w, y + h), (255, 200, 120), 2)
            txt = f"#{f.id_piste} {'/'.join(f.experts.types)} {f.experts.immatriculation or ''}"
            cv2.putText(vue, txt, (x, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 120), 1, cv2.LINE_AA)
        cv2.imwrite(str(ICI / "runs" / "apercu.jpg"), vue, [cv2.IMWRITE_JPEG_QUALITY, 85])

    def boites(self, t):
        """Ce que voit la chaîne : pistes confirmées ou non, avec le type et l'immatriculation dès qu'ils sont connus."""
        out = []
        for f in self.chaine.fiches.values():
            if f.suivi.derniere_vue != t:
                continue
            x, y, w, h = f.suivi.boite
            etiquette = f"#{f.id_piste}"
            if f.experts.types:
                etiquette += " " + "/".join(f.experts.types)
            if f.experts.immatriculation:
                etiquette += " " + f.experts.immatriculation
            etat = f.decision.etat.value if hasattr(f.decision.etat, "value") else str(f.decision.etat)
            if etat not in ("nouvelle", "confirmee"):
                etiquette += f" · {etat.replace('_', ' ')}"
            out.append({"bbox": [x, y, x + w, y + h], "label": etiquette, "score": f.suivi.confiance})
        return {"type": "detections", "boxes": out}

    def traduire_messages(self):
        out = []
        for m in self.sortie.nouveaux:
            if m.get("genre") == "alerte":
                types = ", ".join(m.get("types") or []) or "type inconnu"
                if m.get("complete"):
                    texte = f"Alerte complète · {m.get('immatriculation')}"
                else:
                    texte = "Alerte partielle" + (f" · {m['immatriculation']} ?" if m.get("immatriculation") else "")
                print(f"ALERTE piste {m['id_piste']} : {texte} ({types}) : {m.get('raison')}", flush=True)
                out.append({"type": "alert", "text": texte, "detail": f"piste {m['id_piste']} · {types} · {m.get('raison')}", "duration_ms": 6000})
            elif m.get("genre") == "decision" and m.get("action") == "approche":
                out.append({"type": "alert", "text": f"Chaîne IA : approche du navire #{m['id_piste']}", "detail": m.get("raison", ""), "duration_ms": 4000})
        self.sortie.nouveaux.clear()
        return out

    def piloter(self, meta, t, largeur):
        """L'expert approche donne une cible : le drone du simulateur va vers elle, au relèvement de sa boîte."""
        cible = self.drone.cible
        own = meta["own"]
        if cible is None:
            if self.cible_precedente is not None:
                self.cible_precedente = None
                # fin d'approche : reprise de la patrouille au cap actuel
                return [{"type": "heading", "heading_deg": own["heading_deg"], "speed_mps": 1.0}]
            return []
        self.cible_precedente = cible
        fiche = self.chaine.fiches.get(cible)
        if fiche is None or fiche.suivi.derniere_vue != t:
            return []
        x, _, w, _ = fiche.suivi.boite
        fx = meta["intrinsics"]["fx"]
        releve = (lacet_camera_deg(meta["camera"]["quaternion"]) + math.degrees(math.atan((x + w / 2 - largeur / 2) / fx))) % 360
        arrive = self.drone.distance_m is not None and self.drone.distance_m <= self.drone.distance_arret_m + 0.5
        return [{"type": "heading", "heading_deg": releve, "speed_mps": 0.0 if arrive else 2.5}]

    def cloturer(self):
        self.chaine.cloturer(self.t)
        sortie = self.traduire_messages()
        self.journal.fermer()
        return sortie


async def servir(args):
    import websockets
    pont = Pont(args)

    async def connexion(ws):
        print("simulateur connecté", flush=True)
        derniere = {"m": None}
        nouvelle = asyncio.Event()
        fini = asyncio.Event()

        async def lire():
            try:
                async for m in ws:
                    if not isinstance(m, str):
                        derniere["m"] = m  # on ne garde que la plus récente : la chaîne ne prend jamais de retard
                        nouvelle.set()
            finally:
                fini.set()
                nouvelle.set()

        async def traiter():
            boucle = asyncio.get_running_loop()
            while not fini.is_set():
                await nouvelle.wait()
                nouvelle.clear()
                m, derniere["m"] = derniere["m"], None
                if m is None:
                    continue
                for o in await boucle.run_in_executor(None, pont.traiter, m):
                    try:
                        await ws.send(json.dumps(o, ensure_ascii=False))
                    except Exception:
                        return

        await asyncio.gather(lire(), traiter())
        print("simulateur déconnecté", flush=True)

    async with websockets.serve(connexion, args.host, args.port, max_size=64 * 1024 * 1024):
        print(f"chaîne IA prête, en attente du simulateur sur ws://{args.host}:{args.port}", flush=True)
        try:
            await asyncio.Future()
        finally:
            pont.cloturer()


def main():
    ap = argparse.ArgumentParser(description="Chaîne IA Cerema branchée sur le simulateur")
    ap.add_argument("--depot", type=Path, default=DEPOT,
                    help="copie du dépôt qui contient ia/chaine et ia/suivi (par défaut, celle-ci)")
    ap.add_argument("--detecteur", default="best4_2", help="best4_2 (défaut), best4, yolo11n, ou un chemin .pt")
    ap.add_argument("--reseau-type", default="dinov2", choices=["dinov2", "dinov3"])
    ap.add_argument("--fils", type=int, default=None, help="fils d'ONNX Runtime")
    ap.add_argument("--station", help="adresse de la station sol, par exemple http://localhost:8000")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    args.depot = args.depot.expanduser().resolve()
    if not (args.depot / "ia" / "chaine").is_dir():
        sys.exit(f"ia/chaine introuvable dans {args.depot} : donner avec --depot une copie du dépôt à jour de main")
    preparer_chemins(args.depot)
    try:
        asyncio.run(servir(args))
    except KeyboardInterrupt:
        print("\narrêt", flush=True)


if __name__ == "__main__":
    main()
