"""Mesure si la couleur de la coque aide DINOv2 à séparer les navires. Prototype.

    python -m chaine.outils.comparer_couleur ../data/reid --signatures runs/signatures_reid.npz

Même dossier que `mesurer_reid.py` : UN SOUS-DOSSIER PAR NAVIRE, images recadrées sur le navire.

Pour chaque méthode (DINOv2 seul, couleur seule, mélanges), on compare toutes les paires d'images :
- AUC : probabilité qu'une paire du MÊME navire reçoive une meilleure note qu'une paire de navires DIFFÉRENTS.
  0,5 = hasard, 1 = séparation parfaite ;
- confusion à 80 % de reconnaissance : on règle le seuil pour reconnaître 80 % des paires du même navire,
  et on lit la part de paires de navires différents confondues. Plus c'est bas, mieux c'est.
"""
import argparse
from pathlib import Path

import numpy as np

from ..couleur import fusionner, signature_couleur, similarite_couleur
from .mesurer_reid import calculer_signatures, lister

POIDS = (0.0, 0.1, 0.2, 0.3, 0.5, 1.0)


def descripteurs_couleur(navires: dict[str, list[Path]]) -> dict[str, np.ndarray]:
    import cv2

    resultat = {}
    for nom, images in navires.items():
        vecteurs = []
        for chemin in images:
            image = cv2.imdecode(np.fromfile(str(chemin), np.uint8), cv2.IMREAD_COLOR)
            v = None if image is None else signature_couleur(image)
            if v is not None:
                vecteurs.append(v)
        if vecteurs:
            resultat[nom] = np.stack(vecteurs)
    return resultat


def matrices(signatures: dict[str, np.ndarray], couleurs: dict[str, np.ndarray]):
    """Notes de toutes les paires d'images (triangle haut), avec l'indication « même navire »."""
    noms = [n for n in signatures if n in couleurs and len(signatures[n]) == len(couleurs[n])]
    dino = np.vstack([signatures[n] for n in noms])
    coul = np.vstack([couleurs[n] for n in noms])
    etiquettes = np.concatenate([[i] * len(signatures[n]) for i, n in enumerate(noms)])
    haut = np.triu_indices(len(dino), k=1)
    s_dino = (dino @ dino.T)[haut]
    s_coul = np.clip(coul @ coul.T, 0, 1)[haut]
    meme = (etiquettes[:, None] == etiquettes[None, :])[haut]
    return s_dino, s_coul, meme


def auc(notes: np.ndarray, meme: np.ndarray) -> float:
    """Probabilité qu'une paire du même navire ait une meilleure note qu'une paire différente (rangs)."""
    positifs, negatifs = notes[meme], notes[~meme]
    if len(positifs) == 0 or len(negatifs) == 0:
        return float("nan")
    ordre = np.argsort(np.concatenate([positifs, negatifs]), kind="mergesort")
    rangs = np.empty(len(ordre))
    rangs[ordre] = np.arange(1, len(ordre) + 1)
    return float((rangs[:len(positifs)].sum() - len(positifs) * (len(positifs) + 1) / 2)
                 / (len(positifs) * len(negatifs)))


def confusion_a_rappel(notes: np.ndarray, meme: np.ndarray, rappel: float = 0.8) -> float:
    positifs, negatifs = notes[meme], notes[~meme]
    if len(positifs) == 0 or len(negatifs) == 0:
        return float("nan")
    seuil = np.percentile(positifs, (1 - rappel) * 100)
    return float((negatifs >= seuil).mean())


def comparer(signatures: dict[str, np.ndarray], couleurs: dict[str, np.ndarray]) -> list[dict]:
    s_dino, s_coul, meme = matrices(signatures, couleurs)
    lignes = []
    for poids in POIDS:
        notes = fusionner(s_dino, s_coul, poids)
        etiquette = "DINOv2 seul" if poids == 0 else "couleur seule" if poids == 1 else f"mélange {poids:.0%} couleur"
        lignes.append({"methode": etiquette, "poids_couleur": poids, "auc": round(auc(notes, meme), 4),
                       "confusion_a_80_pour_cent": round(confusion_a_rappel(notes, meme), 4)})
    return lignes


def main() -> None:
    parser = argparse.ArgumentParser(description="La couleur aide-t-elle DINOv2 à distinguer les navires ?")
    parser.add_argument("dossier", type=Path, help="un sous-dossier par navire, images recadrées dedans")
    parser.add_argument("--reseau", choices=("dinov2", "dinov3"), default="dinov2")
    parser.add_argument("--fils", type=int)
    parser.add_argument("--signatures", type=Path, help="cache .npz des signatures DINOv2")
    args = parser.parse_args()

    navires = lister(args.dossier)
    if len(navires) < 4:
        parser.error(f"{len(navires)} navire(s) trouvé(s) dans {args.dossier} : il en faut au moins 4")
    signatures = calculer_signatures(navires, args.reseau, args.fils, args.signatures)
    couleurs = descripteurs_couleur(navires)
    print(f"{len(signatures)} navires\n")
    print(f"{'méthode':<26}{'AUC':>8}{'confusion à 80 %':>20}")
    for ligne in comparer(signatures, couleurs):
        print(f"{ligne['methode']:<26}{ligne['auc']:>8.3f}{ligne['confusion_a_80_pour_cent']:>20.1%}")
    if len(signatures) < 30:
        print(f"\nAttention : {len(signatures)} navires seulement, ordre de grandeur.")


if __name__ == "__main__":
    main()
