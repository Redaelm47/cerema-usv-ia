"""Contrat n°3 : messages envoyés par le décideur (Reda) à la station sol (Adam-Sabri).

Voir docs/repartition_travail.pdf. Un message est un objet JSON ; aucune image n'est envoyée.
"""

GENRES = ("alerte", "decision", "etat")
ACTIONS = ("expert_type", "expert_ocr", "approche", "alerte_complete", "alerte_partielle")
MODES = ("patrouille", "approche")

NOMBRE = "nombre"
ENTIER = "entier"
BOOLEEN = "booleen"
TEXTE = "texte"
LISTE_TEXTES = "liste de textes"

# Champs obligatoires de chaque genre. Un type entre parenthèses accepte aussi null.
CHAMPS = {
    "alerte": {
        "t": NOMBRE,
        "id_piste": ENTIER,
        "complete": BOOLEEN,
        "types": LISTE_TEXTES,
        "immatriculation": (TEXTE,),
        "confiance_immatriculation": (NOMBRE,),
        "raison": TEXTE,
    },
    "decision": {
        "t": NOMBRE,
        "id_piste": ENTIER,
        "action": TEXTE,
        "raison": TEXTE,
    },
    "etat": {
        "t": NOMBRE,
        "mode": TEXTE,
        "batterie": NOMBRE,
        "navires_suivis": ENTIER,
        "temperature_pi": (NOMBRE,),  # null ailleurs que sur le Pi
    },
}


def _du_bon_type(valeur, attendu):
    if isinstance(attendu, tuple):
        return valeur is None or _du_bon_type(valeur, attendu[0])
    if attendu == BOOLEEN:
        return isinstance(valeur, bool)
    if isinstance(valeur, bool):
        return False
    if attendu == NOMBRE:
        return isinstance(valeur, (int, float))
    if attendu == ENTIER:
        return isinstance(valeur, int)
    if attendu == TEXTE:
        return isinstance(valeur, str)
    if attendu == LISTE_TEXTES:
        return isinstance(valeur, list) and all(isinstance(v, str) for v in valeur)
    return False


def verifier(message):
    """Renvoie la liste des erreurs du message ; une liste vide veut dire qu'il respecte le contrat."""
    if not isinstance(message, dict):
        return ["le message doit être un objet JSON"]
    genre = message.get("genre")
    if genre not in GENRES:
        return [f"genre inconnu : {genre!r} (attendu : {', '.join(GENRES)})"]

    erreurs = []
    for champ, attendu in CHAMPS[genre].items():
        if champ not in message:
            erreurs.append(f"champ manquant : {champ}")
        elif not _du_bon_type(message[champ], attendu):
            nom = attendu[0] + " ou null" if isinstance(attendu, tuple) else attendu
            erreurs.append(f"{champ} doit être de type {nom}")

    if genre == "decision" and message.get("action") not in ACTIONS:
        erreurs.append(f"action inconnue : {message.get('action')!r} (attendu : {', '.join(ACTIONS)})")
    if genre == "etat" and message.get("mode") not in MODES:
        erreurs.append(f"mode inconnu : {message.get('mode')!r} (attendu : {', '.join(MODES)})")
    return erreurs
