"""Les contrats avec les deux autres parties : lecture des observations (1), écriture des messages (3).

Le contrat 2 (fiche navire) est dans `fiche.py`, méthode `FicheNavire.contrat`.
"""
from typing import Any

from .fiche import FicheNavire, Observation

ACTIONS = ("expert_type", "expert_ocr", "approche", "alerte_complete", "alerte_partielle")
MODES = ("patrouille", "approche")


class ContratInvalide(ValueError):
    pass


def observations(t: float, pistes: list[Observation]) -> dict[str, Any]:
    """Contrat 1, côté suivi : ce que Guillaume envoie pour une image."""
    return {"t": round(float(t), 3),
            "pistes": [{"id_piste": int(p.id_piste), "boite": [round(float(v), 1) for v in p.boite],
                        "confiance": round(float(p.confiance), 3)} for p in pistes]}


def lire_observations(message: dict[str, Any]) -> tuple[float, list[Observation]]:
    """Contrat 1, côté chaîne : vérifie le message et le convertit."""
    try:
        t = float(message["t"])
        pistes = []
        for piste in message["pistes"]:
            boite = tuple(float(v) for v in piste["boite"])
            if len(boite) != 4 or boite[2] < 0 or boite[3] < 0:
                raise ContratInvalide(f"boîte invalide : {piste['boite']}")
            pistes.append(Observation(int(piste["id_piste"]), boite, float(piste["confiance"])))
    except (KeyError, TypeError, ValueError) as erreur:
        if isinstance(erreur, ContratInvalide):
            raise
        raise ContratInvalide(f"observations hors contrat : {erreur!r}") from erreur
    return t, pistes


def message_alerte(t: float, fiche: FicheNavire, complete: bool, raison: str,
                   textes_lus: list[str] | None = None, deja_vu: dict[str, Any] | None = None) -> dict[str, Any]:
    """Alerte du contrat 3. Deux ajouts au contrat, présents seulement s'ils ne sont pas vides :
    `textes_lus`, ce qui a été lu sur la coque sans être une immatriculation française (nom, immatriculation
    étrangère) ; `deja_vu`, le navire déjà signalé que la ré-identification reconnaît (voir reidentification.py)."""
    message = {"genre": "alerte", "t": round(t, 2), "id_piste": fiche.id_piste, "complete": complete,
               "types": list(fiche.experts.types), "immatriculation": fiche.experts.immatriculation,
               "confiance_immatriculation": round(fiche.experts.confiance_immatriculation, 2), "raison": raison}
    if textes_lus:
        message["textes_lus"] = list(textes_lus)
    if deja_vu:
        message["deja_vu"] = dict(deja_vu)
    return message


def message_decision(t: float, id_piste: int, action: str, raison: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ContratInvalide(f"action hors contrat : {action}")
    return {"genre": "decision", "t": round(t, 2), "id_piste": id_piste, "action": action, "raison": raison}


def message_etat(t: float, mode: str, batterie: float, navires_suivis: int,
                 temperature_pi: float | None) -> dict[str, Any]:
    if mode not in MODES:
        raise ContratInvalide(f"mode hors contrat : {mode}")
    return {"genre": "etat", "t": round(t, 2), "mode": mode, "batterie": round(batterie, 2),
            "navires_suivis": navires_suivis,
            "temperature_pi": None if temperature_pi is None else round(temperature_pi, 1)}
