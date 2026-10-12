"""Scène de test de la vision embarquée : ce que voit le drone quand un navire de pêche passe.

    blender -b -P scene.py -- --apercu 200 /tmp/apercu.jpg      une image, en petit, pour vérifier
    blender -b -P scene.py -- --rendu                            toute la séquence, en suite d'images
    blender -b -P scene.py -- --rendu --debut 100 --fin 160      une partie seulement

La caméra est celle du drone : à 1,2 m de l'eau, 66° de champ, elle roule et tangue avec la mer.
Le navire principal vient de loin sur la gauche, coupe le champ en biais sans jamais être bien
cadré et en sort par la droite au plus près ; un second navire passe au loin en sens inverse.
Un rendu interrompu reprend où il s'est arrêté : les images déjà écrites ne sont pas refaites.
La vérité de la scène (immatriculations, position et distance de chaque navire à chaque image)
est écrite dans `verite.json`, à côté des images.
"""
import argparse
import json
import math
import os
import sys

import bpy

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import bateau  # noqa: E402
import mer  # noqa: E402

DUREE_S = 30.0
IMAGES_PAR_S = 15
ETAT_MER = 3.5
VAGUELETTES = 2.0   # facteur sur la hauteur des vaguelettes de mer.py
RELIEF_FIN = 2.2    # force du relief fin de l'eau (1 dans mer.py)
OBTURATION = 0.06  # part de l'intervalle entre deux images : 1/250 s à 15 images/s, plein jour
SORTIE = os.path.normpath(os.path.join(ICI, "..", "..", "data", "blender", "rendu", "scene_01"))

# Chaque navire : route en ligne droite de `depart` à `arrivee` (x vers la droite, y devant la caméra, mètres).
NAVIRES = [
    dict(nom="MARIE-LOUISE", immatriculation="GV 642410", longueur=14.0, couleur_coque=(0.05, 0.18, 0.45),
         depart=(-80.0, 105.0), arrivee=(24.0, 32.0), graine=0),
    dict(nom="AR MEN", immatriculation="CC 911290", longueur=12.0, couleur_coque=(0.45, 0.06, 0.05),
         depart=(150.0, 290.0), arrivee=(40.0, 250.0), graine=3),
]


def poser_navire(navire: dict) -> list[tuple[float, float]]:
    """Crée le navire sur sa route et renvoie sa position à chaque image."""
    n_images = int(round(DUREE_S * IMAGES_PAR_S)) + 1
    (x0, y0), (x1, y1) = navire["depart"], navire["arrivee"]
    positions = [(x0 + (x1 - x0) * i / (n_images - 1), y0 + (y1 - y0) * i / (n_images - 1)) for i in range(n_images)]
    vitesse_m_s = math.hypot(x1 - x0, y1 - y0) / DUREE_S

    route = bpy.data.objects.new("Route " + navire["nom"], None)
    bpy.context.scene.collection.objects.link(route)
    route.location = (x0, y0, 0.0)
    route.rotation_euler = (0.0, 0.0, math.atan2(y1 - y0, x1 - x0))  # étrave (+X du navire) dans le sens de la route
    mer._poser_courbe(route, "location", [p[0] for p in positions], 0)
    mer._poser_courbe(route, "location", [p[1] for p in positions], 1)

    objet = bateau.creer_bateau(nom=navire["nom"], immatriculation=navire["immatriculation"],
                                longueur=navire["longueur"], couleur_coque=navire["couleur_coque"],
                                graine=navire["graine"])
    objet.parent = route
    mer.faire_flotter(objet, navire["longueur"], etat=ETAT_MER, duree_s=DUREE_S, images_par_s=IMAGES_PAR_S,
                      graine=navire["graine"])
    mer.creer_sillage(objet, navire["longueur"], navire["longueur"] / 3, vitesse_m_s / 0.5144)
    return positions


def construire(couverture: float, graine: int) -> dict:
    mer.vider_scene()
    # Mer plus hachée que le réglage d'origine, qui donnait une surface trop lisse vue au ras de l'eau :
    # vaguelettes plus hautes et relief fin du matériau renforcé.
    for etat in mer._ETATS.values():
        etat["hs_rides"] *= VAGUELETTES
    mer.creer_mer(etat=ETAT_MER, duree_s=DUREE_S, images_par_s=IMAGES_PAR_S, graine=graine)
    bpy.data.materials[mer.NOM_MATERIAU_EAU].node_tree.nodes["Rides"].inputs["Strength"].default_value = RELIEF_FIN
    mer.creer_ciel(heure=17.0, couverture=couverture, graine=graine)
    mer.creer_camera(duree_s=DUREE_S, images_par_s=IMAGES_PAR_S, etat=ETAT_MER, graine=graine)
    verite = {"images_par_s": IMAGES_PAR_S, "duree_s": DUREE_S, "etat_mer": ETAT_MER, "couverture": couverture,
              "champ_horizontal_deg": 66.0, "navires": []}
    for navire in NAVIRES:
        positions = poser_navire(navire)
        verite["navires"].append({
            "nom": navire["nom"], "immatriculation": navire["immatriculation"], "longueur_m": navire["longueur"],
            "par_image": [{"x": round(x, 1), "y": round(y, 1), "distance_m": round(math.hypot(x, y), 1),
                           "gisement_deg": round(math.degrees(math.atan2(x, y)), 1)} for x, y in positions]})
    return verite


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apercu", nargs=2, metavar=("IMAGE", "FICHIER"), help="rend une seule image")
    parser.add_argument("--rendu", action="store_true", help="rend la séquence")
    parser.add_argument("--debut", type=int, default=1)
    parser.add_argument("--fin", type=int)
    parser.add_argument("--largeur", type=int, default=2028)
    parser.add_argument("--hauteur", type=int, default=1520)
    parser.add_argument("--echantillons", type=int, help="échantillons Cycles par pixel (défaut : 40)")
    parser.add_argument("--couverture", type=float, default=0.4, help="0 = ciel clair, 1 = couvert")
    parser.add_argument("--graine", type=int, default=0)
    parser.add_argument("--sortie", default=SORTIE)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    verite = construire(args.couverture, args.graine)
    scene = bpy.context.scene
    if args.apercu:
        mer.regler_rendu(args.largeur, args.hauteur, IMAGES_PAR_S, qualite="finale", echantillons=args.echantillons)
        scene.render.motion_blur_shutter = OBTURATION
        scene.frame_set(int(args.apercu[0]))
        scene.render.filepath = args.apercu[1]
        bpy.ops.render.render(write_still=True)
    elif args.rendu:
        os.makedirs(args.sortie, exist_ok=True)
        mer.regler_rendu(args.largeur, args.hauteur, IMAGES_PAR_S, qualite="finale", dossier_sortie=args.sortie,
                         echantillons=args.echantillons)
        scene.render.motion_blur_shutter = OBTURATION
        with open(os.path.join(args.sortie, "verite.json"), "w", encoding="utf-8") as f:
            json.dump(verite, f, ensure_ascii=False)
        scene.frame_start = args.debut
        scene.frame_end = args.fin or scene.frame_end
        scene.render.use_overwrite = False     # reprise : les images déjà là sont gardées
        scene.render.use_placeholder = False
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
