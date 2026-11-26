"""Envoi des messages du contrat 3 vers la station sol : un objet JSON par message.

L'adresse choisit le transport :
    runs/messages.jsonl            fichier, une ligne par message (pour vérifier sans serveur)
    http://hote:8000/messages      requête POST par message, corps JSON
    udp://hote:9000                un datagramme par message

L'envoi par le réseau passe par un fil à part : une station sol lente ou absente ne ralentit jamais la chaîne.
"""
import json
import queue
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse


class Emetteur(Protocol):
    def envoyer(self, message: dict[str, Any]) -> None: ...
    def fermer(self) -> None: ...


class EmetteurMemoire:
    """Garde les messages en mémoire (tests)."""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []

    def envoyer(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def fermer(self) -> None:
        pass


class EmetteurFichier:
    def __init__(self, chemin: str | Path):
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._fichier = chemin.open("w", encoding="utf-8")

    def envoyer(self, message: dict[str, Any]) -> None:
        self._fichier.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._fichier.flush()

    def fermer(self) -> None:
        self._fichier.close()


class EmetteurReseau:
    """File d'attente vidée par un fil à part. Si la file est pleine, le message est abandonné et compté."""

    def __init__(self, adresse: str, delai_s: float = 3.0, taille_file: int = 1000):
        self.adresse = adresse
        self.delai_s = delai_s
        self.envoyes = 0
        self.echecs = 0   # destinataire injoignable
        self.refus = 0    # destinataire joint, message refusé
        self._url = urlparse(adresse)
        if self._url.scheme not in ("http", "https", "udp"):
            raise ValueError(f"adresse non gérée : {adresse}")
        self._prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if self._url.scheme == "udp" else None
        self._file: queue.Queue = queue.Queue(maxsize=taille_file)
        self._fil = threading.Thread(target=self._vider, daemon=True)
        self._fil.start()

    def envoyer(self, message: dict[str, Any]) -> None:
        try:
            self._file.put_nowait(json.dumps(message, ensure_ascii=False).encode("utf-8"))
        except queue.Full:
            self.echecs += 1

    def _vider(self) -> None:
        while True:
            corps = self._file.get()
            if corps is None:
                return
            try:
                if self._prise is not None:
                    self._prise.sendto(corps, (self._url.hostname, self._url.port))
                else:
                    requete = urllib.request.Request(self.adresse, data=corps, method="POST",
                                                     headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(requete, timeout=self.delai_s).close()
                self.envoyes += 1
            except urllib.error.HTTPError as erreur:
                # Le destinataire a répondu, mais refuse le message (hors contrat, par exemple).
                self.refus += 1
                if self.refus == 1:
                    print(f"message refusé par {self.adresse} : {erreur.read().decode('utf-8', 'replace')[:300]}")
            except OSError:
                self.echecs += 1

    def fermer(self, attente_s: float = 3.0) -> None:
        self._file.put(None)
        self._fil.join(attente_s)
        if self._prise is not None:
            self._prise.close()
        if self.echecs or self.refus:
            print(f"{self.adresse} : {self.envoyes} message(s) reçu(s), {self.refus} refusé(s), "
                  f"{self.echecs} perdu(s) (destinataire injoignable)")


class Emetteurs:
    """Envoie chaque message à plusieurs destinataires."""

    def __init__(self, emetteurs: list[Emetteur]):
        self.emetteurs = emetteurs

    def envoyer(self, message: dict[str, Any]) -> None:
        for emetteur in self.emetteurs:
            emetteur.envoyer(message)

    def fermer(self) -> None:
        for emetteur in self.emetteurs:
            emetteur.fermer()


def creer_emetteur(adresse: str, boite: str | Path | None = None) -> Emetteur:
    """`boite` : fichier SQLite de la boîte d'envoi (`boite.py`), utilisée pour les adresses http(s) seulement."""
    if boite and adresse.startswith(("http://", "https://")):
        from .boite import EmetteurBoite
        return EmetteurBoite(boite, adresse)
    if "://" in adresse:
        return EmetteurReseau(adresse)
    return EmetteurFichier(adresse)
