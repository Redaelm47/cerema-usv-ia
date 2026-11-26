"""Lance la chaîne sur le scénario simulé ou sur une vidéo.

    python3 -m chaine                                   scénario simulé, experts factices, sans dépendance
    python3 -m chaine --video ../data/bateau.webm       vidéo, vrais experts, suivi de remplacement (ultralytics)
    python3 -m chaine --video v.mp4 --sortie runs/annotee.mp4 --messages http://127.0.0.1:8000/messages
"""
import argparse
import os
import sys
import time
from collections import defaultdict

from .chaine import Chaine
from .experts import DroneSimule, ExpertApprocheSimulee, ExpertOCRFactice, ExpertTypeFactice
from .journal import Journal
from .messages import Emetteurs, creer_emetteur
from .reglages import Reglages
from .sources import ScenarioSimule, SourceRejouee, SourceVideo


def main() -> None:
    parser = argparse.ArgumentParser(description="Chaîne de vision embarquée : décision et experts")
    parser.add_argument("--video", help="chemin d'une vidéo ; sans cette option, scénario simulé")
    parser.add_argument("--observations", help="avec --video : observations du contrat 1 déjà enregistrées (.jsonl), "
                                               "rejouées à la place de la détection et du suivi")
    parser.add_argument("--enregistrer-observations", metavar="FICHIER",
                        help="avec --video : écrit les observations du contrat 1, une ligne JSON par image")
    parser.add_argument("--factices", action="store_true", help="experts factices même sur une vidéo")
    parser.add_argument("--seuil-ocr", type=float, help="largeur en pixels à partir de laquelle on tente de lire")
    parser.add_argument("--vitesse-approche", type=float, default=3.0, help="vitesse du drone simulé, en m/s")
    parser.add_argument("--sans-zoom", action="store_true", help="avec --video : l'approche simulée ne zoome pas")
    parser.add_argument("--largeur-vue", type=int, metavar="PX",
                        help="avec --video : largeur de l'image fournie à la chaîne ; plus petite que la vidéo, "
                             "le zoom de l'approche apporte du vrai détail")
    parser.add_argument("--reseau-type", choices=("dinov2", "dinov3"), default="dinov2",
                        help="réseau figé de l'expert type")
    parser.add_argument("--taille-detection", type=int, default=640, metavar="PX",
                        help="avec --video : côté de l'image vue par le détecteur du suivi de remplacement")
    parser.add_argument("--fils", type=int, help="nombre de fils d'ONNX Runtime")
    ajouter_options_reid(parser)
    parser.add_argument("--sortie", help="avec --video : chemin de la vidéo annotée à écrire (.mp4)")
    parser.add_argument("--afficher", action="store_true",
                        help="avec --video : montrer les images annotées en direct (Q dans la fenêtre pour arrêter)")
    parser.add_argument("--journal", default="runs/journal.jsonl", help="fichier du journal des décisions")
    parser.add_argument("--messages", action="append", metavar="ADRESSE",
                        help="où envoyer les messages du contrat 3 : fichier .jsonl, http://hôte:port/chemin ou "
                             "udp://hôte:port ; option répétable (défaut : runs/messages.jsonl)")
    parser.add_argument("--boite", metavar="FICHIER",
                        help="boîte d'envoi SQLite : les messages vers http(s) y attendent l'accusé de la station "
                             "(liaison coupée, relance du programme) au lieu d'être perdus ; voir boite.py")
    args = parser.parse_args()

    reglages = Reglages()
    if args.seuil_ocr:
        reglages.seuil_ocr_px = args.seuil_ocr
    drone = DroneSimule(vitesse_m_s=args.vitesse_approche)

    if args.video and args.observations:
        source = SourceRejouee(args.video, args.observations)
    elif args.video:
        source = SourceVideo(args.video, drone=None if args.sans_zoom else drone,
                             enregistrer=args.enregistrer_observations, largeur_vue=args.largeur_vue,
                             taille_detection=args.taille_detection)
    else:
        source = ScenarioSimule(drone)

    derouler(source, reglages, drone, vrais_experts=bool(args.video) and not args.factices, fils=args.fils,
             reseau_type=args.reseau_type, journal=args.journal, messages=args.messages or ["runs/messages.jsonl"], boite=args.boite,
             sortie=args.sortie if args.video else None, reid=creer_reid(args, reglages), memoire_navires=args.memoire_navires,
             afficher_direct=args.afficher and bool(args.video))


def ajouter_options_reid(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reid", action="store_true",
                        help="ré-identification : reconnaître un navire déjà signalé (champ deja_vu des alertes)")
    parser.add_argument("--memoire-navires", metavar="CHEMIN",
                        help="ré-identification gardée d'une mission à l'autre : relue au départ si elle existe, "
                             "écrite à la fin (CHEMIN.json et CHEMIN.npz) ; implique --reid")
    parser.add_argument("--reid-reapprocher", action="store_true",
                        help="approcher quand même un navire reconnu avec certitude et déjà identifié")


def creer_reid(args: argparse.Namespace, reglages: Reglages):
    """Mémoire des navires selon les options : None sans --reid ni --memoire-navires."""
    reglages.reid_eviter_reapproche = not args.reid_reapprocher
    if not (args.reid or args.memoire_navires):
        return None
    from .reidentification import MemoireNavires  # NumPy seulement si demandé
    if args.memoire_navires:
        from pathlib import Path
        chemin = Path(args.memoire_navires)
        if chemin.with_suffix(".json").exists():
            memoire = MemoireNavires.charger(chemin)
            print(f"mémoire des navires relue : {len(memoire.navires)} navire(s) déjà connus")
            return memoire
    return MemoireNavires()


