"""Filtre qualité : mesure de netteté sur le recadrage, sans réseau de neurones.

Passe avant chaque expert qui regarde l'image, pour ne pas le réveiller sur une image inexploitable.
"""
import cv2

from ..fiche import FicheNavire
from ..reglages import Reglages
from .base import Image, Resultat, recadrer

COTE_MESURE = 512  # le recadrage est ramené à ce grand côté avant la mesure


def mesurer(recadrage: Image) -> tuple[float, float]:
    """Netteté (variance du laplacien) et contraste (écart-type) du recadrage, en niveaux de gris."""
    gris = cv2.cvtColor(recadrage, cv2.COLOR_BGR2GRAY) if recadrage.ndim == 3 else recadrage
    grand_cote = max(gris.shape)
    if grand_cote > COTE_MESURE:
        echelle = COTE_MESURE / grand_cote
        gris = cv2.resize(gris, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gris, cv2.CV_64F).var()), float(gris.std())


class FiltreQualite:
    nom = "qualite"

    def __init__(self, reglages: Reglages):
        self.reglages = reglages

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        return self.evaluer(recadrer(image, fiche.suivi.boite))

    def evaluer(self, recadrage: Image) -> Resultat:
        """Juge un recadrage déjà fait. Sert aussi à comparer les images d'une même piste entre elles."""
        if min(recadrage.shape[:2], default=0) < self.reglages.cote_min_px:
            return Resultat(False, {"raison": "recadrage trop petit", "nettete": 0.0, "contraste": 0.0})
        nettete, contraste = mesurer(recadrage)
        valeurs = {"nettete": round(nettete, 1), "contraste": round(contraste, 1)}
        if contraste < self.reglages.contraste_min:
            return Resultat(False, {"raison": "contraste trop faible", **valeurs})
        if nettete < self.reglages.nettete_min:
            return Resultat(False, {"raison": "image floue", **valeurs})
        return Resultat(True, valeurs)
