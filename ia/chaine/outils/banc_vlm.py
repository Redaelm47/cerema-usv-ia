"""Banc des petits modèles vision-langage (2B paramètres au plus) contre les experts actuels, sur les mêmes images.

    python3 -m chaine.outils.banc_vlm --preparer                       # une fois : recadrages dans data/banc_vlm/
    python3 -m chaine.outils.banc_vlm --modele ../data/vlm/qwen3.5-0.8b/Qwen3.5-0.8B-Q4_K_M.gguf \\
                                      --mmproj ../data/vlm/qwen3.5-0.8b/mmproj-F16.gguf --rapport runs/vlm_qwen.json

Trois questions, posées en une seule invite, avec une réponse JSON imposée par un schéma (llama-server) :
1. navire ou non : les 147 recadrages de navires du test de l'expert type, et les recadrages sans navire du test
   de la classe « pas_navire » (data/pas_navire, rôle test) ;
2. type parmi les six de l'expert type, sur les mêmes 147 navires ;
3. immatriculation, sur les photos réelles de `immatriculations_commons` (photo entière, comme l'OCR la reçoit),
   passée ensuite dans `interpreter()` comme la lecture de l'OCR.
Raisonnement désactivé (`--reasoning off`) : sur le Pi, il multiplierait le texte généré.
Demande llama.cpp (llama-server) et, pour --preparer, ultralytics.
"""
import argparse
import base64
import csv
import json
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from ..experts.base import recadrer
from ..experts.immatriculation import interpreter
from ..experts.ocr import MODELES

BANC = Path("../data/banc_vlm")
TYPES = {"cargo": "cargo", "ferry": "ferry", "fishing": "peche", "inflatable": "pneumatique",
         "motorboat": "vedette", "sailboat": "voilier"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["is_vessel", "type", "registration"],
          "properties": {"is_vessel": {"type": "boolean"},
                         "type": {"enum": [*TYPES, "other", "none"]},
                         "registration": {"type": "string", "maxLength": 20}}}
INVITE = (
    "This image comes from a camera on a small surface drone at sea; it may be a crop around a detection. "
    "Answer in JSON.\n"
    "is_vessel: true only if a boat or ship is clearly visible, false for waves, sun glints, reflections, foam, "
    "buoys, rocks, coast, buildings, birds or sky.\n"
    "type: cargo (cargo or container ship), ferry (ferry or passenger ship), fishing (fishing boat or trawler), "
    "inflatable (inflatable boat or RIB), motorboat (small motor boat, speedboat or launch), sailboat (sailing boat "
    "or yacht), other (another kind of vessel), or none if there is no vessel.\n"
    "registration: the registration number painted on the hull, copied exactly as written (on French fishing boats "
    "it is two letters followed by six digits), or an empty string if no registration is clearly readable. "
    "Never guess or invent one.")
# Pas d'exemple d'immatriculation dans l'invite : avec « par exemple GV 642410 », les trois modèles recopiaient
# l'exemple sur des photos sans immatriculation visible (16/11/2026).


def preparer(types_commons: Path, pas_navire: Path, graine: int = 0, marge: float = 0.08) -> None:
    """Recadrages du test, refaits exactement comme `entrainer_tete_type.py` (même partage, même détecteur)."""
    from ultralytics import YOLO
    d = np.load(types_commons / "signatures_dinov2.npz")
    types, y, fichiers = [str(t) for t in d["types"]], d["type"], d["fichier"]
    rng = np.random.default_rng(graine)
    test = []
    for classe in range(len(types)):
        indices = rng.permutation(np.flatnonzero(y == classe))
        test += [int(i) for i in indices[int(0.8 * len(indices)):]]
    detecteur = YOLO(str(MODELES / "yolo11n.pt"))
    lignes = []
    for i in sorted(test):
        image = cv2.imread(str(types_commons / fichiers[i]))
        boites = detecteur.predict(image, classes=[8], conf=0.25, verbose=False)[0].boxes.xyxy.tolist()
        x0, y0, x1, y1 = max(boites, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        sortie = BANC / "navires" / fichiers[i]
        sortie.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(sortie), recadrer(image, (x0, y0, x1 - x0, y1 - y0), marge))
        lignes.append({"fichier": f"navires/{fichiers[i]}", "navire": "oui", "type": types[y[i]], "source": "commons"})
    for ligne in csv.DictReader(open(pas_navire / "sources.csv")):
        if ligne["role"] == "test":
            lignes.append({"fichier": str((pas_navire / ligne["fichier"]).resolve()), "navire": "non", "type": "",
                           "source": ligne["source"]})
    with open(BANC / "recadrages.csv", "w", newline="") as f:
        csv.DictWriter(f, fieldnames=list(lignes[0])).writeheader()
        csv.DictWriter(f, fieldnames=list(lignes[0])).writerows(lignes)
    print(f"{sum(l['navire'] == 'oui' for l in lignes)} navires, {sum(l['navire'] == 'non' for l in lignes)} "
          f"recadrages sans navire, liste dans {BANC / 'recadrages.csv'}")


