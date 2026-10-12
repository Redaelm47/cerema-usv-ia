"""Entraîne la tête linéaire de l'expert type et calibre sa prédiction conforme.

    python3 -m chaine.outils.entrainer_tete_type --images ../data/types_commons

Étapes : recadrage de chaque photo sur son plus gros bateau (YOLO, comme le fera la chaîne), signature
DINOv2 de chaque recadrage, régression logistique sur 60 % des images, seuil conforme calibré sur 20 %,
mesures sur les 20 % restants. Écrit `modeles/tete_type.npz` et `modeles/tete_type.json` (les chiffres).
Demande ultralytics ; à lancer sur un ordinateur, pas sur le Pi.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from ..experts.base import recadrer
from ..experts.ocr import MODELES
from ..experts.type import RESEAUX, Signature

LARGEURS_TEST = (32, 48, 64, 96, 128, 224)  # largeur du navire en pixels, pour mesurer l'effet de la distance


def reduire(recadrage: np.ndarray, largeur: int) -> np.ndarray:
    echelle = largeur / recadrage.shape[1]
    if echelle >= 1:
        return recadrage
    return cv2.resize(recadrage, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_AREA)


def calculer_signatures(dossier: Path, marge: float, rng: np.random.Generator, reseau: str) -> dict:
    from ultralytics import YOLO
    detecteur, signature = YOLO(str(MODELES / "yolo11n.pt")), Signature(reseau=reseau)
    types = sorted(d.name for d in dossier.iterdir() if d.is_dir())
    lignes = {"type": [], "fichier": [], "native": [], "reduite": [], **{f"l{l}": [] for l in LARGEURS_TEST}}
    for numero, nom in enumerate(types):
        gardees = 0
        for chemin in sorted((dossier / nom).glob("*.jpg")):
            image = cv2.imread(str(chemin))
            if image is None:
                continue
            boites = detecteur.predict(image, classes=[8], conf=0.25, verbose=False)[0].boxes.xyxy.tolist()
            boites = [(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in boites]
            if not boites:
                continue
            boite = max(boites, key=lambda b: b[2] * b[3])
            if boite[2] * boite[3] < 0.03 * image.shape[0] * image.shape[1]:
                continue  # bateau trop petit dans la photo : étiquette douteuse
            recadrage = recadrer(image, boite, marge)
            lignes["type"].append(numero)
            lignes["fichier"].append(f"{nom}/{chemin.name}")
            lignes["native"].append(signature.calculer(recadrage))
            lignes["reduite"].append(signature.calculer(reduire(recadrage, int(rng.integers(40, 160)))))
            for largeur in LARGEURS_TEST:
                lignes[f"l{largeur}"].append(signature.calculer(reduire(recadrage, largeur)))
            gardees += 1
        print(f"{nom} : {gardees} recadrages", flush=True)
    return {"types": np.array(types), **{k: np.array(v) for k, v in lignes.items()}}


def entrainer(x: np.ndarray, y: np.ndarray, classes: int, regularisation: float, iterations: int = 800):
    """Régression logistique à plusieurs classes, descente de gradient (Adam), sans autre bibliothèque."""
    poids, biais = np.zeros((classes, x.shape[1])), np.zeros(classes)
    cible = np.eye(classes)[y]
    m = [np.zeros_like(poids), np.zeros_like(biais)]
    v = [np.zeros_like(poids), np.zeros_like(biais)]
    for i in range(1, iterations + 1):
        p = probabilites(x, poids, biais)
        gradients = [(p - cible).T @ x / len(x) + regularisation * poids, (p - cible).mean(axis=0)]
        for k, (parametre, g) in enumerate(zip((poids, biais), gradients)):
            m[k] = 0.9 * m[k] + 0.1 * g
            v[k] = 0.999 * v[k] + 0.001 * g * g
            parametre -= 0.05 * (m[k] / (1 - 0.9 ** i)) / (np.sqrt(v[k] / (1 - 0.999 ** i)) + 1e-8)
    return poids, biais


def probabilites(x, poids, biais):
    scores = x @ poids.T + biais
    exposants = np.exp(scores - scores.max(axis=1, keepdims=True))
    return exposants / exposants.sum(axis=1, keepdims=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--images", default="../data/types_commons", help="un sous-dossier par type")
    parser.add_argument("--alpha", type=float, default=0.1, help="taux d'erreur visé : le vrai type manque au plus alpha fois")
    parser.add_argument("--marge", type=float, default=0.08)
    parser.add_argument("--graine", type=int, default=0)
    parser.add_argument("--reseau", choices=sorted(RESEAUX), default="dinov2", help="réseau figé")
    args = parser.parse_args()
    rng = np.random.default_rng(args.graine)  # ne sert qu'au partage : le même pour tous les réseaux

    dossier = Path(args.images)
    cache = dossier / f"signatures_{args.reseau}.npz"
    if cache.exists():
        d = dict(np.load(cache))
        print(f"signatures relues dans {cache}")
    else:
        d = calculer_signatures(dossier, args.marge, np.random.default_rng(args.graine + 1), args.reseau)
        np.savez(cache, **d)
    types, y = [str(t) for t in d["types"]], d["type"]
    n, classes = len(y), len(types)

    # Partage 60 / 20 / 20, type par type
    role = np.empty(n, dtype="U5")
    for classe in range(classes):
        indices = rng.permutation(np.flatnonzero(y == classe))
        a, b = int(0.6 * len(indices)), int(0.8 * len(indices))
        role[indices[:a]], role[indices[a:b]], role[indices[b:]] = "train", "calib", "test"
    train, calib, test = (role == r for r in ("train", "calib", "test"))

    # Entraînement sur les recadrages natifs et réduits ; régularisation choisie sur le jeu de calibration
    x_train = np.concatenate([d["native"][train], d["reduite"][train]])
    y_train = np.concatenate([y[train], y[train]])
    x_calib = np.concatenate([d["native"][calib], d["reduite"][calib]])
    y_calib = np.concatenate([y[calib], y[calib]])
    essais = {}
    for regularisation in (1e-2, 1e-3, 1e-4):
        poids, biais = entrainer(x_train, y_train, classes, regularisation)
        essais[regularisation] = (float((probabilites(x_calib, poids, biais).argmax(1) == y_calib).mean()), poids, biais)
        print(f"régularisation {regularisation:g} : exactitude de calibration {essais[regularisation][0]:.3f}")
    regularisation = max(essais, key=lambda r: essais[r][0])
    _, poids, biais = essais[regularisation]

    # Prédiction conforme : seuil tel que le vrai type soit dans l'ensemble au moins 1 - alpha fois
    scores = 1 - probabilites(x_calib, poids, biais)[np.arange(len(y_calib)), y_calib]
    rang = min(math.ceil((len(scores) + 1) * (1 - args.alpha)), len(scores))
    seuil = 1 - float(np.sort(scores)[rang - 1])

    def mesurer(x, y_vrai):
        p = probabilites(x, poids, biais)
        dans = p >= seuil
        dans[np.arange(len(p)), p.argmax(1)] = True
        return {"exactitude": round(float((p.argmax(1) == y_vrai).mean()), 3),
                "couverture": round(float(dans[np.arange(len(p)), y_vrai].mean()), 3),
                "taille_ensemble": round(float(dans.sum(1).mean()), 2),
                "un_seul_type": round(float((dans.sum(1) == 1).mean()), 3)}

    rapport = {"reseau": args.reseau, "types": types, "images": {t: int((y == i).sum()) for i, t in enumerate(types)},
               "partage": {"entrainement": int(train.sum()), "calibration": int(calib.sum()), "test": int(test.sum())},
               "regularisation": regularisation, "alpha": args.alpha, "seuil": round(seuil, 4),
               "test_natif": mesurer(d["native"][test], y[test]),
               "test_par_largeur_px": {str(l): mesurer(d[f"l{l}"][test], y[test]) for l in LARGEURS_TEST}}
    confusion = np.zeros((classes, classes), int)
    for vrai, predit in zip(y[test], probabilites(d["native"][test], poids, biais).argmax(1)):
        confusion[vrai, predit] += 1
    rapport["confusion_test"] = {t: confusion[i].tolist() for i, t in enumerate(types)}
    print(json.dumps({k: rapport[k] for k in ("reseau", "partage", "regularisation", "seuil", "test_natif",
                                              "test_par_largeur_px")}, ensure_ascii=False, indent=1))

    np.savez(MODELES / f"tete_type_{args.reseau}.npz", types=np.array(types), poids=poids.astype(np.float32),
             biais=biais.astype(np.float32), seuil=np.float32(seuil))
    (MODELES / f"tete_type_{args.reseau}.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2) + "\n")
    print(f"tête écrite dans {MODELES / f'tete_type_{args.reseau}.npz'}")


if __name__ == "__main__":
    main()
