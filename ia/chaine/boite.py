"""Boîte d'envoi : les messages du contrat 3 passent par une base SQLite à bord avant de partir vers la station.

Pourquoi : `EmetteurReseau` abandonne un message quand la station est injoignable. En mer, la liaison coupe ; avec la
boîte, rien ne se perd : le message reste dans le fichier jusqu'à ce que la station l'accuse (réponse 2xx), même si le
programme est relancé entre-temps. La station et les messages ne changent pas : c'est le même POST.

Ce que la boîte fait :
- `envoyer` ne touche jamais le disque : le message va dans une liste en mémoire, un fil à part l'écrit par lots
  (toutes les `lot_s` secondes, tout de suite pour une alerte), ce qui épargne la carte SD ou le SSD ;
- les alertes et décisions partent d'abord, dans l'ordre, les `etat` ensuite ;
- pendant une coupure, seul le dernier `etat` compte : les `etat` de plus de `peremption_etat_s` secondes qui ont été
  remplacés par un plus récent ne sont jamais envoyés ;
- un refus de la station (réponse 400 ou 422 : message hors contrat) est noté une fois et ne bloque pas la file ;
- un destinataire injoignable ou une autre erreur (404 d'une adresse mal tapée, 5xx...) garde le message et fait attendre 1 s, puis 2, 4... jusqu'à `attente_max_s` ;
- au démarrage, ce qui reste d'une mission précédente est envoyé en premier ; les messages déjà traités sont purgés
  après `conservation_s` (7 jours).

Ce qu'elle ne fait pas : le datagramme UDP (aucun accusé de réception, donc rien à garantir), ni la compression.
Un arrêt brutal (batterie, plantage) peut perdre les messages des `lot_s` dernières secondes, sauf les alertes.
"""
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EN_ATTENTE, ENVOYE, REFUSE, REMPLACE = 0, 1, 2, 3
# Seules ces réponses disent « ce message est hors contrat » : il est écarté. Toute autre erreur (404 d'une adresse
# mal tapée, 401, 429, 5xx...) peut se réparer côté station : le message est gardé et réessayé.
REFUS_DEFINITIFS = (400, 422)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL,
    cree_le REAL NOT NULL,
    genre TEXT NOT NULL,
    corps TEXT NOT NULL,
    statut INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_a_envoyer ON messages (destination, statut, id);
