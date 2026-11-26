"""
Branche la chaîne IA du projet (ia/suivi et ia/chaine) sur le simulateur.

    simulateur (image de la caméra du drone, ~10 img/s)
        -> suivi : ia/suivi, le même que sur le Pi : détecteur (best4_2 de Guillaume par défaut, détection sûre à
           55 %), associateur ByteTrack, numéros de pistes                                     contrat 1
        -> confirmation : 5 détections sûres d'affilée avant de lancer un expert (règle de Guillaume)
        -> décision et experts : ia/chaine (qualité, type DINOv2, OCR, approche, garde-fous)
        -> messages du contrat 3 : alertes, décisions, état              contrat 3
    et en retour vers le simulateur : boîtes de la chaîne (en bleu), alertes, et consignes de cap et de
    vitesse quand la chaîne décide une approche. Journaux dans bridge/runs/ (ignoré par git).

Lancer depuis la racine du dépôt, avec le Python du dépôt (ultralytics, OpenCV, ONNX Runtime) :

    .venv/bin/python ia/simulateur/bridge/chaine_cerema.py
    # option : --depot ../autre-copie        pour tester la chaîne d'une autre copie du dépôt (worktree)
    # option : --station http://localhost:8000  pour alimenter aussi la page de la station sol
    # option : --detecteur yolo11n             pour le modèle COCO qui tourne aujourd'hui sur l'IMX500
    # option : --appareil cpu                  détecteur sur le processeur (par défaut : la carte graphique si possible)

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


def modele_detecteur(choix: str, depot: Path) -> str | Path:
    """Modèle à charger : un nom de ia/suivi/detecteur.py (best4_2, best4, yolo11n) ou un fichier .pt.

    Les poids de best4 et best4_2 sont dans ia/detection/best4 ; s'ils manquent dans la copie de travail, on les lit
    dans git (origin/main) sans toucher à la copie.
    """
    from suivi.detecteur import PROFILS
    if choix not in PROFILS:
        return Path(choix).expanduser()
    if PROFILS[choix].poids.exists():
        return choix
    dest = ICI / "modeles" / f"{choix}.pt"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["git", "-C", str(depot), "show", f"origin/main:ia/detection/best4/{choix}.pt"],
                              check=True, capture_output=True).stdout
        dest.write_bytes(data)
    return dest


def lacet_camera_deg(q) -> float:
    """Cap (0 = nord, sens horaire) de l'axe optique, depuis le quaternion three.js (x est, y haut, z sud)."""
    x, y, z, w = q
    fx = -(2 * (x * z + w * y))
    fz = -(1 - 2 * (x * x + y * y))
    return (math.degrees(math.atan2(fx, -fz)) + 360) % 360