class Serveur:
    """llama-server lancé pour un modèle, arrêté à la fin."""

    def __init__(self, modele: str, mmproj: str, port: int, gpu: bool, fils: int | None, journal: Path):
        commande = ["llama-server", "-m", modele, "--mmproj", mmproj, "--port", str(port), "--reasoning", "off",
                    "-c", "8192", "-ngl", "99" if gpu else "0", "--no-webui"]
        if not gpu:
            commande += ["--no-mmproj-offload"]
        if fils:
            commande += ["-t", str(fils)]
        self.url = f"http://127.0.0.1:{port}"
        self.processus = subprocess.Popen(commande, stdout=open(journal, "w"), stderr=subprocess.STDOUT)
        for _ in range(240):
            try:
                if json.load(urllib.request.urlopen(self.url + "/health", timeout=2)).get("status") == "ok":
                    return
            except Exception:
                pass
            if self.processus.poll() is not None:
                raise RuntimeError(f"llama-server s'est arrêté, voir {journal}")
            time.sleep(0.5)
        raise RuntimeError(f"llama-server ne répond pas, voir {journal}")

    def demander(self, chemin_image: str, cote_max: int) -> tuple[dict | None, float, int]:
        image = cv2.imread(chemin_image)
        echelle = cote_max / max(image.shape[:2])
        if echelle < 1:
            image = cv2.resize(image, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_AREA)
        jpeg = base64.b64encode(cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1]).decode()
        corps = {"messages": [{"role": "user", "content": [
                     {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg}"}},
                     {"type": "text", "text": INVITE}]}],
                 "temperature": 0, "seed": 0, "max_tokens": 120,
                 "response_format": {"type": "json_schema", "json_schema": {"name": "reponse", "schema": SCHEMA}}}
        requete = urllib.request.Request(self.url + "/v1/chat/completions", json.dumps(corps).encode(),
                                         {"Content-Type": "application/json"})
        debut = time.perf_counter()
        reponse = json.load(urllib.request.urlopen(requete, timeout=600))
        duree = time.perf_counter() - debut
        texte = reponse["choices"][0]["message"]["content"]
        try:
            return json.loads(texte), duree, reponse["usage"]["prompt_tokens"]
        except (json.JSONDecodeError, KeyError):
            return None, duree, 0

    def arreter(self) -> None:
        self.processus.terminate()
        self.processus.wait(timeout=30)


