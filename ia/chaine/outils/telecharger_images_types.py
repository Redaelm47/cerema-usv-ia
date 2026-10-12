"""Télécharge des photos de navires par type depuis Wikimedia Commons, pour entraîner la tête de l'expert type.

    python3 -m chaine.outils.telecharger_images_types --sortie ../data/types_commons --par-type 150

Les étiquettes viennent des catégories de Commons : elles sont bruitées. Les images restent hors du dépôt
(dossier data/) ; `sources.csv` garde le titre et la licence de chaque fichier.
"""
import argparse
import csv
import json
import time
import urllib.parse
from pathlib import Path

from .reseau import lire

API = "https://commons.wikimedia.org/w/api.php"

# type -> catégories de Commons parcourues avec leurs sous-catégories
CATEGORIES = {
    "peche": ["Trawlers", "Fishing boats of France", "Fishing vessels"],
    "voilier": ["Sailing yachts", "Sailboats"],
    "cargo": ["Container ships", "Bulk carriers", "General cargo ships"],
    "ferry": ["Ferries of France", "Ro-ro passenger ferries", "Ferries"],
    "vedette": ["Motor yachts", "Motorboats"],
    "pneumatique": ["Rigid-hulled inflatable boats", "Inflatable boats"],
}


def appeler(**parametres) -> dict:
    url = API + "?" + urllib.parse.urlencode({"format": "json", **parametres})
    return json.loads(lire(url))


def chercher(categorie: str, nombre: int, largeur: int) -> list[dict]:
    """Fichiers image d'une catégorie et de ses sous-catégories, avec l'adresse d'une vignette."""
    trouves, suite = [], {}
    while len(trouves) < nombre:
        reponse = appeler(action="query", generator="search", gsrnamespace=6, gsrlimit=50,
                          gsrsearch=f'deepcategory:"{categorie}" filetype:bitmap',
                          prop="imageinfo", iiprop="url|extmetadata|mime", iiurlwidth=largeur, **suite)
        for page in reponse.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") == "image/jpeg" and "thumburl" in info:
                meta = info.get("extmetadata", {})
                trouves.append({"titre": page["title"], "vignette": info["thumburl"],
                                "licence": meta.get("LicenseShortName", {}).get("value", ""),
                                "page": info.get("descriptionurl", "")})
        if "continue" not in reponse:
            break
        suite = reponse["continue"]
        time.sleep(0.5)
    return trouves[:nombre]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sortie", default="../data/types_commons")
    parser.add_argument("--par-type", type=int, default=150)
    parser.add_argument("--largeur", type=int, default=640)
    args = parser.parse_args()

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    with (sortie / "sources.csv").open("w", newline="", encoding="utf-8") as f:
        sources = csv.writer(f)
        sources.writerow(["type", "fichier", "titre", "licence", "page"])
        for type_navire, categories in CATEGORIES.items():
            dossier = sortie / type_navire
            dossier.mkdir(exist_ok=True)
            vus, numero = set(), 0
            for categorie in categories:
                if numero >= args.par_type:
                    break
                try:
                    fichiers = chercher(categorie, args.par_type, args.largeur)
                except Exception as erreur:
                    print(f"  {categorie} : {erreur}")
                    continue
                for fichier in fichiers:
                    if numero >= args.par_type or fichier["titre"] in vus:
                        continue
                    vus.add(fichier["titre"])
                    chemin = dossier / f"{numero:04d}.jpg"
                    try:
                        chemin.write_bytes(lire(fichier["vignette"]))
                    except Exception as erreur:
                        print(f"  {fichier['titre']} : {erreur}")
                        time.sleep(2.0)
                        continue
                    sources.writerow([type_navire, chemin.name, fichier["titre"], fichier["licence"], fichier["page"]])
                    numero += 1
                    time.sleep(0.2)
            print(f"{type_navire} : {numero} images", flush=True)


if __name__ == "__main__":
    main()