def iou(a, b) -> float:
    """Recouvrement de deux boîtes [x0, y0, x1, y1]."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def classe_drone_simulateur(DroneSimule):
    """Le drone de la chaîne, branché sur le simulateur.

    Même interface que DroneSimule (c'est lui que l'expert approche commande), mais la distance au navire
    approché est mesurée dans le simulateur, comme le ferait un AIS ou un télémètre, au lieu d'être déduite
    d'une longueur supposée. La position et le cap du drone sont ceux du simulateur.
    """

    class DroneSimulateur(DroneSimule):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.distance_mesuree_m = None
            self.position_m = None
            self.cap_deg = None
            self.mesurer = None          # numéro de piste -> distance réelle en mètres (donné par le pont)
            self.distance_min_m = 30.0

        def approcher(self, id_piste, distance_m, distance_arret_m):
            d = self.mesurer(id_piste) if self.mesurer else None
            if d:
                # la distance d'arrêt garde le même rapport à la distance, mais sur la distance mesurée
                if distance_arret_m > self.distance_min_m:
                    distance_arret_m = max(distance_arret_m * d / max(distance_m, 1e-6), self.distance_min_m)
                distance_m = d
            super().approcher(id_piste, distance_m, distance_arret_m)

        def avancer(self, t):
            super().avancer(t)
            if self.cible is not None and self.distance_mesuree_m is not None:
                self.distance_m = max(self.distance_mesuree_m, 0.1)

        def contexte(self, t):
            c = super().contexte(t)
            c.position_m, c.cap_deg = self.position_m, self.cap_deg
            c.distance_navire_m = self.distance_mesuree_m if self.cible is not None else None
            return c

    return DroneSimulateur


class EmetteurSimulateur:
    """Garde les messages du contrat 3 pour les traduire en messages du simulateur."""

    def __init__(self):
        self.nouveaux = []
        self.tous = []

    def envoyer(self, message):
        self.nouveaux.append(message)
        self.tous.append(message)

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
        from suivi.detecteur import DetecteurYolo
        from suivi.suivi import Suivi

        self.args = args
        self.cv2, self.np = cv2, np
        self.Chaine, self.DroneSimule, self.ExpertApprocheSimulee = Chaine, DroneSimule, ExpertApprocheSimulee
        self.Journal, self.Emetteurs, self.creer_emetteur, self.Suivi = Journal, Emetteurs, creer_emetteur, Suivi
        # le suivi du Pi, image par image : détecteur, détection sûre selon le modèle, associateur ByteTrack
        appareil = {} if args.appareil == "auto" else {"appareil": args.appareil}
        self.detecteur = DetecteurYolo(modele_detecteur(args.detecteur, args.depot), taille=640, **appareil)
        self.nom_detecteur = self.detecteur.nom
        self.appareil = getattr(self.detecteur, "appareil", "cpu")
        self.reglages = Reglages()
        self.reglages.confiance_confirmation = Suivi(None, self.detecteur).confiance_confirmation
        print(f"détecteur : {self.detecteur.nom} sur {self.appareil} (classes {self.detecteur.classes}), "
              f"détection sûre à {self.detecteur.confiance:.0%}, experts après {self.reglages.images_confirmation} détections sûres "
              f"d'affilée", flush=True)
        # experts chargés une fois (réseaux) ; l'approche dépend du drone, recréée à chaque épisode
        self.experts_fixes = [FiltreQualite(self.reglages), ExpertType(fils=args.fils, reseau=args.reseau_type),
                              ExpertOCR(self.reglages, fils=args.fils)]
        self.dossier = Path(args.campagne) / "journaux" if args.campagne else ICI / "runs"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.derniere_meta = {}
        self.premiere = True
        self.taille_image = None
        self.mesures = None
        self.journal = None
        self.nouvel_episode()

    def nouvel_episode(self, numero: int | None = None) -> None:
        """Chaîne remise à zéro : suivi, fiches, drone, journal (un épisode de campagne, ou la session entière)."""
        if self.journal is not None:
            self.journal.fermer()
            self.emetteurs.fermer()
        self.suivi = self.Suivi(None, self.detecteur)
        # le drone du simulateur va au plus à 5 nœuds ; sa distance au navire approché est mesurée
        self.drone = classe_drone_simulateur(self.DroneSimule)(vitesse_m_s=2.5)
        self.drone.mesurer = self.distance_piste
        self.drone.distance_min_m = self.reglages.distance_min_m
        suffixe = "" if numero is None else f"_{numero:04d}"
        self.journal = self.Journal(self.dossier / f"journal{suffixe}.jsonl")
        self.sortie = EmetteurSimulateur()
        emetteurs = [self.creer_emetteur(str(self.dossier / f"messages{suffixe}.jsonl")), self.sortie]
        if self.args.station:
            emetteurs.append(self.creer_emetteur(self.args.station.rstrip("/") + "/message"))
        self.emetteurs = self.Emetteurs(emetteurs)
        experts = [self.ExpertApprocheSimulee(self.drone, self.reglages)] + self.experts_fixes
        self.chaine = self.Chaine(experts, self.reglages, self.journal, self.emetteurs, self.drone)
        self.cible_precedente = None
        self.t = 0.0
        self.images = 0
        self.debut = time.perf_counter()

    def fin_episode(self) -> dict:
        """Clôt l'épisode (alertes partielles des navires en cours) et rend ses résultats."""
        self.chaine.cloturer(self.t)
        self.traduire_messages()
        resultat = self.mesures.resumer(self.sortie.tous, list(self.journal.lignes), self.t)
        self.mesures = None
        return resultat

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
        own = meta.get("own", {})
        if "x" in own:
            self.drone.position_m = (own["x"], -own["z"])  # est, nord
        self.drone.cap_deg = own.get("heading_deg")
        self.derniere_meta = meta
        self.drone.distance_mesuree_m = self.distance_piste(self.drone.cible)
        # contrat 1 : détection + suivi, puis un pas de la chaîne
        obs = self.suivi.pas(t, image)
        t = obs["t"]  # le contrat 1 arrondit le temps : on compare avec la même valeur que les fiches
        self.t = t
        self.chaine.pas(obs, image)
        self.images += 1
        if self.mesures is not None:
            self.mesures.observer(meta, t, self.chaine)
        elif self.images % 10 == 0:
            self.ecrire_apercu(image, t)
        sortie = [self.boites(t)]
        sortie += self.traduire_messages()
        sortie += self.piloter(meta, t, image.shape[1])
        if self.images % 50 == 0:
            ips = self.images / (time.perf_counter() - self.debut)
            if self.mesures is None:
                print(f"{self.images} images · {ips:.1f} img/s · {len(obs['pistes'])} pistes · mode {self.drone.mode}", flush=True)
        return sortie

    def distance_piste(self, id_piste):
        """Distance réelle au navire d'une piste : sa boîte rapprochée de la vérité terrain du simulateur."""
        fiche = self.chaine.fiches.get(id_piste) if id_piste is not None else None
        if fiche is None:
            return None
        meta = self.derniere_meta
        x, y, w, h = fiche.suivi.boite
        boite = [x, y, x + w, y + h]
        meilleur, distance = 0.2, None
        for v in meta.get("ground_truth", []):
            r = iou(boite, v["bbox"])
            if r > meilleur:
                meilleur, distance = r, v.get("distance")
        return distance

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
        cv2.imwrite(str(self.dossier / "apercu.jpg"), vue, [cv2.IMWRITE_JPEG_QUALITY, 85])

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
                # fin d'approche : le drone reprend sa route (ou garde son cap s'il n'en a pas)
                print("fin d'approche : reprise de la route", flush=True)
                return [{"type": "mission", "speed_mps": 1.0}]
            return []
        self.cible_precedente = cible
        fiche = self.chaine.fiches.get(cible)
        if fiche is None or fiche.suivi.derniere_vue != t:
            return []
        x, _, w, _ = fiche.suivi.boite
        fx = meta["intrinsics"]["fx"]
        releve = (lacet_camera_deg(meta["camera"]["quaternion"]) + math.degrees(math.atan((x + w / 2 - largeur / 2) / fx))) % 360
        reste = None if self.drone.distance_m is None else self.drone.distance_m - self.drone.distance_arret_m
        vitesse = 2.5 if reste is None else max(0.0, min(2.5, reste / 8.0))  # ralentit sur les 20 derniers mètres
        return [{"type": "heading", "heading_deg": releve, "speed_mps": vitesse if reste is None or reste > 0.5 else 0.0}]

    def cloturer(self):
        self.chaine.cloturer(self.t)
        sortie = self.traduire_messages()
        self.journal.fermer()
        return sortie


