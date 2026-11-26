"""Boîte d'envoi SQLite : rien ne se perd quand la station est absente, refusée ou relancée."""
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from chaine.boite import EmetteurBoite, ENVOYE, EN_ATTENTE, REFUSE, REMPLACE
from chaine.messages import creer_emetteur

ALERTE = {"genre": "alerte", "t": 3.0, "id_piste": 1, "complete": True}
DECISION = {"genre": "decision", "t": 2.9, "id_piste": 1, "action": "alerte_complete", "raison": "lue"}


def etat(t: float) -> dict:
    return {"genre": "etat", "t": t, "mode": "patrouille", "batterie": 0.9, "navires_suivis": 0}


class Station:
    """Fausse station sol : garde les messages reçus, peut répondre autre chose que 204."""

    def __init__(self, port: int = 0, code: int = 204):
        self.recus: list[dict] = []
        self.code = code
        station = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def do_POST(self):
                corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if station.code < 400:
                    station.recus.append(corps)
                self.send_response(station.code)
                self.end_headers()
                if station.code >= 400:
                    self.wfile.write(b"refus")

            def log_message(self, *args):
                pass

        self.serveur = HTTPServer(("127.0.0.1", port), Gestionnaire)
        self.port = self.serveur.server_port
        self.url = f"http://127.0.0.1:{self.port}/messages"
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def arreter(self) -> None:
        self.serveur.shutdown()
        self.serveur.server_close()


def attendre(condition, delai_s: float = 5.0) -> bool:
    fin = time.perf_counter() + delai_s
    while time.perf_counter() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


def port_libre() -> int:
    with socket.socket() as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


def statuts(chemin: Path) -> list[int]:
    base = sqlite3.connect(chemin)
    try:
        return [ligne[0] for ligne in base.execute("SELECT statut FROM messages ORDER BY id")]
    finally:
        base.close()


