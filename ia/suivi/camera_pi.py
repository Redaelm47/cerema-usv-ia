"""Raspberry Pi AI Camera (IMX500) : la détection tourne dans le capteur, le Pi ne reçoit que les boîtes.

Rend (t, image BGR pleine résolution, détections). Ne se charge que sur le Pi (picamera2).
Essayé sur le Pi le 12/10/2026 avec le modèle YOLO11n officiel (`~/models/imx500_network_yolo11n_pp.rpk`,
dépôt raspberrypi/imx500-models) : la caméra tourne à 10 images par seconde en 2028 x 1520 et le modèle
rend ses sorties. Pas encore vérifié devant un navire : le repère des boîtes et le sens de l'image.
"""
import os
import time
from typing import Any, Iterator

MODELE = os.path.expanduser("~/models/imx500_network_yolo11n_pp.rpk")
BATEAU = 8  # classe COCO


class CameraIMX500:
    def __init__(self, modele: str = MODELE, resolution: tuple[int, int] = (2028, 1520), images_par_s: float = 10.0,
                 classes: tuple[int, ...] | None = (BATEAU,), confiance_min: float = 0.05, retourner: bool = True,
                 duree_s: float | None = None):
        self.modele = modele
        self.resolution = resolution      # image fournie à la chaîne ; 4056 x 3040 au maximum, plus lent
        self.images_par_s = images_par_s
        self.classes = set(classes) if classes else None   # None : toutes les classes (essais sans navire)
        self.confiance_min = confiance_min
        self.retourner = retourner        # la caméra est montée tête en bas
        self.duree_s = duree_s

    def __iter__(self) -> Iterator[tuple[float, Any, list]]:
        import cv2
        from picamera2 import Picamera2
        from picamera2.devices import IMX500

        largeur, hauteur = self.resolution
        imx500 = IMX500(self.modele)  # avant Picamera2 : charge le modèle dans la caméra
        _, cote_reseau = imx500.get_input_size()
        camera = Picamera2(imx500.camera_num)
        # Le format « RGB888 » de picamera2 range les couleurs dans l'ordre bleu, vert, rouge : celui d'OpenCV.
        reglage = camera.create_video_configuration(main={"size": (largeur, hauteur), "format": "RGB888"},
                                                    controls={"FrameRate": self.images_par_s}, buffer_count=4)
        camera.start(reglage)
        debut = None  # l'horloge part à la première image : charger le modèle dans la caméra prend jusqu'à une minute
        try:
            while debut is None or self.duree_s is None or time.monotonic() - debut < self.duree_s:
                requete = camera.capture_request()
                try:
                    debut = debut or time.monotonic()
                    t = time.monotonic() - debut
                    metadonnees = requete.get_metadata()
                    sorties = imx500.get_outputs(metadonnees, add_batch=True)
                    if sorties is None:
                        # Mesuré le 02/11/2026 : en 4056 x 3040, le réseau ne rend un résultat qu'une image sur deux
                        # (toutes en 2028 x 1520). Transmettre cette image dirait « plus aucun navire », et les
                        # pistes, jamais vues trois images d'affilée, ne seraient jamais confirmées.
                        continue
                    image = requete.make_array("main").copy()
                finally:
                    requete.release()
                detections = []
                boites, confiances, classes = sorties[0][0], sorties[1][0], sorties[2][0]
                # Boîtes (x0, y0, x1, y1) en pixels de l'entrée du réseau ; convert_inference_coords
                # attend (y0, x0, y1, x1) entre 0 et 1 et rend des pixels de l'image principale.
                boites = (boites / cote_reseau)[:, [1, 0, 3, 2]]
                for boite, confiance, classe in zip(boites, confiances, classes):
                    if confiance < self.confiance_min or (self.classes and int(classe) not in self.classes):
                        continue
                    x, y, l, h = imx500.convert_inference_coords(tuple(boite), metadonnees, camera)
                    detections.append((float(x), float(y), float(l), float(h), float(confiance)))
                if self.retourner:
                    image = cv2.rotate(image, cv2.ROTATE_180)
                    detections = [(largeur - x - l, hauteur - y - h, l, h, c) for x, y, l, h, c in detections]
                yield t, image, detections
        finally:
            camera.stop()
