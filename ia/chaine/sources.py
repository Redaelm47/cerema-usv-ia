"""Sources d'observations au format du contrat 1.

Chaque source produit, pour chaque image, le message du contrat 1 et l'image pleine résolution.
- `ScenarioSimule` : deux navires et une fausse détection, sans image ni dépendance ;
- `SourceVideo` : remplaçant de la caméra et du suivi, YOLO + ByteTrack sur une vidéo ;
- `SourceRejouee` : rejoue des observations enregistrées, sans refaire la détection.
"""
import json
from pathlib import Path
from typing import Any, Iterator

from . import contrats
from .fiche import Observation

Image = Any


class ScenarioSimule:
    """Deux navires et une fausse détection, pour tester la chaîne sans caméra.

    - piste 3 : fausse détection, vue sur une seule image ;
    - piste 7 : navire lointain (150 px), qui ne grossit que si le drone s'approche ;
    - piste 9 : navire proche (700 px), lisible tout de suite.
    """

    def __init__(self, drone=None, duree_s: float = 150.0, images_par_s: float = 5.0):
        self.drone = drone
        self.duree_s = duree_s
        self.images_par_s = images_par_s

    def __iter__(self) -> Iterator[tuple[dict, Image]]:
        pas_s = 1.0 / self.images_par_s
        for numero in range(int(self.duree_s * self.images_par_s) + 1):
            t = numero * pas_s
            largeur_7 = 150.0
            if self.drone is not None and self.drone.cible == 7:
                largeur_7 *= self.drone.rapprochement
            pistes = [Observation(7, (1000.0, 800.0, largeur_7, largeur_7 / 3), 0.8)]
            if numero == 5:
                pistes.append(Observation(3, (200.0, 900.0, 30.0, 12.0), 0.4))
            if t >= 20.0:
                pistes.append(Observation(9, (2500.0, 1200.0, 700.0, 230.0), 0.9))
            yield contrats.observations(t, pistes), None


