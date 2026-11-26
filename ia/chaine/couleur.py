"""Prototype : signature de couleur d'un navire, en complément de la signature DINOv2.

DINOv2 est entraîné avec des variations de couleur : il distingue mal deux navires de même forme et de
couleurs différentes. Cette signature décrit la couleur de la coque par un histogramme, qui se compare avec
`similarite_couleur`. Elle ne remplace pas DINOv2 : voir `outils/comparer_couleur.py`, qui mesure si les deux
ensemble séparent mieux les navires.

Choix :
- on ne garde que le centre du recadrage (le bord contient surtout de l'eau et du ciel) ;
- les pixels colorés vont dans un histogramme teinte x saturation, les pixels gris, blancs ou noirs dans un
  histogramme de luminosité : une coque blanche et une coque grise ne se confondent pas avec une coque bleue ;
- la racine carrée des fréquences rend la comparaison plus tolérante aux petits changements de lumière
  (distance de Hellinger).
"""
import numpy as np

TEINTES = 12          # secteurs de teinte (OpenCV : 0 à 179)
SATURATIONS = 3       # niveaux de saturation des pixels colorés
LUMINOSITES = 6       # niveaux de luminosité des pixels sans couleur
MARGE = 0.2           # part du recadrage ignorée sur chaque bord
SATURATION_MIN = 50   # en dessous (sur 255), le pixel est gris, blanc ou noir
LUMINOSITE_MIN = 40   # en dessous, le pixel est noir : la teinte n'a plus de sens
DIMENSION = TEINTES * SATURATIONS + LUMINOSITES


def signature_couleur(recadrage: np.ndarray) -> np.ndarray | None:
    """Recadrage BGR -> vecteur de norme 1, ou None si le recadrage est vide."""
    import cv2  # importé ici : la comparaison seule se teste sans OpenCV

    if recadrage is None or recadrage.ndim != 3 or recadrage.shape[0] < 4 or recadrage.shape[1] < 4:
        return None
    h, l = recadrage.shape[:2]
    dy, dx = int(h * MARGE), int(l * MARGE)
    return _histogramme(recadrage[dy:h - dy, dx:l - dx])


BANDES = 3  # de haut en bas : superstructure, flanc, coque


def signature_couleur_bandes(recadrage: np.ndarray) -> np.ndarray | None:
    """Recadrage BGR -> vecteur de norme 1 qui décrit la couleur de trois bandes horizontales du navire.

    « Coque bleue, cabine blanche » distingue mieux que la moyenne « bleu et blanc » : deux navires aux
    mêmes couleurs mal réparties ne se confondent plus. Le vecteur concatène les histogrammes des bandes,
    divisé par la racine du nombre de bandes : le produit scalaire de deux vecteurs est la moyenne des
    similarités des bandes. Une bande vide donne None (le navire entier est alors ignoré).
    """
    import cv2  # noqa: F401  (même dépendance que signature_couleur)

    if recadrage is None or recadrage.ndim != 3 or recadrage.shape[0] < 3 * BANDES or recadrage.shape[1] < 4:
        return None
    h, l = recadrage.shape[:2]
    dy, dx = int(h * MARGE), int(l * MARGE)
    centre = recadrage[dy:h - dy, dx:l - dx]
    if centre.shape[0] < BANDES or centre.size == 0:
        return None
    hauteur = centre.shape[0]
    morceaux = []
    for i in range(BANDES):
        histogramme = _histogramme(centre[i * hauteur // BANDES:(i + 1) * hauteur // BANDES])
        if histogramme is None:
            return None
        morceaux.append(histogramme)
    return (np.concatenate(morceaux) / np.sqrt(BANDES)).astype(np.float32)


def _histogramme(centre: np.ndarray) -> np.ndarray | None:
    import cv2

    if centre.size == 0:
        return None
    hsv = cv2.cvtColor(centre, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)
    teinte, saturation, valeur = hsv[:, 0], hsv[:, 1], hsv[:, 2]

    colore = (saturation >= SATURATION_MIN) & (valeur >= LUMINOSITE_MIN)
    histogramme = np.zeros(DIMENSION, np.float32)
    t = np.minimum(teinte[colore] * TEINTES // 180, TEINTES - 1)
    s = np.minimum((saturation[colore] - SATURATION_MIN) * SATURATIONS // (256 - SATURATION_MIN), SATURATIONS - 1)
    np.add.at(histogramme, t * SATURATIONS + s, 1.0)
    v = np.minimum(valeur[~colore] * LUMINOSITES // 256, LUMINOSITES - 1)
    np.add.at(histogramme, TEINTES * SATURATIONS + v, 1.0)

    total = histogramme.sum()
    if total <= 0:
        return None
    vecteur = np.sqrt(histogramme / total)   # norme 1 : la somme des carrés vaut 1
    return vecteur.astype(np.float32)


def similarite_couleur(a: np.ndarray, b: np.ndarray) -> float:
    """Entre 0 (aucune couleur commune) et 1 (même répartition de couleurs)."""
    return float(np.clip(a @ b, 0.0, 1.0))


def fusionner(similarite_dino: np.ndarray, similarite_coul: np.ndarray, poids: float) -> np.ndarray:
    """Note combinée : (1 - poids) x DINOv2 + poids x couleur. Fonctionne sur des tableaux de même forme."""
    return (1.0 - poids) * similarite_dino + poids * similarite_coul