"""


class EmetteurBoite:
    def __init__(self, chemin: str | Path, adresse: str, delai_s: float = 3.0, lot_s: float = 2.0,
                 attente_max_s: float = 30.0, peremption_etat_s: float = 30.0,
                 conservation_s: float = 7 * 86400.0):
        self.adresse = adresse
        self.delai_s, self.lot_s = delai_s, lot_s
        self.attente_max_s, self.peremption_etat_s = attente_max_s, peremption_etat_s
        self.envoyes = self.refus = self.echecs = 0   # depuis l'ouverture ; echecs : tentatives sans réponse
        if urlparse(adresse).scheme not in ("http", "https"):
            raise ValueError(f"la boîte d'envoi ne gère que http et https, pas {adresse}")
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._base = sqlite3.connect(chemin, check_same_thread=False)
        self._base.execute("PRAGMA journal_mode=WAL")
        self._base.execute("PRAGMA synchronous=NORMAL")
        self._base.executescript(SCHEMA)
        self._base.execute("DELETE FROM messages WHERE destination = ? AND statut != ? AND cree_le < ?",
                           (adresse, EN_ATTENTE, time.time() - conservation_s))
        self._base.commit()
        self._verrou = threading.Lock()         # la base
        self._verrou_liste = threading.Lock()   # la liste en mémoire : `envoyer` n'attend jamais le disque
        self._nouveaux: list[tuple[float, str, str]] = []
        self._reveil = threading.Event()
        self._restant: int | None = None   # renseigné à la fermeture
        self._fermeture = threading.Event()
        self._attente_fermeture_s = 3.0
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def envoyer(self, message: dict[str, Any]) -> None:
        ligne = (time.time(), str(message.get("genre", "")), json.dumps(message, ensure_ascii=False))
        with self._verrou_liste:
            self._nouveaux.append(ligne)
        if ligne[1] == "alerte":
            self._reveil.set()

    def en_attente(self) -> int:
        """Nombre de messages écrits et pas encore accusés par la station (après `fermer` : ce qui reste dans le fichier)."""
        if self._restant is not None:
            return self._restant
        with self._verrou:
            return self._base.execute("SELECT COUNT(*) FROM messages WHERE destination = ? AND statut = ?",
                                      (self.adresse, EN_ATTENTE)).fetchone()[0]

    def _ecrire_lot(self) -> None:
        with self._verrou_liste:
            lot, self._nouveaux = self._nouveaux, []
        with self._verrou:
            if lot:
                self._base.executemany(
                    "INSERT INTO messages (destination, cree_le, genre, corps) VALUES (?, ?, ?, ?)",
                    [(self.adresse, cree_le, genre, corps) for cree_le, genre, corps in lot])
            # seul le dernier état compte : les plus vieux, déjà périmés, ne partiront pas
            self._base.execute(
                "UPDATE messages SET statut = ? WHERE destination = ? AND statut = ? AND genre = 'etat' AND cree_le < ? "
                "AND id < (SELECT MAX(id) FROM messages WHERE destination = ? AND genre = 'etat')",
                (REMPLACE, self.adresse, EN_ATTENTE, time.time() - self.peremption_etat_s, self.adresse))
            self._base.commit()

    def _prochains(self, n: int = 50) -> list[tuple[int, str]]:
        with self._verrou:
            return self._base.execute(
                "SELECT id, corps FROM messages WHERE destination = ? AND statut = ? "
                "ORDER BY genre = 'etat', id LIMIT ?", (self.adresse, EN_ATTENTE, n)).fetchall()

    def _noter(self, id_message: int, statut: int) -> None:
        with self._verrou:
            self._base.execute("UPDATE messages SET statut = ? WHERE id = ?", (statut, id_message))
            self._base.commit()

    def _poster(self, corps: str) -> bool | None:
        """True : accusé. False : refusé (400 ou 422). None : pas de réponse utile, à réessayer."""
        requete = urllib.request.Request(self.adresse, data=corps.encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(requete, timeout=self.delai_s).close()
            return True
        except urllib.error.HTTPError as erreur:
            if erreur.code in REFUS_DEFINITIFS:
                if self.refus == 0:
                    print(f"message refusé par {self.adresse} : {erreur.read().decode('utf-8', 'replace')[:300]}")
                return False
            return None
        except OSError:
            return None

    def _vider(self, echeance: float | None = None) -> bool:
        """Envoie ce qui attend. Rend False dès qu'une tentative échoue (destinataire injoignable)."""
        while echeance is None or time.perf_counter() < echeance:
            lot = self._prochains()
            if not lot:
                return True
            for id_message, corps in lot:
                resultat = self._poster(corps)
                if resultat is None:
                    self.echecs += 1
                    return False
                self._noter(id_message, ENVOYE if resultat else REFUSE)
                if resultat:
                    self.envoyes += 1
                else:
                    self.refus += 1
        return False

    def _boucle(self) -> None:
        attente = 1.0
        while not self._fermeture.is_set():
            self._ecrire_lot()
            if self._vider():
                attente = 1.0
                pause = self.lot_s
            else:
                pause = attente
                attente = min(attente * 2, self.attente_max_s)
            self._reveil.wait(pause)
            self._reveil.clear()
        self._ecrire_lot()   # dernier passage : tout ce qui reste est écrit, puis un dernier essai d'envoi
        self._vider(time.perf_counter() + self._attente_fermeture_s)

    def fermer(self, attente_s: float = 3.0) -> None:
        """Écrit ce qui reste, tente un dernier envoi pendant `attente_s` au plus, puis ferme la base."""
        self._attente_fermeture_s = attente_s
        self._fermeture.set()
        self._reveil.set()
        self._fil.join(attente_s + self.delai_s + 1.0)
        restant = self.en_attente()
        with self._verrou:
            self._base.close()
        self._restant = restant
        if restant or self.refus:
            suite = f", {restant} gardé(s) dans la boîte pour le prochain démarrage" if restant else ""
            print(f"{self.adresse} : {self.envoyes} message(s) reçu(s), {self.refus} refusé(s){suite}")
