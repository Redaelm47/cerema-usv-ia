"""Images synthétiques d'immatriculations peintes sur une coque, pour mesurer l'expert OCR.

Faute de photos réelles étiquetées, on dessine l'immatriculation sur une coque de couleur, puis on dégrade
l'image comme le ferait la prise de vue : perspective, roulis, flou, bruit, compression. La hauteur des
caractères, en pixels, est le paramètre qui compte (12 à 28 px à 50 m d'après la proposition d'architecture).
"""
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..experts.immatriculation import QUARTIERS

POLICES = [  # macOS puis Linux ; les polices absentes sont ignorées
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
COQUES = [  # couleur de coque et couleur des caractères, en RVB
    ((20, 40, 90), (255, 255, 255)), ((15, 15, 20), (255, 255, 255)), ((140, 25, 25), (255, 255, 255)),
    ((10, 80, 60), (255, 255, 255)), ((235, 235, 230), (10, 10, 10)), ((30, 90, 150), (250, 240, 120)),
    ((225, 225, 225), (20, 40, 120)),
]


def polices_disponibles() -> list[str]:
    return [p for p in POLICES if Path(p).exists()]


def immatriculation_au_hasard(rng: random.Random) -> str:
    return f"{rng.choice(sorted(QUARTIERS))} {rng.randrange(1000000):06d}"


def dessiner(immatriculation: str, hauteur_caracteres: float, rng: random.Random, degradation: float = 1.0,
             largeur: int = 1000, hauteur: int = 360) -> np.ndarray:
    """Image BGR d'un navire schématique portant l'immatriculation, caractères hauts de `hauteur_caracteres` px."""
    echelle = 4  # dessin à grande échelle puis réduction, pour un rendu propre des petits caractères
    coque, encre = rng.choice(COQUES)
    separateur = rng.choice([" ", " ", ".", ""])
    texte = immatriculation.replace(" ", separateur)

    image = Image.new("RGB", (largeur * echelle, hauteur * echelle), (95, 110, 120))
    dessin = ImageDraw.Draw(image)
    haut = hauteur * echelle
    dessin.rectangle([0, int(0.75 * haut), largeur * echelle, haut], fill=(50, 70, 85))  # mer
    dessin.polygon([(int(0.04 * largeur * echelle), int(0.3 * haut)), (int(0.96 * largeur * echelle), int(0.3 * haut)),
                    (int(0.88 * largeur * echelle), int(0.8 * haut)), (int(0.10 * largeur * echelle), int(0.8 * haut))],
                   fill=coque)
    dessin.rectangle([int(0.45 * largeur * echelle), int(0.08 * haut), int(0.7 * largeur * echelle), int(0.3 * haut)],
                     fill=(220, 220, 215))  # passerelle

    polices = polices_disponibles()
    taille = 40
    police = ImageFont.truetype(rng.choice(polices), taille) if polices else ImageFont.load_default(taille)
    x0, y0, x1, y1 = police.getbbox("0")
    taille = max(int(round(taille * hauteur_caracteres * echelle / (y1 - y0))), 4)
    police = police.font_variant(size=taille) if polices else ImageFont.load_default(taille)
    x0, y0, x1, y1 = dessin.textbbox((0, 0), texte, font=police)
    x = rng.uniform(0.12, 0.6) * largeur * echelle
    x = min(x, 0.9 * largeur * echelle - (x1 - x0))
    y = rng.uniform(0.36, 0.6) * haut
    dessin.text((x, y - y0), texte, font=police, fill=encre)

    image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    image = cv2.resize(image, (largeur, hauteur), interpolation=cv2.INTER_AREA)

    # Perspective (navire vu de trois quarts) et roulis
    d = degradation
    ecart = rng.uniform(-0.12, 0.12) * d * hauteur
    depart = np.float32([[0, 0], [largeur, 0], [largeur, hauteur], [0, hauteur]])
    arrivee = np.float32([[0, max(ecart, 0)], [largeur, max(-ecart, 0)],
                          [largeur, hauteur - max(-ecart, 0)], [0, hauteur - max(ecart, 0)]])
    image = cv2.warpPerspective(image, cv2.getPerspectiveTransform(depart, arrivee), (largeur, hauteur),
                                borderMode=cv2.BORDER_REPLICATE)
    rotation = cv2.getRotationMatrix2D((largeur / 2, hauteur / 2), rng.uniform(-6, 6) * d, 1.0)
    image = cv2.warpAffine(image, rotation, (largeur, hauteur), borderMode=cv2.BORDER_REPLICATE)

    # Flou de mise au point et de bougé, éclairage, bruit, compression
    sigma = rng.uniform(0.0, 1.0) * d
    if sigma > 0.1:
        image = cv2.GaussianBlur(image, (0, 0), sigma)
    if rng.random() < 0.3 * d:
        noyau = np.zeros((3, 3), np.float32)
        noyau[1, :] = 1 / 3
        image = cv2.filter2D(image, -1, noyau)
    image = image.astype(np.float32) * rng.uniform(1 - 0.4 * d, 1 + 0.2 * d) + rng.uniform(-20, 20) * d
    bruit = np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1, 6) * d, image.shape)
    image = np.clip(image + bruit, 0, 255).astype(np.uint8)
    _, code = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(rng.uniform(95 - 45 * d, 95))])
    return cv2.imdecode(code, cv2.IMREAD_COLOR)
