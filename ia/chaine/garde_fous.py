"""Garde-fous : règles fixes qui ont le dernier mot sur toute approche. Aucun modèle appris ici."""
from .fiche import FicheNavire
from .reglages import Contexte, Reglages


def approche_autorisee(fiche: FicheNavire, contexte: Contexte, reglages: Reglages) -> tuple[bool, str]:
    if not contexte.dans_la_zone:
        return False, "drone hors de la zone autorisée"
    if contexte.batterie < reglages.batterie_min_approche:
        return False, "batterie trop basse"
    if fiche.decision.tentatives.get("approche", 0) >= reglages.max_approches:
        return False, "navire déjà approché"
    return True, "approche autorisée"


def approche_a_abandonner(fiche: FicheNavire, t: float, contexte: Contexte, reglages: Reglages) -> tuple[bool, str]:
    """Vérifié à chaque image pendant une approche en cours."""
    if not contexte.dans_la_zone:
        return True, "sortie de la zone autorisée"
    if contexte.batterie < reglages.batterie_min_approche:
        return True, "batterie trop basse"
    if fiche.interne.batterie_debut_approche - contexte.batterie > reglages.energie_max_approche:
        return True, "énergie maximale d'approche dépassée"
    debut = fiche.decision.debut_approche
    if debut is not None:
        if t - debut > reglages.duree_max_approche_s:
            return True, "durée maximale d'approche dépassée"
        # largeur lissée : une seule boîte plus petite (bruit du détecteur, de loin) ne fait pas abandonner
        grossi = fiche.largeur_lissee_px >= reglages.croissance_min_approche * fiche.interne.largeur_debut_approche
        if t - debut > reglages.delai_eloignement_s and not grossi:
            return True, "le navire s'éloigne plus vite que le drone"
    if (contexte.distance_m is not None and contexte.distance_m <= reglages.distance_min_m
            and fiche.largeur_px < reglages.seuil_ocr_px):
        return True, "distance minimale atteinte sans pouvoir lire"
    return False, ""