def derouler(source, reglages: Reglages, drone: DroneSimule, vrais_experts: bool, fils: int | None = None,
             reseau_type: str = "dinov2", journal: str = "runs/journal.jsonl", messages: list[str] | None = None,
             sortie: str | None = None, reid=None,
             memoire_navires: str | None = None, afficher_direct: bool = False, direct=None,
             boite: str | None = None) -> Chaine:
    """Fait tourner la chaîne sur une source d'observations (contrat 1) jusqu'à son épuisement.

    `reid` : mémoire des navires (ré-identification), sauvée dans `memoire_navires` à la fin si donné.
    Avec les experts factices, aucune signature n'est calculée : la ré-identification ne voit rien.
    `boite` : fichier SQLite de la boîte d'envoi pour les messages vers http(s).
    `afficher_direct` : fenêtre OpenCV (ordinateur). `direct` : flux binaire où écrire les images annotées
    en JPEG ; sa fermeture par le lecteur arrête la chaîne.
    """
    messages = messages or ["runs/messages.jsonl"]
    experts = [ExpertApprocheSimulee(drone, reglages)]
    if vrais_experts:
        # Importés ici : ONNX Runtime et OpenCV ne sont demandés que pour les vrais experts.
        from .experts.ocr import ExpertOCR
        from .experts.qualite import FiltreQualite
        from .experts.type import ExpertType
        experts += [FiltreQualite(reglages), ExpertType(fils=fils, reseau=reseau_type), ExpertOCR(reglages, fils=fils)]
    else:
        experts += [ExpertTypeFactice(), ExpertOCRFactice(reglages)]

    chemin_journal, journal = journal, Journal(journal)
    emetteur = Emetteurs([creer_emetteur(adresse, boite) for adresse in messages])
    chaine = Chaine(experts, reglages, journal, emetteur, drone, reid=reid)
    video_annotee = fenetre = None
    if sortie:
        from .affichage import VideoAnnotee
        video_annotee = VideoAnnotee(sortie, source.images_par_s)
    if afficher_direct:
        from .affichage import FenetreDirecte
        fenetre = FenetreDirecte()
    vue_directe = None
    if direct is not None:
        from .affichage import FluxAnnote
        vue_directe = FluxAnnote(direct)

    deja_affiche, images, t, debut = 0, 0, 0.0, time.perf_counter()
    try:
        for observations, image in source:
            chaine.pas(observations, image)
            images, t = images + 1, observations["t"]
            if image is not None and (video_annotee is not None or fenetre is not None):
                from .affichage import annoter
                image_annotee = annoter(image, list(chaine.fiches.values()), observations["t"], drone)
                if video_annotee is not None:
                    video_annotee.ecrire(image_annotee)
                if fenetre is not None:
                    fenetre.montrer(image_annotee)
            if image is not None and vue_directe is not None:
                vue_directe.ecrire(image, list(chaine.fiches.values()), observations["t"], drone)
            for ligne in journal.lignes[deja_affiche:]:
                afficher(ligne)
            deja_affiche = len(journal.lignes)
    except (KeyboardInterrupt, BrokenPipeError) as arret:
        # Ctrl+C devant une caméra, ou fenêtre du direct fermée : on clôt proprement, alertes en cours comprises
        if isinstance(arret, BrokenPipeError):  # plus personne ne lit, le texte non plus : il ne doit pas gêner la clôture
            sys.stdout = sys.stderr = open(os.devnull, "w")
        print("\narrêt demandé")
    duree = time.perf_counter() - debut
    chaine.cloturer(t)
    for ligne in journal.lignes[deja_affiche:]:
        afficher(ligne)
    if reid is not None and memoire_navires:
        reid.sauver(memoire_navires)
        print(f"mémoire des navires écrite : {len(reid.navires)} navire(s) dans {memoire_navires}.json/.npz")
    journal.fermer()
    emetteur.fermer()
    if video_annotee is not None:
        video_annotee.fermer()
        print(f"vidéo annotée écrite dans {sortie}")
    if fenetre is not None:
        fenetre.fermer()

    print(f"\n{images} images en {duree:.1f} s ({images / max(duree, 1e-9):.1f} images/s, détection et suivi compris)")
    durees = defaultdict(list)
    for ligne in journal.lignes:
        if "duree_ms" in ligne:
            durees[ligne["action"]].append(ligne["duree_ms"])
    for action, valeurs in durees.items():
        valeurs.sort()
        print(f"  {action:<12} {len(valeurs):3d} lancement(s), médiane {valeurs[len(valeurs) // 2]:7.1f} ms, "
              f"max {valeurs[-1]:7.1f} ms")
    print(f"{len(chaine.alertes)} alerte(s), journal dans {chemin_journal}, messages vers "
          f"{', '.join(messages)}")
    for alerte in chaine.alertes:
        print("  ", alerte)
    return chaine


def afficher(ligne: dict) -> None:
    fiche = ligne["fiche"]
    experts = fiche["experts"]
    print(f"{ligne['t']:7.2f} s  piste {ligne['piste']:<3} {ligne['action']:<16} {ligne['raison']:<44}"
          f" {fiche['suivi']['boite'][2]:5.0f} px  type {'/'.join(experts['types']) or '?':<12}"
          f" immat {experts['immatriculation'] or '?'}")


if __name__ == "__main__":
    main()
