"""Expert type : DINO ViT-S figé (v2 ou v3), puis une petite tête linéaire, puis un ensemble de types possibles.

Le réseau figé donne une signature du navire (768 nombres). La tête linéaire, entraînée à part sur peu
d'images (`outils/entrainer_tete_type.py`), en tire une probabilité par type. La prédiction conforme
garde tous les types dont la probabilité dépasse un seuil calibré : un seul type si l'expert est sûr,
plusieurs s'il hésite.
"""
from pathlib import Path

import cv2
import numpy as np

from ..fiche import FicheNavire
from .base import Image, Resultat, recadrer
from .ocr import MODELES, session

COTE = 224
# Réseaux figés possibles : fichier ONNX, et nombre de jetons avant ceux de l'image (classe, puis registres).
RESEAUX = {"dinov2": ("dinov2_vits14.onnx", 1), "dinov3": ("dinov3_vits16/model.onnx", 5)}
MOYENNE = np.array([0.485, 0.456, 0.406], np.float32)  # normalisation d'ImageNet, en RVB
ECART = np.array([0.229, 0.224, 0.225], np.float32)


def preparer(recadrage: Image) -> np.ndarray:
    """Recadrage BGR -> entrée du réseau : navire entier dans un carré, bandes à la couleur moyenne."""
    hauteur, largeur = recadrage.shape[:2]
    echelle = COTE / max(hauteur, largeur)
    l, h = max(int(round(largeur * echelle)), 1), max(int(round(hauteur * echelle)), 1)
    interpolation = cv2.INTER_AREA if echelle < 1 else cv2.INTER_CUBIC
    reduit = cv2.cvtColor(cv2.resize(recadrage, (l, h), interpolation=interpolation), cv2.COLOR_BGR2RGB)
    carre = np.zeros((COTE, COTE, 3), np.float32)  # zéro = couleur moyenne après normalisation
    x, y = (COTE - l) // 2, (COTE - h) // 2
    carre[y:y + h, x:x + l] = (reduit.astype(np.float32) / 255.0 - MOYENNE) / ECART
    return carre.transpose(2, 0, 1)[None]


class Signature:
    """Le réseau figé : une image de navire -> un vecteur de 768 nombres, de norme 1."""

    def __init__(self, dossier: Path = MODELES, fils: int | None = None, reseau: str = "dinov2"):
        fichier, self.jetons_avant_image = RESEAUX[reseau]
        self.reseau = session(dossier / fichier, fils)

    def calculer(self, recadrage: Image) -> np.ndarray:
        jetons = self.reseau.run(["last_hidden_state"], {"pixel_values": preparer(recadrage)})[0][0]
        # jeton de classe + moyenne des jetons de l'image
        vecteur = np.concatenate([jetons[0], jetons[self.jetons_avant_image:].mean(axis=0)])
        return vecteur / np.linalg.norm(vecteur)


class Tete:
    """Tête linéaire et seuil de la prédiction conforme, lus dans un fichier .npz."""

    def __init__(self, chemin: Path):
        if not chemin.exists():
            raise FileNotFoundError(f"{chemin} manquant : lancer python3 -m chaine.outils.entrainer_tete_type")
        donnees = np.load(chemin)
        self.types = [str(t) for t in donnees["types"]]
        self.poids, self.biais = donnees["poids"], donnees["biais"]
        self.seuil = float(donnees["seuil"])  # un type est gardé si sa probabilité atteint ce seuil

    def probabilites(self, signature: np.ndarray) -> np.ndarray:
        scores = self.poids @ signature + self.biais
        exposants = np.exp(scores - scores.max())
        return exposants / exposants.sum()

    def ensemble(self, probabilites: np.ndarray) -> list[str]:
        """Types possibles, du plus probable au moins probable. Jamais vide."""
        ordre = np.argsort(-probabilites)
        return [self.types[i] for i in ordre if probabilites[i] >= self.seuil] or [self.types[ordre[0]]]


class ExpertType:
    nom = "type"

    def __init__(self, dossier: Path = MODELES, fils: int | None = None, marge: float = 0.08,
                 reseau: str = "dinov2"):
        self.signature = Signature(dossier, fils, reseau)
        self.tete = Tete(dossier / f"tete_type_{reseau}.npz")
        self.marge = marge
        self.cumuls: dict[int, tuple[np.ndarray, int]] = {}  # par piste : somme des probabilités, nombre d'essais

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        recadrage = recadrer(image, fiche.suivi.boite, self.marge)
        if min(recadrage.shape[:2], default=0) < 2:
            return Resultat(False, {"raison": "recadrage vide"})
        probabilites = self.tete.probabilites(self.signature.calculer(recadrage))
        somme, essais = self.cumuls.get(fiche.id_piste, (np.zeros_like(probabilites), 0))
        somme, essais = somme + probabilites, essais + 1
        self.cumuls[fiche.id_piste] = (somme, essais)
        moyenne = somme / essais  # moyenne sur les essais de la même piste
        return Resultat(True, {"types": self.tete.ensemble(moyenne), "confiance": round(float(moyenne.max()), 3),
                               "probabilites": {t: round(float(p), 3) for t, p in zip(self.tete.types, moyenne)}})

    def oublier(self, id_piste: int) -> None:
        self.cumuls.pop(id_piste, None)

    def renommer(self, ancien: int, nouveau: int) -> None:
        if ancien in self.cumuls:
            self.cumuls[nouveau] = self.cumuls.pop(ancien)
