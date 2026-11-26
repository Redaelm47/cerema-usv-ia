"""Recadrages sans navire, pour apprendre à l'expert type à dire « pas un navire ».

    python3 -m chaine.outils.extraire_negatifs

Deux genres de recadrages :
- `fausse_detection` : ce que YOLO croit être un bateau, avec une confiance faible, loin de tout vrai navire
  (vague, reflet, écume, horizon). C'est ce qui peut arriver jusqu'aux experts sur le drone.
- `aleatoire` : un rectangle tiré au hasard, de la forme et de la taille d'un navire (mer, ciel, côte, quai).

Trois sources :
- la scène Blender (`data/blender/rendu/scene_01`) : la vérité donne le gisement et la distance de chaque
  navire, d'où une bande verticale interdite autour de chacun ;
- la vidéo Dingle : le seul navire est celui que YOLO voit avec assurance, et l'on ne garde que les images
  où il est vu ;
- les photos Commons de `types_commons`, sauf cargos et ferries : seulement des rectangles au hasard, loin de
  toute détection de bateau, même douteuse (dans un port, une détection douteuse est souvent un vrai petit bateau).

Le rôle de chaque recadrage (entraînement, calibration, test) est fixé ici : par tranche de temps pour les
vidéos (60 / 20 / 20 %, pour que deux images voisines ne soient pas l'une en entraînement et l'autre en test),
par photo pour Commons. Écrit `data/pas_navire/<source>/*.jpg` et `data/pas_navire/sources.csv`.
Demande ultralytics ; à lancer sur un ordinateur, pas sur le Pi.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np

from ..experts.ocr import MODELES

BATEAU = 8  # classe « boat » de COCO, celle que garde le détecteur de la caméra
ROLES = ("train", "calib", "test")
# Photos Commons dont le rectangle tiré (graine 0) tombe sur un morceau de bateau : coque, nom peint,
# pneumatique, voiliers au loin. Retirées après examen à l'œil des recadrages, le 16/11/2026.
EXCLUES = {"peche/0096.jpg", "peche/0110.jpg", "pneumatique/0005.jpg", "pneumatique/0093.jpg",
           "pneumatique/0131.jpg", "vedette/0036.jpg", "vedette/0038.jpg", "voilier/0082.jpg"}


def role_par_temps(position: float) -> str:
    """position entre 0 et 1 dans la vidéo -> rôle, par tranches de 60 / 20 / 20 %."""
    return "train" if position < 0.6 else ("calib" if position < 0.8 else "test")


def se_chevauchent(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def dilater(boite, facteur: float):
    x, y, l, h = boite
    return (x - l * (facteur - 1) / 2, y - h * (facteur - 1) / 2, l * facteur, h * facteur)


def detections(detecteur, image, confiance_min: float):
    """Boîtes de bateau (x, y, largeur, hauteur) et leurs confiances."""
    boites = detecteur.predict(image, classes=[BATEAU], conf=confiance_min, verbose=False)[0].boxes
    return [((x0, y0, x1 - x0, y1 - y0), float(c)) for (x0, y0, x1, y1), c in zip(boites.xyxy.tolist(), boites.conf.tolist())]


def rectangle_au_hasard(rng, largeur_image: int, hauteur_image: int, interdits, essais: int = 50):
    """Rectangle de la forme d'un navire (largeur 48 à 480 px, 1,2 à 4 fois plus large que haut), hors des zones interdites."""
    for _ in range(essais):
        largeur = float(np.exp(rng.uniform(math.log(48), math.log(480))))
        hauteur = largeur / rng.uniform(1.2, 4.0)
        if largeur >= largeur_image or hauteur >= hauteur_image:
            continue
        boite = (rng.uniform(0, largeur_image - largeur), rng.uniform(0, hauteur_image - hauteur), largeur, hauteur)
        if not any(se_chevauchent(boite, z) for z in interdits):
            return boite
    return None


class Ecrivain:
    def __init__(self, sortie: Path):
        self.sortie, self.lignes = sortie, []

    def garder(self, image, boite, source: str, origine: str, genre: str, role: str, confiance=None) -> None:
        x, y, l, h = (int(round(v)) for v in boite)
        x, y = max(x, 0), max(y, 0)
        recadrage = image[y:y + h, x:x + l]
        if min(recadrage.shape[:2]) < 16:
            return
        nom = f"{source}/{len([r for r in self.lignes if r['source'] == source]):04d}.jpg"
        (self.sortie / source).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self.sortie / nom), recadrage, [cv2.IMWRITE_JPEG_QUALITY, 95])
        self.lignes.append({"fichier": nom, "source": source, "origine": origine, "genre": genre, "role": role,
                            "boite": f"{x} {y} {l} {h}", "confiance_yolo": "" if confiance is None else round(confiance, 3)})


def fausses_detections(ecrivain, image, candidates, interdits, source, origine, role, maximum):
    gardees = 0
    for boite, confiance in sorted(candidates, key=lambda c: -c[1]):
        if gardees >= maximum:
            break
        if boite[2] < 24 or any(se_chevauchent(boite, z) for z in interdits):
            continue
        ecrivain.garder(image, boite, source, origine, "fausse_detection", role, confiance)
        gardees += 1


