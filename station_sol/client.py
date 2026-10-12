"""Envoi d'un message à la station sol, à importer côté drone (décideur).

    from client import envoyer
    envoyer({"genre": "etat", "t": 48.0, "mode": "patrouille", "batterie": 0.82,
             "navires_suivis": 2, "temperature_pi": 61.5}, url="http://<ip-du-mac>:8000")
"""

import json
import urllib.error
import urllib.request

URL_PAR_DEFAUT = "http://localhost:8000"


def _poster(url, corps=b""):
    requete = urllib.request.Request(url, data=corps, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=2) as reponse:
            return json.load(reponse)
    except urllib.error.HTTPError as erreur:
        raise ValueError(erreur.read().decode("utf-8")) from None


def envoyer(message, url=URL_PAR_DEFAUT):
    """Envoie un message (dict). Lève ValueError si la station sol le refuse."""
    return _poster(url.rstrip("/") + "/message", json.dumps(message).encode("utf-8"))


def reinitialiser(url=URL_PAR_DEFAUT):
    """Vide l'historique de la station sol et la page opérateur."""
    return _poster(url.rstrip("/") + "/reinitialiser")
