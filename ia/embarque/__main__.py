"""Programme embarqué complet, celui qui tourne sur le Raspberry Pi.

    caméra et suivi (paquet `suivi`)  --contrat 1-->  décision et experts (paquet `chaine`)  --contrat 3-->  station sol

    python3 -m embarque --pi --station http://192.168.1.20:8000          sur le Pi, caméra IMX500
    python3 -m embarque --video ../data/scene-blender-01.mp4 --temps-reel --seuil-ocr 300 --station http://localhost:8000
    python3 -m embarque --camera 0 --toutes-classes                       webcam du Mac, essai sans navire

Les deux parties ne se parlent que par le contrat 1 : `Chaine.pas(observations, image)`, une fois par image.
"""
import argparse
import os

from chaine.__main__ import ajouter_options_reid, creer_reid, derouler
from chaine.experts import DroneSimule
from chaine.reglages import Reglages
from suivi.__main__ import ajouter_options, creer_suivi


def main() -> None:
    parser = argparse.ArgumentParser(description="Programme embarqué : suivi, décision, experts, messages")
    ajouter_options(parser)
    parser.add_argument("--station", metavar="URL", help="adresse de la station sol, par exemple http://192.168.1.20:8000")
    parser.add_argument("--seuil-ocr", type=float, metavar="PX",
                        help="largeur du navire à partir de laquelle on tente de lire (défaut : 600, ramené à la "
                             "largeur de l'image)")
    parser.add_argument("--sans-filtre-flou", action="store_true",
                        help="ne plus écarter les images floues avant les experts (essais sur écran ou projection)")
    parser.add_argument("--fils", type=int, help="nombre de fils d'ONNX Runtime (4 par défaut sur le Pi)")
    parser.add_argument("--observations", metavar="FICHIER", default="runs/observations.jsonl",
                        help="copie des observations du contrat 1")
    parser.add_argument("--journal", default="runs/journal.jsonl", help="journal des décisions")
    parser.add_argument("--messages", default="runs/messages.jsonl", help="copie des messages du contrat 3")
    parser.add_argument("--sortie", help="vidéo annotée à écrire (.mp4) ; à éviter sur le Pi")
    parser.add_argument("--afficher", action="store_true",
                        help="montrer les images annotées en direct (Q dans la fenêtre pour arrêter) ; pas sur le Pi")
    parser.add_argument("--direct", action="store_true",
                        help="écrit les images annotées (boîtes, type, immatriculation) sur la sortie standard, en "
                             "MJPEG, pour ffplay à travers ssh ; fermer ffplay arrête le programme")
    parser.add_argument("--boite", metavar="FICHIER",
                        help="boîte d'envoi SQLite vers la station (--station) : rien n'est perdu si la liaison coupe "
                             "ou si le programme est relancé ; conseillé en mer")
    ajouter_options_reid(parser)
    args = parser.parse_args()

    direct = None
    if args.direct:
        # La sortie standard ne porte plus que les images : tout le texte part vers l'erreur standard.
        direct = os.fdopen(os.dup(1), "wb")
        os.dup2(2, 1)

    reglages = Reglages()
    if args.seuil_ocr:
        reglages.seuil_ocr_px = args.seuil_ocr
    elif args.pi:
        # Le seuil par défaut est pensé pour l'image de 4056 px de large : on garde la même part de l'image.
        reglages.seuil_ocr_px *= int(args.resolution.split("x")[0]) / reglages.largeur_image_px
    if args.sans_filtre_flou:
        reglages.nettete_min = 0.0  # la variance du laplacien n'est jamais négative : plus aucun rejet pour flou
    messages = [args.messages]
    if args.station:
        messages.append(args.station.rstrip("/") + "/message")
    derouler(creer_suivi(args, enregistrer=args.observations), reglages, DroneSimule(), vrais_experts=True,
             fils=args.fils, journal=args.journal, messages=messages, sortie=args.sortie, direct=direct,
             reid=creer_reid(args, reglages), memoire_navires=args.memoire_navires,
             afficher_direct=args.afficher, boite=args.boite)


if __name__ == "__main__":
    main()
