"""Assemble une source d'images, un détecteur et l'associateur, et rend le contrat 1.

Ce module ne dépend pas de la chaîne de décision : sa sortie est le message du contrat 1 et l'image
pleine résolution, rien d'autre.
"""
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from .associateur import Associateur, Piste

Image = Any


def observations(t: float, pistes: list[Piste]) -> dict[str, Any]:
    """Message du contrat 1 pour une image. Boîtes en pixels de l'image fournie avec le message."""
    return {"t": round(float(t), 3),
            "pistes": [{"id_piste": int(p.id_piste), "boite": [round(float(v), 1) for v in p.boite],
                        "confiance": round(float(p.confiance), 3)} for p in pistes]}


class Suivi:
    """Itère sur (message du contrat 1, image BGR pleine résolution), une fois par image.

    `images` rend des triplets (t, image, détections). Les détections valent None quand la source ne
    détecte pas elle-même (vidéo, webcam) : le `detecteur` est alors appelé sur l'image. La caméra IMX500
    détecte dans le capteur et fournit directement ses boîtes.
    """

    def __init__(self, images: Iterable, detecteur=None, associateur: Associateur | None = None,
                 enregistrer: str | None = None):
        self.images = images
        self.detecteur = detecteur
        self.associateur = associateur or Associateur()
        self.enregistrer = enregistrer
        self.images_par_s = getattr(images, "images_par_s", 15.0)

    def __iter__(self) -> Iterator[tuple[dict, Image]]:
        fichier = None
        if self.enregistrer:
            Path(self.enregistrer).parent.mkdir(parents=True, exist_ok=True)
            fichier = open(self.enregistrer, "w", encoding="utf-8")
        try:
            for t, image, detections in self.images:
                if detections is None:
                    detections = self.detecteur.detecter(image)
                message = observations(t, self.associateur.mettre_a_jour(detections, t))
                if fichier:
                    fichier.write(json.dumps(message) + "\n")
                    fichier.flush()
                yield message, image
        finally:
            if fichier:
                fichier.close()
