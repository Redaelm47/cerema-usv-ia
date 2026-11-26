"""Téléchargements pour les outils (jamais utilisé par la chaîne elle-même, qui tourne hors ligne)."""
import ssl
import urllib.request

AGENT = "cerema-usv-ia/0.1 (projet etudiant IMT Atlantique ; reda.elmekkaoui.47@gmail.com)"


def _contexte() -> ssl.SSLContext:
    try:  # le Python de python.org sur macOS n'a pas les certificats du système
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def lire(url: str, delai_s: float = 60.0) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=delai_s, context=_contexte()) as reponse:
        return reponse.read()
