"""Mesure le taux de lecture de l'expert OCR sur des immatriculations synthétiques, par hauteur de caractères.

    python3 -m chaine.outils.mesurer_ocr --navires 60 --rapport runs/mesure_ocr.json
    python3 -m chaine.outils.mesurer_ocr --photos ../data/immatriculations_commons

Pour chaque navire synthétique, l'expert reçoit jusqu'à `max_tentatives_ocr` images différentes de la même
immatriculation, comme dans la chaîne. On compte :
- lecture sur une image : la première image donne l'immatriculation exacte ;
- fausse lecture sur une image : elle donne une autre immatriculation au bon format ;
- vote juste, vote faux, vote sans résultat : ce que la chaîne mettrait dans l'alerte.
"""
import argparse
import csv
import json
import random
import statistics
from pathlib import Path

from ..experts.immatriculation import Vote
from ..experts.ocr import ExpertOCR
from ..reglages import Reglages
from .immatriculations_synthetiques import dessiner, immatriculation_au_hasard


def mesurer(navires: int, hauteurs: list[int], graine: int = 0, fils: int | None = None,
            degradation: float = 1.0) -> dict:
    reglages = Reglages()
    expert = ExpertOCR(reglages, fils=fils)
    rng = random.Random(graine)
    lignes, durees = [], {"detection": [], "lecture": []}
    for hauteur in hauteurs:
        c = {"hauteur_px": hauteur, "navires": navires, "lue_1_image": 0, "fausse_1_image": 0,
             "vote_juste": 0, "vote_faux": 0, "vote_sans_resultat": 0, "images_par_vote": []}
        for _ in range(navires):
            verite = immatriculation_au_hasard(rng)
            vote = Vote()
            for essai in range(reglages.max_tentatives_ocr):
                lue, confiance, _ = expert.lire_immatriculation(dessiner(verite, hauteur, rng, degradation))
                for etape, duree in expert.lecteur.durees_ms.items():
                    durees[etape].append(duree)
                if essai == 0:
                    c["lue_1_image"] += lue == verite
                    c["fausse_1_image"] += lue is not None and lue != verite
                if lue is not None:
                    vote.ajouter(lue, confiance)
                candidate, _, validee = vote.resultat(reglages.lectures_pour_valider, reglages.part_min_vote)
                if validee:
                    c["vote_juste" if candidate == verite else "vote_faux"] += 1
                    c["images_par_vote"].append(essai + 1)
                    break
            else:
                c["vote_sans_resultat"] += 1
        c["images_par_vote"] = round(statistics.mean(c["images_par_vote"]), 2) if c["images_par_vote"] else None
        lignes.append(c)
        print(f"caractères de {hauteur:3d} px : lue sur 1 image {c['lue_1_image'] / navires:5.0%}, fausse "
              f"{c['fausse_1_image'] / navires:4.0%} | vote juste {c['vote_juste'] / navires:5.0%}, faux "
              f"{c['vote_faux'] / navires:4.0%}, sans résultat {c['vote_sans_resultat'] / navires:4.0%}, "
              f"images par vote {c['images_par_vote']}", flush=True)
    temps = {etape: {"mediane_ms": round(statistics.median(v), 1), "max_ms": round(max(v), 1)}
             for etape, v in durees.items()}
    print("temps par image :", temps)
    return {"par_hauteur": lignes, "temps": temps, "image": "1000 x 360 px, synthétique",
            "degradation": degradation}


def mesurer_photos(dossier: Path, cotes_max: list[int], fils: int | None = None) -> list[dict]:
    """Taux de lecture sur des photos réelles (une image par navire, donc sans vote), par taille d'analyse."""
    import cv2
    expert = ExpertOCR(Reglages(), fils=fils)
    with (dossier / "verites.csv").open(encoding="utf-8") as f:
        photos = list(csv.DictReader(f))
    lignes = []
    for cote_max in cotes_max:
        expert.lecteur.cote_max = cote_max
        c = {"cote_max_px": cote_max, "visibles": 0, "lues": 0, "autre_immatriculation": 0, "non_visibles": 0,
             "lectures_sur_non_visibles": 0}
        durees = []
        for photo in photos:
            lue, _, _ = expert.lire_immatriculation(cv2.imread(str(dossier / photo["fichier"])))
            durees.append(sum(expert.lecteur.durees_ms.values()))
            if photo["visible"] == "oui":
                c["visibles"] += 1
                c["lues"] += lue == photo["immatriculation"]
                c["autre_immatriculation"] += lue is not None and lue != photo["immatriculation"]
            else:
                c["non_visibles"] += 1
                c["lectures_sur_non_visibles"] += lue is not None
        c["mediane_ms"] = round(statistics.median(durees), 1)
        lignes.append(c)
        print(f"analyse à {cote_max} px : {c['lues']}/{c['visibles']} immatriculations visibles lues "
              f"({c['lues'] / max(c['visibles'], 1):.0%}), {c['autre_immatriculation']} autre(s) immatriculation(s) lue(s), "
              f"{c['lectures_sur_non_visibles']}/{c['non_visibles']} lecture(s) sur photos sans immatriculation visible, "
              f"{c['mediane_ms']} ms par photo", flush=True)
    return lignes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--navires", type=int, default=60, help="navires par hauteur de caractères")
    parser.add_argument("--hauteurs", type=int, nargs="+", default=[6, 8, 10, 12, 16, 20, 28, 40])
    parser.add_argument("--fils", type=int, help="nombre de fils d'ONNX Runtime (4 sur le Pi)")
    parser.add_argument("--degradation", type=float, default=1.0, help="1 = dégradations normales, 2 = doublées")
    parser.add_argument("--photos", help="dossier de photos réelles avec verites.csv "
                                         "(voir telecharger_photos_immatriculees)")
    parser.add_argument("--cotes-max", type=int, nargs="+", default=[1280, 1920],
                        help="avec --photos : tailles d'analyse à comparer")
    parser.add_argument("--rapport", help="fichier JSON où écrire les chiffres")
    args = parser.parse_args()
    rapport = mesurer(args.navires, args.hauteurs, fils=args.fils, degradation=args.degradation)
    if args.photos:
        rapport["photos_reelles"] = mesurer_photos(Path(args.photos), args.cotes_max, args.fils)
    if args.rapport:
        Path(args.rapport).parent.mkdir(parents=True, exist_ok=True)
        Path(args.rapport).write_text(json.dumps(rapport, ensure_ascii=False, indent=2))
