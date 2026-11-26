"""Détecteur de navires sur ordinateur : YOLO par Ultralytics (PyTorch).

Sert sur le Mac et pour les essais sur vidéo. Sur le Pi, c'est la caméra IMX500 qui détecte (voir
`camera_pi.py`) et ce fichier n'est pas chargé.
"""
from pathlib import Path
from typing import Any

MODELE = Path(__file__).resolve().parent.parent / "chaine" / "modeles" / "yolo11n.pt"
BATEAU = 8  # classe COCO


class DetecteurYolo:
    def __init__(self, modele: str | Path = MODELE, taille: int = 640, classes: tuple[int, ...] = (BATEAU,),
                 confiance_min: float = 0.05):
        from ultralytics import YOLO
        self._modele = YOLO(str(modele))
        self.taille = taille                # côté de l'image vue par le réseau, comme l'entrée de l'IMX500
        self.classes = list(classes)
        self.confiance_min = confiance_min  # bas exprès : l'associateur se sert des détections douteuses

    def detecter(self, image: Any) -> list[tuple[float, float, float, float, float]]:
        """Boîtes (x, y, largeur, hauteur, confiance) en pixels de l'image reçue."""
        boites = self._modele.predict(image, classes=self.classes, imgsz=self.taille, conf=self.confiance_min,
                                      verbose=False)[0].boxes
        return [(cx - l / 2, cy - h / 2, l, h, confiance)
                for (cx, cy, l, h), confiance in zip(boites.xywh.tolist(), boites.conf.tolist())]