def scene_blender(ecrivain, detecteur, rng, dossier: Path, verite: Path, pas: int) -> None:
    verite = json.loads(verite.read_text())
    images = sorted(dossier.glob("image_*.jpg"))
    for numero in range(0, len(images), pas):
        image = cv2.imread(str(images[numero]))
        hauteur, largeur = image.shape[:2]
        focale = (largeur / 2) / math.tan(math.radians(verite["champ_horizontal_deg"] / 2))
        interdits = []
        for navire in verite["navires"]:
            vu = navire["par_image"][min(numero, len(navire["par_image"]) - 1)]
            centre = largeur / 2 + focale * math.tan(math.radians(vu["gisement_deg"]))
            demi = focale * navire["longueur_m"] / vu["distance_m"] / 2 + 150  # 150 px : roulis et erreur de projection
            interdits.append((centre - demi, -1.0, 2 * demi, hauteur + 2.0))  # toute la hauteur de l'image
        candidates = detections(detecteur, image, 0.01)
        interdits += [dilater(b, 2.0) for b, c in candidates if c >= 0.3]
        role = role_par_temps(numero / len(images))
        origine = images[numero].name
        fausses_detections(ecrivain, image, candidates, interdits, "blender", origine, role, 2)
        boite = rectangle_au_hasard(rng, largeur, hauteur, interdits)
        if boite:
            ecrivain.garder(image, boite, "blender", origine, "aleatoire", role)


def video_dingle(ecrivain, detecteur, rng, video: Path, pas: int) -> None:
    lecteur = cv2.VideoCapture(str(video))
    total = int(lecteur.get(cv2.CAP_PROP_FRAME_COUNT))
    for numero in range(0, total, pas):
        lecteur.set(cv2.CAP_PROP_POS_FRAMES, numero)
        lu, image = lecteur.read()
        if not lu:
            break
        candidates = detections(detecteur, image, 0.01)
        surs = [b for b, c in candidates if c >= 0.3]
        if not surs:
            continue  # navire non vu : il pourrait être n'importe où
        hauteur, largeur = image.shape[:2]
        interdits = [dilater(b, 2.0) for b in surs]
        role = role_par_temps(numero / total)
        origine = f"image {numero}"
        fausses_detections(ecrivain, image, candidates, interdits, "dingle", origine, role, 2)
        boite = rectangle_au_hasard(rng, largeur, hauteur, interdits)
        if boite:
            ecrivain.garder(image, boite, "dingle", origine, "aleatoire", role)


def photos_commons(ecrivain, detecteur, rng, dossier: Path, nombre: int) -> None:
    # Pas de photos de cargos ni de ferries : YOLO n'y encadre souvent qu'une partie du navire, et un rectangle
    # au hasard tombe sur des conteneurs ou une superstructure, c'est-à-dire sur un navire vu de près.
    photos = sorted(p for p in dossier.glob("*/*.jpg") if p.parent.name not in ("cargo", "ferry"))
    for chemin in [photos[i] for i in sorted(rng.choice(len(photos), min(nombre, len(photos)), replace=False))]:
        image = cv2.imread(str(chemin))
        if image is None:
            continue
        hauteur, largeur = image.shape[:2]
        interdits = [dilater(b, 1.5) for b, _ in detections(detecteur, image, 0.02)]
        boite = rectangle_au_hasard(rng, largeur, hauteur, interdits)
        if boite:
            role = ROLES[int(rng.choice(3, p=[0.6, 0.2, 0.2]))]
            origine = f"{chemin.parent.name}/{chemin.name}"
            if origine not in EXCLUES:
                ecrivain.garder(image, boite, "commons", origine, "aleatoire", role)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--donnees", default="../data", help="dossier data du dépôt")
    parser.add_argument("--sortie", default="../data/pas_navire")
    parser.add_argument("--pas-blender", type=int, default=3, help="une image sur N de la scène Blender (15 images/s)")
    parser.add_argument("--pas-dingle", type=int, default=6, help="une image sur N de la vidéo Dingle (50 images/s)")
    parser.add_argument("--photos", type=int, default=300, help="photos Commons tirées au hasard")
    parser.add_argument("--graine", type=int, default=0)
    args = parser.parse_args()

    from ultralytics import YOLO
    detecteur, rng = YOLO(str(MODELES / "yolo11n.pt")), np.random.default_rng(args.graine)
    donnees, sortie = Path(args.donnees), Path(args.sortie)
    ecrivain = Ecrivain(sortie)
    scene_blender(ecrivain, detecteur, rng, donnees / "blender/rendu/scene_01", donnees / "scene-blender-01-verite.json",
                  args.pas_blender)
    video_dingle(ecrivain, detecteur, rng, donnees / "bateau-peche-dingle.webm", args.pas_dingle)
    photos_commons(ecrivain, detecteur, rng, donnees / "types_commons", args.photos)

    with open(sortie / "sources.csv", "w", newline="") as f:
        csv.DictWriter(f, fieldnames=list(ecrivain.lignes[0])).writeheader()
        csv.DictWriter(f, fieldnames=list(ecrivain.lignes[0])).writerows(ecrivain.lignes)
    for source in ("blender", "dingle", "commons"):
        lignes = [r for r in ecrivain.lignes if r["source"] == source]
        print(source, len(lignes), "recadrages :", {g: sum(r["genre"] == g for r in lignes) for g in ("fausse_detection", "aleatoire")},
              {r: sum(l["role"] == r for l in lignes) for r in ROLES})
    print(f"écrit dans {sortie}")


if __name__ == "__main__":
    main()
