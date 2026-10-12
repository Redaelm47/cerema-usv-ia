"""Interface commune des experts, et recadrage du navire dans l'image pleine résolution."""
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..fiche import Boite, FicheNavire

Image = Any  # tableau numpy hauteur x largeur x 3, en BGR (convention d'OpenCV)


@dataclass
class Resultat:
    reussi: bool
    valeurs: dict[str, Any] = field(default_factory=dict)


class Expert(Protocol):
    nom: str

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        """`image` est l'image pleine résolution (None dans le scénario simulé) ; la boîte est dans la fiche."""
        ...


def recadrer(image: Image, boite: Boite, marge: float = 0.0) -> Image:
    """Recadrage de l'image sur la boîte, élargie de `marge` (part de la largeur et de la hauteur)."""
    x, y, largeur, hauteur = boite
    hauteur_image, largeur_image = image.shape[:2]
    x0 = max(int(round(x - marge * largeur)), 0)
    y0 = max(int(round(y - marge * hauteur)), 0)
    x1 = min(int(round(x + largeur * (1 + marge))), largeur_image)
    y1 = min(int(round(y + hauteur * (1 + marge))), hauteur_image)
    return image[y0:y1, x0:x1]