class TestBoite(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.chemin = Path(self.dossier.name) / "sous" / "boite.db"

    def boite(self, url: str, **options) -> EmetteurBoite:
        options = {"lot_s": 0.05, "delai_s": 0.3, "attente_max_s": 0.2, **options}
        boite = EmetteurBoite(self.chemin, url, **options)
        self.addCleanup(lambda: boite._fil.is_alive() and boite.fermer(0.5))
        return boite

    def test_les_messages_arrivent_dans_l_ordre_et_sont_marques_envoyes(self):
        station = Station()
        self.addCleanup(station.arreter)
        boite = self.boite(station.url)
        for message in (DECISION, ALERTE):
            boite.envoyer(message)
        self.assertTrue(attendre(lambda: len(station.recus) == 2))
        boite.fermer()
        self.assertEqual(station.recus, [DECISION, ALERTE])
        self.assertEqual(statuts(self.chemin), [ENVOYE, ENVOYE])

    def test_station_absente_puis_revenue_rien_n_est_perdu(self):
        port = port_libre()
        boite = self.boite(f"http://127.0.0.1:{port}/messages")
        boite.envoyer(DECISION)
        boite.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: boite.echecs >= 1))
        self.assertEqual(boite.en_attente(), 2)

        station = Station(port)
        self.addCleanup(station.arreter)
        self.assertTrue(attendre(lambda: len(station.recus) == 2))
        boite.fermer()
        self.assertEqual(station.recus, [DECISION, ALERTE])
        self.assertEqual(boite.en_attente(), 0)

    def test_relance_du_programme_la_station_est_la(self):
        port = port_libre()
        premiere = self.boite(f"http://127.0.0.1:{port}/messages")
        premiere.envoyer(ALERTE)
        premiere.fermer(0.3)
        self.assertEqual(statuts(self.chemin), [EN_ATTENTE])

        station = Station(port)
        self.addCleanup(station.arreter)
        seconde = self.boite(station.url)
        self.assertTrue(attendre(lambda: station.recus == [ALERTE]))
        seconde.fermer()
        self.assertEqual(statuts(self.chemin), [ENVOYE])

    def test_les_alertes_et_decisions_passent_avant_les_etats(self):
        port = port_libre()
        boite = self.boite(f"http://127.0.0.1:{port}/messages", peremption_etat_s=1000)
        boite.envoyer(etat(1.0))
        boite.envoyer(etat(2.0))
        boite.envoyer(DECISION)
        boite.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: boite.echecs >= 1))
        station = Station(port)
        self.addCleanup(station.arreter)
        self.assertTrue(attendre(lambda: len(station.recus) == 4))
        boite.fermer()
        self.assertEqual([m["genre"] for m in station.recus], ["decision", "alerte", "etat", "etat"])

    def test_seul_le_dernier_etat_compte_pendant_une_coupure(self):
        port = port_libre()
        boite = self.boite(f"http://127.0.0.1:{port}/messages", peremption_etat_s=0.0)
        for t in range(5):
            boite.envoyer(etat(float(t)))
        boite.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: boite.echecs >= 1))
        station = Station(port)
        self.addCleanup(station.arreter)
        self.assertTrue(attendre(lambda: len(station.recus) == 2))
        boite.fermer()
        self.assertEqual(station.recus, [ALERTE, etat(4.0)])
        self.assertEqual(statuts(self.chemin).count(REMPLACE), 4)

    def test_un_refus_ne_bloque_pas_la_file(self):
        station = Station(code=400)
        self.addCleanup(station.arreter)
        boite = self.boite(station.url)
        boite.envoyer({"genre": "n_importe_quoi"})
        self.assertTrue(attendre(lambda: boite.refus == 1))
        station.code = 204
        boite.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: station.recus == [ALERTE]))
        boite.fermer()
        self.assertEqual(statuts(self.chemin), [REFUSE, ENVOYE])

    def test_une_erreur_serveur_ou_une_mauvaise_adresse_est_reessayee(self):
        station = Station(code=404)   # adresse mal tapée : le message ne doit pas être jeté
        self.addCleanup(station.arreter)
        boite = self.boite(station.url)
        boite.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: boite.echecs >= 1))
        station.code = 204
        self.assertTrue(attendre(lambda: station.recus == [ALERTE]))
        boite.fermer()

    def test_envoyer_ne_bloque_pas_la_chaine(self):
        boite = self.boite(f"http://127.0.0.1:{port_libre()}/messages", lot_s=5.0)
        debut = time.perf_counter()
        for t in range(2000):
            boite.envoyer(etat(float(t)))
        self.assertLess(time.perf_counter() - debut, 0.3)
        boite.fermer(0.3)
        self.assertGreater(boite.en_attente(), 0)

    def test_les_anciens_messages_traites_sont_purges(self):
        station = Station()
        self.addCleanup(station.arreter)
        premiere = self.boite(station.url)
        premiere.envoyer(ALERTE)
        self.assertTrue(attendre(lambda: station.recus == [ALERTE]))
        premiere.fermer()
        seconde = self.boite(station.url, conservation_s=0.0)
        seconde.fermer()
        self.assertEqual(statuts(self.chemin), [])

    def test_udp_et_adresses_non_http_refusees(self):
        with self.assertRaises(ValueError):
            EmetteurBoite(self.chemin, "udp://127.0.0.1:9000")

    def test_creer_emetteur_choisit_la_boite_pour_http_seulement(self):
        station = Station()
        self.addCleanup(station.arreter)
        emetteur = creer_emetteur(station.url, boite=self.chemin)
        self.assertIsInstance(emetteur, EmetteurBoite)
        emetteur.fermer()
        fichier = creer_emetteur(str(Path(self.dossier.name) / "m.jsonl"), boite=self.chemin)
        self.assertNotIsInstance(fichier, EmetteurBoite)
        fichier.fermer()


if __name__ == "__main__":
    unittest.main()
