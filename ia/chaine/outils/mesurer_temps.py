"""Mesure le temps de chaque expert sur cette machine, pour plusieurs tailles de recadrage.

    python3 -m chaine.outils.mesurer_temps --fils 4 --rapport runs/mesure_temps.json

À relancer tel quel sur le Raspberry Pi : les chiffres d'un ordinateur ne s'y transposent pas.
Le recadrage est une image synthétique de navire avec immatriculation, agrandie à la taille voulue.
"""
import argparse
import json
import platform
import random
import resource
import statistics
import sys
import time
from pathlib import Path

import cv2

from ..experts.ocr import ExpertOCR
from ..experts.qualite import FiltreQualite
from ..experts.type import ExpertType
from ..fiche import FicheNavire, Observation
from ..reglages import Reglages
from .immatriculations_synthetiques import dessiner

LARGEURS = (300, 600, 1000, 2000)  # largeur du navire dans l'image, en pixels


def memoire_mo() -> float:
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maximum / (1e6 if sys.platform == "darwin" else 1e3)  # octets sur macOS, kilo-octets sur Linux


def chronometrer(fonction, repetitions: int) -> dict:
    fonction()  # premier appel écarté : il inclut des initialisations
    durees = []
    for _ in range(repetitions):
        debut = time.perf_counter()
        fonction()
        durees.append((time.perf_counter() - debut) * 1000)
    return {"mediane_ms": round(statistics.median(durees), 1), "max_ms": round(max(durees), 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fils", type=int, help="nombre de fils d'ONNX Runtime (4 = autant que de cœurs sur le Pi 4)")
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--rapport", help="fichier JSON où écrire les chiffres")
    args = parser.parse_args()

    reglages = Reglages()
    rapport = {"machine": f"{platform.machine()} {platform.processor() or platform.platform()}", "fils": args.fils,
               "chargement_ms": {}, "experts": {}}
    experts = {}
    for nom, fabrique in (("qualite", lambda: FiltreQualite(reglages)), ("type", lambda: ExpertType(fils=args.fils)),
                          ("ocr", lambda: ExpertOCR(reglages, fils=args.fils))):
        debut = time.perf_counter()
        experts[nom] = fabrique()
        rapport["chargement_ms"][nom] = round((time.perf_counter() - debut) * 1000)
    rapport["memoire_max_mo_apres_chargement"] = round(memoire_mo())

    modele = dessiner("GV 642410", 28, random.Random(0), degradation=0.5)
    for largeur in LARGEURS:
        image = cv2.resize(modele, (largeur, int(largeur * modele.shape[0] / modele.shape[1])))
        fiche = FicheNavire.creer(1, 0.0)
        fiche.observer(0.0, Observation(1, (0.0, 0.0, float(image.shape[1]), float(image.shape[0])), 0.9))
        for nom, expert in experts.items():
            mesure = chronometrer(lambda: expert.lancer(fiche, image), args.repetitions)
            rapport["experts"].setdefault(nom, {})[f"{largeur} px"] = mesure
            print(f"{nom:<8} navire de {largeur:4d} px : médiane {mesure['mediane_ms']:7.1f} ms, "
                  f"max {mesure['max_ms']:7.1f} ms", flush=True)
    rapport["memoire_max_mo"] = round(memoire_mo())
    print(f"chargement : {rapport['chargement_ms']} ms, mémoire maximale {rapport['memoire_max_mo']} Mo")
    if args.rapport:
        Path(args.rapport).parent.mkdir(parents=True, exist_ok=True)
        Path(args.rapport).write_text(json.dumps(rapport, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
