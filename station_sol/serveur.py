"""Station sol : reçoit les messages du drone et les pousse en direct vers la page opérateur.

    python serveur.py              # puis ouvrir http://localhost:8000

Routes :
    POST /message        un objet JSON, ou plusieurs (un par ligne)
    POST /reinitialiser  vide l'historique
    GET  /flux           flux en direct pour la page (Server-Sent Events)
    GET  /               page opérateur
"""

import argparse
import json
import queue
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from contrat import verifier

DOSSIER = Path(__file__).resolve().parent
PAGE = DOSSIER / "page"
TYPES_FICHIERS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class Station:
    """Historique des messages et liste des pages abonnées au flux."""

    def __init__(self, journal):
        self.messages = []
        self.abonnes = []
        self.verrou = threading.Lock()
        self.journal = journal

    def ajouter(self, message):
        with self.verrou:
            self.messages.append(message)
            for abonne in self.abonnes:
                abonne.put(("message", message))
            if self.journal:
                with open(self.journal, "a", encoding="utf-8") as f:
                    f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def reinitialiser(self):
        with self.verrou:
            self.messages.clear()
            for abonne in self.abonnes:
                abonne.put(("reinit", None))

    def abonner(self):
        abonne = queue.Queue()
        with self.verrou:
            historique = list(self.messages)
            self.abonnes.append(abonne)
        return historique, abonne

    def desabonner(self, abonne):
        with self.verrou:
            self.abonnes.remove(abonne)


def lire_messages(corps):
    """Accepte un objet JSON seul ou plusieurs objets, un par ligne (JSON Lines)."""
    texte = corps.decode("utf-8").strip()
    try:
        return [json.loads(texte)]
    except json.JSONDecodeError:
        return [json.loads(ligne) for ligne in texte.splitlines() if ligne.strip()]


class Gestionnaire(BaseHTTPRequestHandler):
    station = None

    def log_message(self, format, *args):
        pass  # on n'affiche que les messages reçus et les erreurs

    def _repondre(self, code, contenu, type_contenu="application/json; charset=utf-8"):
        if isinstance(contenu, (dict, list)):
            contenu = json.dumps(contenu, ensure_ascii=False)
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        self.wfile.write(contenu)

    def do_POST(self):
        if self.path == "/reinitialiser":
            self.station.reinitialiser()
            print("historique vidé")
            return self._repondre(200, {"ok": True})
        if self.path != "/message":
            return self._repondre(404, {"erreur": "route inconnue"})

        corps = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            messages = lire_messages(corps)
        except (json.JSONDecodeError, UnicodeDecodeError) as erreur:
            print(f"refusé : JSON illisible ({erreur})")
            return self._repondre(400, {"erreur": f"JSON illisible : {erreur}"})

        # On vérifie tout avant d'ajouter quoi que ce soit : un lot est accepté ou refusé en entier.
        for numero, message in enumerate(messages):
            erreurs = verifier(message)
            if erreurs:
                print(f"refusé : {message} -> {'; '.join(erreurs)}")
                return self._repondre(400, {"erreur": "message hors contrat", "message": numero,
                                            "details": erreurs})
        for message in messages:
            self.station.ajouter(message)
            print(f"reçu   : {json.dumps(message, ensure_ascii=False)}")
        return self._repondre(200, {"recus": len(messages)})

    def do_GET(self):
        chemin = urlsplit(self.path).path
        if chemin == "/flux":
            return self._flux()
        nom = "index.html" if chemin == "/" else chemin.lstrip("/")
        fichier = (PAGE / nom).resolve()
        if fichier.parent != PAGE or not fichier.is_file() or fichier.suffix not in TYPES_FICHIERS:
            return self._repondre(404, {"erreur": "fichier introuvable"})
        self._repondre(200, fichier.read_bytes(), TYPES_FICHIERS[fichier.suffix])

    def _flux(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        historique, abonne = self.station.abonner()
        try:
            # À chaque (re)connexion, la page repart de zéro puis reçoit tout l'historique.
            self._evenement("reinit", None)
            for message in historique:
                self._evenement("message", message)
            while True:
                try:
                    self._evenement(*abonne.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # détecte une page fermée
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            self.station.desabonner(abonne)

    def _evenement(self, nom, donnees):
        texte = f"event: {nom}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"
        self.wfile.write(texte.encode("utf-8"))
        self.wfile.flush()


class ServeurDoublePile(ThreadingHTTPServer):
    """Écoute en IPv6 et en IPv4 : sinon « localhost » (résolu d'abord en ::1) perd 2 s par requête sous Windows."""

    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description="Station sol : serveur et page opérateur.")
    parser.add_argument("--hote", default="::",
                        help="adresse d'écoute (par défaut toutes : joignable depuis le Pi sur le même réseau)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--sans-journal", action="store_true",
                        help="ne pas enregistrer les messages reçus dans journaux/")
    args = parser.parse_args()

    journal = None
    if not args.sans_journal:
        (DOSSIER / "journaux").mkdir(exist_ok=True)
        journal = DOSSIER / "journaux" / f"messages_{datetime.now():%Y-%m-%d_%H-%M-%S}.jsonl"

    Gestionnaire.station = Station(journal)
    if ":" in args.hote:
        serveur = ServeurDoublePile((args.hote, args.port), Gestionnaire)
    else:
        serveur = ThreadingHTTPServer((args.hote, args.port), Gestionnaire)
        serveur.daemon_threads = True
    print(f"Station sol : http://localhost:{args.port}  (Ctrl+C pour arrêter)")
    if journal:
        print(f"Journal     : {journal}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\narrêt")


if __name__ == "__main__":
    main()
