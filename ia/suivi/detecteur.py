"""Détecteur de navires sur ordinateur : YOLO par Ultralytics (PyTorch).

Sert sur le Mac, pour les essais sur vidéo et dans le simulateur. Sur le Pi, c'est la caméra IMX500 qui détecte
(voir `camera_pi.py`) et ce fichier n'est pas chargé.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IA = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Profil:
    poids: Path
    classes: tuple[int, ...]
    confiance: float  # seuil d'une détection sûre : elle ouvre une piste et compte pour la confirmer


PROFILS = {
    # Modèle de Guillaume (ia/detection) : YOLO11n entraîné sur ~12 000 images de bateaux, avec gouttes, embruns,
    # flou de bougé, éblouissement et bruit de capteur. Une seule classe, « bateau ». 55 % : son meilleur compromis
    # entre hallucinations (vagues, cailloux) et bateaux manqués sur le jeu de test (précision 0,84, rappel 0,72).
    "best4_2": Profil(IA / "detection" / "best4" / "best4_2.pt", (0,), 0.55),
    "best4": Profil(IA / "detection" / "best4" / "best4.pt", (0,), 0.55),
    # YOLO11n entraîné sur COCO, celui que la caméra IMX500 fait tourner aujourd'hui : classe 8 (bateau).
    "yolo11n": Profil(IA / "chaine" / "modeles" / "yolo11n.pt", (8,), 0.3),
}
PAR_DEFAUT = "best4_2"
MODELE = PROFILS["yolo11n"].poids
BATEAU = 8  # classe COCO


def profil(modele: str | Path) -> Profil:
    """Profil d'un nom connu (best4_2, best4, yolo11n), ou d'un fichier .pt : celui du même nom s'il existe."""
    if str(modele) in PROFILS:
        return PROFILS[str(modele)]
    chemin = Path(modele).expanduser()
    connu = PROFILS.get(chemin.stem)
    return Profil(chemin, connu.classes, connu.confiance) if connu else Profil(chemin, (0,), 0.55)


class DetecteurYolo:
    def __init__(self, modele: str | Path = PAR_DEFAUT, taille: int = 640, classes: tuple[int, ...] | None = None,
                 confiance_min: float = 0.05):
        from ultralytics import YOLO
        p = profil(modele)
        self.nom = Path(p.poids).stem
        self._modele = YOLO(str(p.poids))
        self.taille = taille                # côté de l'image vue par le réseau, comme l'entrée de l'IMX500
        self.classes = list(classes if classes is not None else p.classes)
        self.confiance = p.confiance        # détection sûre (voir PROFILS)
        self.confiance_min = confiance_min  # bas exprès : l'associateur se sert des détections douteuses

    def detecter(self, image: Any) -> list[tuple[float, float, float, float, float]]:
        """Boîtes (x, y, largeur, hauteur, confiance) en pixels de l'image reçue."""
        boites = self._modele.predict(image, classes=self.classes, imgsz=self.taille, conf=self.confiance_min,
                                      verbose=False)[0].boxes
        return [(cx - l / 2, cy - h / 2, l, h, confiance)
                for (cx, cy, l, h), confiance in zip(boites.xywh.tolist(), boites.conf.tolist())]