class SourceVideo:
    """Remplaçant de la caméra et du suivi : détection et suivi sur une vidéo (Ultralytics, YOLO + ByteTrack).

    Classe COCO 8 = bateau. Si un drone simulé est fourni, son approche est rendue par un zoom centré sur
    le navire approché : la détection et le suivi travaillent sur l'image zoomée. Avec `largeur_vue` plus
    petite que la vidéo, la vue large est réduite et le zoom retrouve les pixels d'origine : l'approche
    apporte alors du vrai détail, comme le ferait le drone en se rapprochant.
    """

    def __init__(self, chemin: str, modele: str | None = None, classes: tuple[int, ...] = (8,),
                 drone=None, enregistrer: str | None = None, zoom_max: float = 6.0,
                 largeur_vue: int | None = None, taille_detection: int = 640):
        import cv2
        self.chemin = chemin
        self.modele = modele or str(Path(__file__).resolve().parent / "modeles" / "yolo11n.pt")
        self.classes = list(classes)
        self.drone = drone
        self.enregistrer = enregistrer
        self.zoom_max = zoom_max
        self.largeur_vue = largeur_vue  # largeur de l'image fournie à la chaîne ; None = celle de la vidéo
        self.taille_detection = taille_detection  # côté de l'image vue par YOLO : 640 comme la veille de l'IMX500
        capture = cv2.VideoCapture(chemin)
        if not capture.isOpened():
            raise FileNotFoundError(f"vidéo illisible : {chemin}")
        self.images_par_s = capture.get(cv2.CAP_PROP_FPS) or 25.0
        self._taille = (capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        capture.release()
        self._zoom = 1.0
        self._centre: tuple[float, float] | None = None  # centre du zoom, en part de l'image d'origine
        self._fenetre = (0.0, 0.0, 1.0)                    # coin et facteur du zoom en cours

    def _vue(self, image: Image) -> Image:
        """Image vue par la caméra simulée : la vidéo entière en patrouille, une partie agrandie en approche."""
        import cv2
        cible = min(self.drone.rapprochement, self.zoom_max) if self.drone is not None else 1.0
        # Suit l'approche de près ; revient lentement à la vue large ensuite, pour que le suivi garde la piste.
        self._zoom += (0.2 if cible > self._zoom else 0.02) * (cible - self._zoom)
        hauteur, largeur = image.shape[:2]
        largeur_vue = self.largeur_vue or largeur
        hauteur_vue = int(round(hauteur * largeur_vue / largeur))
        zoom = self._zoom if self._centre is not None else 1.0
        l, h = largeur / zoom, hauteur / zoom
        centre = self._centre or (0.5, 0.5)
        x0 = min(max(centre[0] * largeur - l / 2, 0), largeur - l)
        y0 = min(max(centre[1] * hauteur - h / 2, 0), hauteur - h)
        echelle = largeur_vue / l  # pixels de la vue par pixel de la vidéo
        self._fenetre = (x0, y0, echelle)
        if zoom == 1.0 and largeur_vue == largeur:
            return image
        vue = image[int(y0):int(y0 + h), int(x0):int(x0 + l)]
        return cv2.resize(vue, (largeur_vue, hauteur_vue),
                          interpolation=cv2.INTER_AREA if echelle < 1 else cv2.INTER_CUBIC)

    def __iter__(self) -> Iterator[tuple[dict, Image]]:
        import cv2
        from ultralytics import YOLO

        modele = YOLO(self.modele)
        capture = cv2.VideoCapture(self.chemin)
        fichier = None
        if self.enregistrer:
            Path(self.enregistrer).parent.mkdir(parents=True, exist_ok=True)
            fichier = open(self.enregistrer, "w", encoding="utf-8")
        numero = 0
        try:
            while True:
                lue, image = capture.read()
                if not lue:
                    break
                image = self._vue(image)
                resultat = modele.track(image, persist=True, tracker="bytetrack.yaml", classes=self.classes,
                                        imgsz=self.taille_detection, verbose=False)[0]
                pistes = []
                boites = resultat.boxes
                if boites is not None and boites.id is not None:
                    for xywh, id_piste, confiance in zip(boites.xywh.tolist(), boites.id.tolist(),
                                                         boites.conf.tolist()):
                        cx, cy, largeur, hauteur = xywh
                        pistes.append(Observation(int(id_piste), (cx - largeur / 2, cy - hauteur / 2, largeur, hauteur),
                                                  float(confiance)))
                self._suivre_la_cible(pistes, image)
                message = contrats.observations(numero / self.images_par_s, pistes)
                if fichier:
                    fichier.write(json.dumps(message) + "\n")
                yield message, image
                numero += 1
        finally:
            capture.release()
            if fichier:
                fichier.close()

    def _suivre_la_cible(self, pistes: list[Observation], image: Image) -> None:
        """Garde le centre du zoom sur le navire approché, en coordonnées de l'image d'origine."""
        if self.drone is None or self.drone.cible is None:
            return
        x0, y0, echelle = self._fenetre
        for piste in pistes:
            if piste.id_piste == self.drone.cible:
                x, y, l, h = piste.boite
                centre = ((x0 + (x + l / 2) / echelle) / self._taille[0], (y0 + (y + h / 2) / echelle) / self._taille[1])
                if self._centre is None:
                    self._centre = centre
                else:  # lissage, pour que la vue ne tremble pas
                    self._centre = tuple(0.8 * a + 0.2 * b for a, b in zip(self._centre, centre))


class SourceRejouee:
    """Rejoue une vidéo avec des observations déjà enregistrées (une ligne JSON du contrat 1 par image)."""

    def __init__(self, chemin_video: str, chemin_observations: str):
        import cv2
        self.chemin_video = chemin_video
        self.chemin_observations = chemin_observations
        capture = cv2.VideoCapture(chemin_video)
        self.images_par_s = capture.get(cv2.CAP_PROP_FPS) or 25.0
        capture.release()

    def __iter__(self) -> Iterator[tuple[dict, Image]]:
        import cv2
        capture = cv2.VideoCapture(self.chemin_video)
        try:
            with open(self.chemin_observations, encoding="utf-8") as lignes:
                for ligne in lignes:
                    lue, image = capture.read()
                    if not lue:
                        break
                    yield json.loads(ligne), image
        finally:
            capture.release()
