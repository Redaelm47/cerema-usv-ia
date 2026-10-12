"""Rejoue un fichier de faux messages vers la station sol, au rythme de leur champ t.

    python rejouer.py                                    # scénario de démonstration
    python rejouer.py exemples/scenario_demo.jsonl --vitesse 4 --boucle
"""

import argparse
import json
import time
import urllib.error
from pathlib import Path

from client import URL_PAR_DEFAUT, envoyer, reinitialiser

SCENARIO = Path(__file__).resolve().parent / "exemples" / "scenario_demo.jsonl"


def charger(fichier):
    with open(fichier, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def rejouer(messages, url, vitesse):
    precedent = messages[0]["t"]
    for message in messages:
        time.sleep(max(0.0, message["t"] - precedent) / vitesse)
        precedent = message["t"]
        envoyer(message, url)
        print(f"t={message['t']:>6.1f}  {message['genre']:<8}  {message.get('id_piste', '')}")


def main():
    parser = argparse.ArgumentParser(description="Rejoue de faux messages vers la station sol.")
    parser.add_argument("fichier", nargs="?", default=SCENARIO, help="fichier JSON Lines à rejouer")
    parser.add_argument("--url", default=URL_PAR_DEFAUT)
    parser.add_argument("--vitesse", type=float, default=1.0, help="2 = deux fois plus vite")
    parser.add_argument("--boucle", action="store_true", help="recommencer à la fin")
    parser.add_argument("--garder", action="store_true", help="ne pas vider l'historique avant de rejouer")
    args = parser.parse_args()

    messages = charger(args.fichier)
    try:
        while True:
            if not args.garder:
                reinitialiser(args.url)
            rejouer(messages, args.url, args.vitesse)
            if not args.boucle:
                break
    except urllib.error.URLError:
        print(f"Station sol injoignable à {args.url} : lancer d'abord python serveur.py")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
