"""Télécharge depuis Wikimedia Commons des photos de navires de pêche français dont le titre donne l'immatriculation.

    python3 -m chaine.outils.telecharger_photos_immatriculees --sortie ../data/immatriculations_commons

Le titre sert de vérité (« LR 539755 »). L'immatriculation n'est pas lisible sur toutes les photos (vues de
détail, navire lointain) : la colonne `visible` de `verites.csv` le dit, d'après un tri fait à l'œil.
`verites.csv` garde aussi le titre et la licence de chaque fichier.
"""
import argparse
import csv
import json
import re
import time
import urllib.parse
from pathlib import Path

from ..experts.immatriculation import QUARTIERS
from .reseau import lire

API = "https://commons.wikimedia.org/w/api.php"
RECHERCHE = 'deepcategory:"Fishing boats of France" intitle:/[A-Z][A-Z] ?[0-9][0-9][0-9][0-9][0-9][0-9]/'
# Photos où l'immatriculation du titre n'est pas lisible, repérées à l'œil le 08/10/2026 : série de détails
# du LOLA (coque décapée), vues lointaines du Prins Bernhard, épave vue de l'intérieur.
PAS_VISIBLE = re.compile(r"LOLA|Prins Bernhard IJmuiden|BL 264655 in Le Crotoy , pic[234]")
IMMATRICULATION = re.compile(r"(?<![A-Za-z])([A-Z]{2}) ?(\d{6})(?!\d)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sortie", default="../data/immatriculations_commons")
    parser.add_argument("--largeur", type=int, default=1600)
    parser.add_argument("--maximum", type=int, default=150)
    args = parser.parse_args()
    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    suite, numero = {}, 0
    with (sortie / "verites.csv").open("w", newline="", encoding="utf-8") as f:
        verites = csv.writer(f)
        verites.writerow(["fichier", "immatriculation", "visible", "titre", "licence", "page"])
        while numero < args.maximum:
            url = API + "?" + urllib.parse.urlencode({
                "format": "json", "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 50,
                "gsrsearch": RECHERCHE, "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
                "iiurlwidth": args.largeur, **suite})
            reponse = json.loads(lire(url))
            for page in reponse.get("query", {}).get("pages", {}).values():
                info = (page.get("imageinfo") or [{}])[0]
                trouve = IMMATRICULATION.search(page["title"])
                if not trouve or trouve.group(1) not in QUARTIERS or info.get("mime") != "image/jpeg":
                    continue
                chemin = sortie / f"{numero:04d}.jpg"
                try:
                    chemin.write_bytes(lire(info["thumburl"]))
                except Exception as erreur:
                    print(f"  {page['title']} : {erreur}")
                    time.sleep(2.0)
                    continue
                licence = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
                verites.writerow([chemin.name, f"{trouve.group(1)} {trouve.group(2)}",
                                  "non" if PAS_VISIBLE.search(page["title"]) else "oui", page["title"], licence,
                                  info.get("descriptionurl", "")])
                numero += 1
                time.sleep(0.2)
            if "continue" not in reponse:
                break
            suite = reponse["continue"]
    print(f"{numero} photos dans {sortie}")


if __name__ == "__main__":
    main()