async def servir(args):
    import websockets
    pont = Pont(args)
    boucle = asyncio.get_running_loop()
    arret = boucle.create_future()

    async def connexion_campagne(ws):
        """Mode campagne : toutes les images, dans l'ordre ; « pas » renvoyé après chacune."""
        from campagne import Campagne
        campagne = getattr(pont, "campagne", None) or Campagne(pont, Path(args.campagne))
        pont.campagne = campagne
        print("simulateur connecté (campagne)", flush=True)
        async for m in ws:
            if isinstance(m, str):
                if await boucle.run_in_executor(None, campagne.message, json.loads(m)) and not arret.done():
                    arret.set_result(True)
                continue
            for o in await boucle.run_in_executor(None, pont.traiter, m):
                await ws.send(json.dumps(o, ensure_ascii=False))
            await ws.send('{"type":"pas"}')

    async def connexion(ws):
        if args.campagne:
            return await connexion_campagne(ws)
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
            await arret      # en campagne : jusqu'au dernier épisode ; sinon jusqu'à Ctrl+C
        finally:
            if not args.campagne:
                pont.cloturer()


def main():
    ap = argparse.ArgumentParser(description="Chaîne IA Cerema branchée sur le simulateur")
    ap.add_argument("--depot", type=Path, default=DEPOT,
                    help="copie du dépôt qui contient ia/chaine et ia/suivi (par défaut, celle-ci)")
    ap.add_argument("--detecteur", default="best4_2",
                    help="best4_2 (défaut, modèle de Guillaume), best4, yolo11n (COCO, celui de l'IMX500) ou un fichier .pt")
    ap.add_argument("--appareil", default="auto",
                    help="où tourne le détecteur : auto (carte graphique NVIDIA ou Apple si elle existe), cpu, mps, cuda:0")
    ap.add_argument("--reseau-type", default="dinov2", choices=["dinov2", "dinov3"])
    ap.add_argument("--fils", type=int, default=None, help="fils d'ONNX Runtime")
    ap.add_argument("--station", help="adresse de la station sol, par exemple http://localhost:8000")
    ap.add_argument("--campagne", metavar="DOSSIER",
                    help="mode campagne (simulateur ouvert avec ?campagne=1) : résultats par épisode dans DOSSIER, "
                         "arrêt après le dernier épisode")
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
