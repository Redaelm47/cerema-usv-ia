"""Peint une immatriculation française sur le navire d'une vidéo, pour essayer la chaîne jusqu'à l'alerte complète.

    python3 -m chaine.outils.incruster_immatriculation ../data/bateau-peche-dingle.webm \\
        runs/dingle_observations.jsonl ../data/bateau-peche-dingle-immatricule.mp4 --immatriculation "GV 642410"

Trucage de test, en attendant la scène Blender : la vidéo d'origine ne montre aucune immatriculation
française. Les observations (contrat 1) viennent de `python3 -m chaine --video ... --sans-zoom
--enregistrer-observations ...` ; le cartouche suit la boîte de la piste choisie.
"""
import argparse
import json

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video")
    parser.add_argument("observations", help="observations du contrat 1, une ligne JSON par image")
    parser.add_argument("sortie", help="vidéo à écrire (.mp4)")
    parser.add_argument("--immatriculation", default="GV 642410")
    parser.add_argument("--piste", type=int, help="numéro de la piste à marquer (défaut : la plus grande boîte)")
    parser.add_argument("--largeur", type=float, default=0.5, help="largeur du cartouche, en part de la boîte")
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.video)
    images_par_s = capture.get(cv2.CAP_PROP_FPS) or 25.0
    taille = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    ecrivain = cv2.VideoWriter(args.sortie, cv2.VideoWriter_fourcc(*"mp4v"), images_par_s, taille)
    police, lisse = cv2.FONT_HERSHEY_DUPLEX, None
    with open(args.observations, encoding="utf-8") as lignes:
        for ligne in lignes:
            lue, image = capture.read()
            if not lue:
                break
            pistes = [p for p in json.loads(ligne)["pistes"] if args.piste in (None, p["id_piste"])]
            if pistes:
                boite = max(pistes, key=lambda p: p["boite"][2])["boite"]
                lisse = boite if lisse is None else [0.7 * a + 0.3 * b for a, b in zip(lisse, boite)]
                x, y, largeur, hauteur = lisse
                (l, h), _ = cv2.getTextSize(args.immatriculation, police, 1.0, 2)
                echelle = args.largeur * largeur / l
                l, h = int(l * echelle), int(h * echelle)
                x0, y0 = int(x + 0.2 * largeur), int(y + 0.78 * hauteur)
                cv2.rectangle(image, (x0 - h // 2, y0 - h - h // 2), (x0 + l + h // 2, y0 + h // 2), (70, 40, 20), -1)
                cv2.putText(image, args.immatriculation, (x0, y0), police, echelle, (255, 255, 255),
                            max(int(round(2 * echelle)), 1), cv2.LINE_AA)
            ecrivain.write(image)
    capture.release()
    ecrivain.release()
    print(f"vidéo écrite dans {args.sortie}")


if __name__ == "__main__":
    main()
