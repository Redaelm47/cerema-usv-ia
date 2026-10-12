"""Sources d'images sans détection intégrée : fichier vidéo et webcam. Rendent (t, image BGR, None)."""
import time
from typing import Any, Iterator


class ImagesVideo:
    """Images d'un fichier vidéo.

    Par défaut toutes les images sont rendues, datées d'après leur numéro : le résultat ne dépend pas de
    la vitesse de la machine. Avec `temps_reel`, la vidéo défile à sa vitesse et les images que la machine
    n'a pas le temps de traiter sont sautées, comme devant une vraie caméra.
    """

    def __init__(self, chemin: str, temps_reel: bool = False):
        import cv2
        self.chemin = chemin
        self.temps_reel = temps_reel
        capture = cv2.VideoCapture(chemin)
        if not capture.isOpened():
            raise FileNotFoundError(f"vidéo illisible : {chemin}")
        self.images_par_s = capture.get(cv2.CAP_PROP_FPS) or 25.0
        capture.release()

    def __iter__(self) -> Iterator[tuple[float, Any, None]]:
        import cv2
        capture = cv2.VideoCapture(self.chemin)
        debut, numero = time.monotonic(), 0
        try:
            while True:
                if self.temps_reel:
                    voulu = int((time.monotonic() - debut) * self.images_par_s)
                    while numero < voulu and capture.grab():
                        numero += 1
                    time.sleep(max(numero / self.images_par_s - (time.monotonic() - debut), 0.0))
                lue, image = capture.read()
                if not lue:
                    break
                yield numero / self.images_par_s, image, None
                numero += 1
        finally:
            capture.release()


class ImagesCamera:
    """Webcam de l'ordinateur (essais). Datée à l'horloge, depuis le démarrage."""

    def __init__(self, numero: int = 0, duree_s: float | None = None):
        self.numero = numero
        self.duree_s = duree_s
        self.images_par_s = 15.0

    def __iter__(self) -> Iterator[tuple[float, Any, None]]:
        import cv2
        capture = cv2.VideoCapture(self.numero)
        if not capture.isOpened():
            raise RuntimeError(f"caméra {self.numero} inaccessible")
        debut = time.monotonic()
        try:
            while self.duree_s is None or time.monotonic() - debut < self.duree_s:
                lue, image = capture.read()
                if not lue:
                    break
                yield time.monotonic() - debut, image, None
        finally:
            capture.release()
