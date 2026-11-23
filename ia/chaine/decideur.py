"""Décideur à règles : pour une fiche, choisit la prochaine action.

Les quatre questions de l'arbre sont posées dans l'ordre, on s'arrête à la première qui s'applique.
Le décideur ne regarde aucune image : il ne lit que la fiche et l'état du drone.
"""
from enum import Enum

from .fiche import Etat, FicheNavire
from .garde_fous import approche_a_abandonner, approche_autorisee
from .reglages import Contexte, Reglages


class Action(str, Enum):
    ATTENDRE = "attendre"
    EXPERT_TYPE = "expert_type"
    EXPERT_OCR = "expert_ocr"
    APPROCHE = "approche"
    ALERTE_COMPLETE = "alerte_complete"
    ALERTE_PARTIELLE = "alerte_partielle"


def actualiser_etat(fiche: FicheNavire, t: float, reglages: Reglages) -> None:
    """Bloc decision : confirme une piste vue assez longtemps, déclare perdue une piste disparue."""
    decision, suivi = fiche.decision, fiche.suivi
    assez_vue = (suivi.images_consecutives >= reglages.images_confirmation
                 and t - suivi.premiere_vue >= reglages.duree_confirmation_s
                 and suivi.confiance >= reglages.confiance_confirmation)
    if decision.etat in (Etat.NOUVELLE, Etat.PERDUE) and assez_vue:
        decision.etat = Etat.CONFIRMEE
    elif decision.etat != Etat.ALERTEE and t - suivi.derniere_vue > reglages.delai_perte_s:
        decision.etat = Etat.PERDUE


def decider(fiche: FicheNavire, t: float, contexte: Contexte, reglages: Reglages) -> tuple[Action, str]:
    etat, tentatives = fiche.decision.etat, fiche.decision.tentatives
    if etat == Etat.NOUVELLE:
        return Action.ATTENDRE, "piste non confirmée"
    if etat == Etat.ALERTEE:
        return Action.ATTENDRE, "alerte déjà envoyée"
    if etat == Etat.PERDUE:
        # Un navire perdu en cours d'identification : on dit ce que l'on sait.
        if fiche.experts.types or fiche.interne.lecture_candidate or fiche.decision.debut_approche is not None:
            return Action.ALERTE_PARTIELLE, "piste perdue"
        return Action.ATTENDRE, "piste perdue"
    if fiche.suivi.derniere_vue != t:
        return Action.ATTENDRE, "navire absent de cette image"

    def essayer(action: Action, nom: str, raison: str) -> tuple[Action, str]:
        dernier = fiche.interne.dernier_essai.get(nom)
        if dernier is not None and t - dernier < reglages.intervalle_essais_s:
            return Action.ATTENDRE, "attente avant un nouvel essai"
        return action, raison

    # 1. Type encore inconnu ?
    if not fiche.type_connu and fiche.largeur_px >= reglages.largeur_min_type_px:
        if tentatives.get("type", 0) < reglages.max_tentatives_type:
            return essayer(Action.EXPERT_TYPE, "type", "type inconnu")
        if fiche.largeur_px >= reglages.croissance_nouvel_essai_type * fiche.interne.largeur_dernier_type:
            return essayer(Action.EXPERT_TYPE, "type", "type hésitant, navire plus gros")

    # 2. Immatriculation déjà lue ?
    if fiche.immatriculation_connue:
        return Action.ALERTE_COMPLETE, "immatriculation lue"

    # 3. Navire assez gros dans l'image ?
    assez_gros = fiche.largeur_px >= reglages.seuil_ocr_px
    if assez_gros and tentatives.get("ocr", 0) < reglages.max_tentatives_ocr:
        return essayer(Action.EXPERT_OCR, "ocr", "navire assez gros pour lire")
    # Essai précoce : la plaque est parfois déjà lisible bien avant le seuil d'approche.
    if (not assez_gros and fiche.largeur_px >= reglages.seuil_ocr_essai_px
            and tentatives.get("ocr_precoce", 0) < reglages.max_essais_ocr_precoces):
        return essayer(Action.EXPERT_OCR, "ocr", "essai de lecture précoce")

    # 4. Approche permise par les garde-fous ?
    if etat == Etat.EN_APPROCHE:
        abandon, raison = approche_a_abandonner(fiche, t, contexte, reglages)
        if abandon:
            return Action.ALERTE_PARTIELLE, raison
        if assez_gros:
            return Action.ALERTE_PARTIELLE, "immatriculation illisible malgré l'approche"
        return Action.ATTENDRE, "approche en cours"
    if not assez_gros:
        if contexte.cible is not None and contexte.cible != fiche.id_piste:
            return Action.ATTENDRE, "une autre approche est en cours"
        autorisee, raison = approche_autorisee(fiche, contexte, reglages)
        deja_vu = fiche.interne.deja_vu
        if (autorisee and reglages.reid_eviter_reapproche and deja_vu is not None and deja_vu.niveau == "sur"
                and deja_vu.navire.immatriculation is not None):
            return Action.ALERTE_PARTIELLE, f"navire reconnu ({deja_vu.navire.immatriculation}), pas de nouvelle approche"
        if autorisee:
            return Action.APPROCHE, "navire trop petit pour lire"
        return Action.ALERTE_PARTIELLE, raison
    return Action.ALERTE_PARTIELLE, "immatriculation illisible"
