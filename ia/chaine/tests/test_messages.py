import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from chaine.messages import EmetteurFichier, EmetteurReseau, Emetteurs, EmetteurMemoire, creer_emetteur

MESSAGE = {"genre": "decision", "t": 0.6, "id_piste": 7, "action": "approche", "raison": "navire trop petit pour lire"}


class TestFichier(unittest.TestCase):
    def test_une_ligne_json_par_message(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "sous" / "messages.jsonl"
            emetteur = creer_emetteur(str(chemin))
            self.assertIsInstance(emetteur, EmetteurFichier)
            emetteur.envoyer(MESSAGE)
            emetteur.envoyer({"genre": "etat", "t": 1.0})
            emetteur.fermer()
            lignes = chemin.read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(l) for l in lignes], [MESSAGE, {"genre": "etat", "t": 1.0}])


class TestReseau(unittest.TestCase):
    def test_http_un_post_par_message(self):
        recus = []

        class Station(BaseHTTPRequestHandler):
            def do_POST(self):
                corps = self.rfile.read(int(self.headers["Content-Length"]))
                recus.append((self.path, self.headers["Content-Type"], json.loads(corps)))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        serveur = HTTPServer(("127.0.0.1", 0), Station)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        try:
            emetteur = creer_emetteur(f"http://127.0.0.1:{serveur.server_port}/messages")
            emetteur.envoyer(MESSAGE)
            emetteur.envoyer(MESSAGE)
            emetteur.fermer()
            self.assertEqual(recus, [("/messages", "application/json", MESSAGE)] * 2)
            self.assertEqual((emetteur.envoyes, emetteur.echecs), (2, 0))
        finally:
            serveur.shutdown()
            serveur.server_close()

    def test_udp_un_datagramme_par_message(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prise:
            prise.bind(("127.0.0.1", 0))
            prise.settimeout(2.0)
            emetteur = creer_emetteur(f"udp://127.0.0.1:{prise.getsockname()[1]}")
            emetteur.envoyer(MESSAGE)
            self.assertEqual(json.loads(prise.recv(65535)), MESSAGE)
            emetteur.fermer()

    def test_station_absente_ne_bloque_pas_la_chaine(self):
        with socket.socket() as prise:   # port libre, sur lequel personne n'écoute
            prise.bind(("127.0.0.1", 0))
            port = prise.getsockname()[1]
        emetteur = EmetteurReseau(f"http://127.0.0.1:{port}/messages", delai_s=0.2)
        debut = time.perf_counter()
        for _ in range(50):
            emetteur.envoyer(MESSAGE)
        self.assertLess(time.perf_counter() - debut, 0.1)
        emetteur.fermer()
        self.assertEqual((emetteur.envoyes, emetteur.echecs), (0, 50))

    def test_adresse_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            creer_emetteur("ftp://exemple/messages")

    def test_plusieurs_destinataires(self):
        a, b = EmetteurMemoire(), EmetteurMemoire()
        emetteurs = Emetteurs([a, b])
        emetteurs.envoyer(MESSAGE)
        emetteurs.fermer()
        self.assertEqual((a.messages, b.messages), ([MESSAGE], [MESSAGE]))


if __name__ == "__main__":
    unittest.main()
