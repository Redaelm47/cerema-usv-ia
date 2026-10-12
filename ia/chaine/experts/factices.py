"""Experts factices : font tourner la chaîne sans modèle ni image (scénario simulé, tests)."""
from typing import Callable

from ..fiche import FicheNavire
from ..reglages import Reglages
from .base import Image, Resultat


class ExpertTypeFactice:
    nom = "type"

    def __init__(self, types: tuple[str, ...] = ("chalutier",), confiance: float = 0.9):
        self.types = list(types)
        self.confiance = confiance

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        return Resultat(True, {"types": list(self.types), "confiance": self.confiance})


class ExpertOCRFactice:
    """Lit une immatriculation fixe dès que le navire dépasse le seuil de lisibilité."""
    nom = "ocr"

    def __init__(self, reglages: Reglages, immatriculation: str = "GV 123456"):
        self.reglages = reglages
        self.immatriculation = immatriculation

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        if fiche.largeur_px < self.reglages.seuil_ocr_px:
            return Resultat(False, {"raison": "navire trop petit"})
        return Resultat(True, {"immatriculation": self.immatriculation, "confiance": 0.9})


class ExpertApprocheFactice:
    """Accepte toute approche et prévient qui veut l'entendre."""
    nom = "approche"

    def __init__(self, sur_debut: Callable[[int], None] | None = None,
                 sur_fin: Callable[[int], None] | None = None):
        self.sur_debut = sur_debut
        self.sur_fin = sur_fin

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        if self.sur_debut:
            self.sur_debut(fiche.id_piste)
        return Resultat(True)

    def terminer(self, fiche: FicheNavire) -> None:
        if self.sur_fin:
            self.sur_fin(fiche.id_piste)