def banc(serveur: Serveur, photos: Path | None, cote_max: int, limite: int | None,
         liste: Path = BANC / "recadrages.csv") -> dict:
    recadrages = list(csv.DictReader(open(liste)))
    photos_csv = list(csv.DictReader(open(photos / "verites.csv"))) if photos else []
    if limite:
        recadrages = recadrages[::max(len(recadrages) // limite, 1)][:limite]
        photos_csv = photos_csv[:limite]
    durees, jetons, invalides, details = [], [], 0, []
    navires = {"vrais_acceptes": 0, "vrais": 0, "faux_ecartes": 0, "faux": 0, "faux_par_source": {}}
    types = {"bons": 0, "total": 0, "confusion": {}}
    for ligne in recadrages:
        chemin = ligne["fichier"] if Path(ligne["fichier"]).is_absolute() else str(BANC / ligne["fichier"])
        reponse, duree, n = serveur.demander(chemin, cote_max)
        durees.append(duree), jetons.append(n)
        invalides += reponse is None
        reponse = reponse or {"is_vessel": True, "type": "other", "registration": ""}
        details.append({**ligne, "reponse": reponse, "duree_s": round(duree, 2)})
        if ligne["navire"] == "oui":
            navires["vrais"] += 1
            navires["vrais_acceptes"] += bool(reponse["is_vessel"])
            types["total"] += 1
            predit = TYPES.get(reponse["type"], reponse["type"])
            types["bons"] += predit == ligne["type"]
            types["confusion"].setdefault(ligne["type"], {}).setdefault(predit, 0)
            types["confusion"][ligne["type"]][predit] += 1
        else:
            navires["faux"] += 1
            navires["faux_ecartes"] += not reponse["is_vessel"]
            par_source = navires["faux_par_source"].setdefault(ligne["source"], [0, 0])
            par_source[0] += not reponse["is_vessel"]
            par_source[1] += 1
    lecture = {"visibles": 0, "lues": 0, "autre_immatriculation": 0, "non_visibles": 0, "lectures_sur_non_visibles": 0}
    for photo in photos_csv:
        reponse, duree, n = serveur.demander(str(photos / photo["fichier"]), cote_max)
        durees.append(duree), jetons.append(n)
        invalides += reponse is None
        brute = (reponse or {}).get("registration", "")
        lue = interpreter(brute)
        lue = lue.texte if lue else None
        details.append({"photo": photo["fichier"], "verite": photo["immatriculation"], "visible": photo["visible"],
                        "brute": brute, "lue": lue, "duree_s": round(duree, 2)})
        if photo["visible"] == "oui":
            lecture["visibles"] += 1
            lecture["lues"] += lue == photo["immatriculation"]
            lecture["autre_immatriculation"] += lue is not None and lue != photo["immatriculation"]
        else:
            lecture["non_visibles"] += 1
            lecture["lectures_sur_non_visibles"] += lue is not None
    return {"navire_ou_non": navires, "type": types, "immatriculation": lecture, "reponses_invalides": invalides,
            "temps_s": {"mediane": round(statistics.median(durees), 2), "max": round(max(durees), 2)},
            "jetons_image_mediane": int(statistics.median(jetons)), "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preparer", action="store_true", help="refait les recadrages du banc")
    parser.add_argument("--modele", help="fichier GGUF du modèle")
    parser.add_argument("--mmproj", help="fichier GGUF de l'encodeur d'image")
    parser.add_argument("--photos", default="../data/immatriculations_commons", help="'' pour ne pas lire de photos")
    parser.add_argument("--recadrages", default=str(BANC / "recadrages.csv"),
                        help="liste des recadrages (fichier, navire, type, source)")
    parser.add_argument("--cote-max", type=int, default=1024, help="plus grand côté de l'image envoyée")
    parser.add_argument("--processeur", action="store_true", help="sans GPU, pour approcher le Pi (--fils 4)")
    parser.add_argument("--fils", type=int)
    parser.add_argument("--limite", type=int, help="nombre d'images par partie, pour un essai rapide")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--rapport", help="fichier JSON du rapport")
    args = parser.parse_args()
    if args.preparer:
        preparer(Path("../data/types_commons"), Path("../data/pas_navire"))
        return
    rapport_chemin = Path(args.rapport or "runs/banc_vlm.json")
    rapport_chemin.parent.mkdir(parents=True, exist_ok=True)
    serveur = Serveur(args.modele, args.mmproj, args.port, not args.processeur, args.fils,
                      rapport_chemin.with_suffix(".serveur.log"))
    try:
        rapport = banc(serveur, Path(args.photos) if args.photos else None, args.cote_max, args.limite,
                       Path(args.recadrages))
    finally:
        serveur.arreter()
    rapport.update(modele=Path(args.modele).name, processeur=args.processeur, cote_max=args.cote_max)
    rapport_chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    n, t, l = rapport["navire_ou_non"], rapport["type"], rapport["immatriculation"]
    print(f"{rapport['modele']} : navires acceptés {n['vrais_acceptes']}/{n['vrais']}, sans navire écartés "
          f"{n['faux_ecartes']}/{n['faux']} {n['faux_par_source']}, bons types {t['bons']}/{t['total']}, "
          f"immatriculations lues {l['lues']}/{l['visibles']} (autres {l['autre_immatriculation']}, sur photos sans "
          f"immatriculation visible {l['lectures_sur_non_visibles']}/{l['non_visibles']}), réponses invalides "
          f"{rapport['reponses_invalides']}, {rapport['temps_s']['mediane']} s par image, "
          f"{rapport['jetons_image_mediane']} jetons d'invite")


if __name__ == "__main__":
    main()
