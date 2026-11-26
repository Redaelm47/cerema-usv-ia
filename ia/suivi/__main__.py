"""Lance la caméra et le suivi seuls, et écrit leur sortie : les observations du contrat 1.

    python3 -m suivi --video ../data/scene-blender-01.mp4 --observations runs/observations.jsonl
    python3 -m suivi --camera 0 --duree 20                 webcam de l'ordinateur
    python3 -m suivi --pi --duree 20                       caméra IMX500, sur le Raspberry Pi
"""
import argparse
import json
import time


def creer_suivi(args, enregistrer: str | None = None):
    """Le suivi demandé par les options communes (`ajouter_options`)."""
    from .suivi import Suivi
    if args.pi:
        from .camera_pi import CameraIMX500
        largeur, hauteur = (int(v) for v in args.resolution.split("x"))
        images = CameraIMX500(resolution=(largeur, hauteur), duree_s=args.duree,
                              classes=None if args.toutes_classes else (8,), retourner=not args.sans_retournement)
        return Suivi(images, enregistrer=enregistrer)
    from .detecteur import DetecteurYolo
    from .images import ImagesCamera, ImagesVideo
    images = ImagesVideo(args.video, temps_reel=args.temps_reel) if args.video else ImagesCamera(args.camera, args.duree)
    if args.toutes_classes:  # essais sans navire : le modèle COCO, toutes ses classes
        detecteur = DetecteurYolo("yolo11n", taille=args.taille_detection, classes=tuple(range(80)))
    else:
        detecteur = DetecteurYolo(args.detecteur, taille=args.taille_detection)
    return Suivi(images, detecteur, enregistrer=enregistrer)


def ajouter_options(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", help="fichier vidéo")
    source.add_argument("--camera", type=int, metavar="N", help="webcam de l'ordinateur (0 en général)")
    source.add_argument("--pi", action="store_true", help="caméra IMX500 du Raspberry Pi")
    parser.add_argument("--temps-reel", action="store_true",
                        help="avec --video : la vidéo défile à sa vitesse, les images en retard sont sautées")
    parser.add_argument("--duree", type=float, metavar="S", help="avec --camera ou --pi : s'arrêter après S secondes")
    parser.add_argument("--resolution", default="2028x1520", help="avec --pi : taille de l'image (LxH)")
    parser.add_argument("--sans-retournement", action="store_true", help="avec --pi : caméra montée à l'endroit")
    parser.add_argument("--taille-detection", type=int, default=640, metavar="PX",
                        help="avec --video ou --camera : côté de l'image vue par le détecteur")
    parser.add_argument("--detecteur", default="best4_2", metavar="MODELE",
                        help="avec --video ou --camera : best4_2 (défaut, modèle de Guillaume, seuil 55 %%), best4, "
                             "yolo11n (COCO, celui de l'IMX500) ou un fichier .pt")
    parser.add_argument("--toutes-classes", action="store_true",
                        help="suivre tous les objets, pas seulement les bateaux (essais sans navire)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Caméra et suivi : écrit les observations du contrat 1")
    ajouter_options(parser)
    parser.add_argument("--observations", default="runs/observations.jsonl", help="fichier de sortie (.jsonl)")
    parser.add_argument("--sortie", help="vidéo annotée à écrire (.mp4)")
    args = parser.parse_args()

    suivi = creer_suivi(args, enregistrer=args.observations)
    ecrivain, images, numeros, debut = None, 0, set(), time.perf_counter()
    for message, image in suivi:
        images += 1
        numeros.update(p["id_piste"] for p in message["pistes"])
        if images % 30 == 1:
            print(json.dumps(message))
        if args.sortie:
            import cv2
            if ecrivain is None:
                ecrivain = cv2.VideoWriter(args.sortie, cv2.VideoWriter_fourcc(*"mp4v"), suivi.images_par_s,
                                           (image.shape[1], image.shape[0]))
            for p in message["pistes"]:
                x, y, l, h = (int(v) for v in p["boite"])
                cv2.rectangle(image, (x, y), (x + l, y + h), (0, 255, 0), 3)
                cv2.putText(image, f"{p['id_piste']}  {p['confiance']:.2f}", (x, max(y - 8, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            ecrivain.write(image)
    if ecrivain is not None:
        ecrivain.release()
    duree = time.perf_counter() - debut
    print(f"{images} images en {duree:.1f} s ({images / max(duree, 1e-9):.1f} images/s), {len(numeros)} numéro(s) "
          f"de piste : {sorted(numeros)}")
    print(f"observations écrites dans {args.observations}")


if __name__ == "__main__":
    main()
