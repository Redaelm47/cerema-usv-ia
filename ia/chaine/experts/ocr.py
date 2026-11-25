"""Expert OCR : localise le texte sur le navire puis le lit, avec les modèles mobiles de PaddleOCR.

Les deux modèles tournent sur ONNX Runtime ; les traitements avant et après sont réécrits ici avec
NumPy et OpenCV, sans PaddlePaddle. La lecture est ensuite contrôlée (format français) et votée sur
plusieurs images de la même piste, voir `immatriculation.py`.
"""
import math
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from ..fiche import FicheNavire
from ..reglages import Reglages
from .base import Image, Resultat, recadrer
from .immatriculation import Vote, interpreter

MODELES = Path(__file__).resolve().parent.parent / "modeles"
CARACTERES_ADMIS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .-")


@dataclass
class Texte:
    texte: str
    confiance: float                   # moyenne des probabilités des caractères
    boite: tuple[float, float, float, float]  # x, y, largeur, hauteur dans l'image lue


def session(chemin: Path, fils: int | None) -> ort.InferenceSession:
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} manquant : lancer python3 -m chaine.outils.telecharger_modeles")
    options = ort.SessionOptions()
    if fils:
        options.intra_op_num_threads = fils
    return ort.InferenceSession(str(chemin), options, providers=["CPUExecutionProvider"])


class LecteurDeTexte:
    """Localisation (DBNet) puis lecture (CRNN, décodage CTC) du texte d'une image."""

    def __init__(self, dossier: Path = MODELES, fils: int | None = None, cote_min: int = 736, cote_max: int = 1920,
                 seuil_carte: float = 0.3, seuil_zone: float = 0.5, elargissement: float = 1.6, max_zones: int = 8,
                 fichier_detection: str = "ocr_detection.onnx", fichier_lecture: str = "ocr_lecture.onnx"):
        # Fichiers relatifs à `dossier`, ou chemins absolus : d'autres modèles PaddleOCR au même format
        # (PP-OCRv5, PP-OCRv6, exports RapidOCR avec le dictionnaire dans les métadonnées) se branchent ici.
        self.detection = session(dossier / fichier_detection, fils)
        self.lecture = session(dossier / fichier_lecture, fils)
        self.cote_min, self.cote_max = cote_min, cote_max
        self.seuil_carte, self.seuil_zone = seuil_carte, seuil_zone
        self.elargissement = elargissement
        self.max_zones = max_zones
        # Sortie du modèle de lecture : 0 = vide (CTC), puis les caractères du dictionnaire, puis l'espace.
        dictionnaire = self.lecture.get_modelmeta().custom_metadata_map["character"].rstrip("\n").split("\n")
        self.caracteres = [""] + dictionnaire + [" "]
        sortie = self.lecture.get_outputs()[0].shape[-1]
        if isinstance(sortie, int) and sortie != len(self.caracteres):
            raise ValueError(f"{fichier_lecture} : {sortie} sorties pour {len(self.caracteres)} caractères")
        self.admis = np.array([i == 0 or c in CARACTERES_ADMIS for i, c in enumerate(self.caracteres)])
        self.durees_ms = {"detection": 0.0, "lecture": 0.0}

    def lire(self, image: Image) -> list[Texte]:
        debut = time.perf_counter()
        zones = self.localiser(image)
        milieu = time.perf_counter()
        textes = []
        for coins in zones:
            texte, confiance = self.lire_zone(image, coins)
            if texte.strip():
                x, y, largeur, hauteur = cv2.boundingRect(coins.astype(np.float32))
                textes.append(Texte(texte.strip(), confiance, (x, y, largeur, hauteur)))
        self.durees_ms = {"detection": (milieu - debut) * 1000, "lecture": (time.perf_counter() - milieu) * 1000}
        return textes

    def localiser(self, image: Image) -> list[np.ndarray]:
        """Zones de texte, chacune par ses quatre coins (haut gauche, haut droit, bas droit, bas gauche)."""
        hauteur, largeur = image.shape[:2]
        grand_cote = max(hauteur, largeur)
        echelle = min(max(grand_cote, self.cote_min), self.cote_max) / grand_cote
        l = max(int(round(largeur * echelle / 32)) * 32, 32)
        h = max(int(round(hauteur * echelle / 32)) * 32, 32)
        entree = cv2.resize(image, (l, h)).astype(np.float32) / 255.0
        entree = (entree - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
        entree = entree.transpose(2, 0, 1)[None].astype(np.float32)
        carte = self.detection.run(None, {self.detection.get_inputs()[0].name: entree})[0][0, 0]

        zones = []
        contours, _ = cv2.findContours((carte > self.seuil_carte).astype(np.uint8), cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            (cx, cy), (a, b), angle = cv2.minAreaRect(contour)
            if min(a, b) < 3:
                continue
            masque = np.zeros(carte.shape, np.uint8)
            cv2.fillPoly(masque, [contour], 1)
            score = cv2.mean(carte, masque)[0]
            if score < self.seuil_zone:
                continue
            # La carte ne couvre que le cœur du texte : on élargit le rectangle, comme le fait DBNet.
            marge = a * b * self.elargissement / (2 * (a + b))
            coins = cv2.boxPoints(((cx, cy), (a + 2 * marge, b + 2 * marge), angle))
            coins = ordonner(coins) * (largeur / l, hauteur / h)
            zones.append((score * a * b, coins))
        zones.sort(key=lambda z: -z[0])
        return [coins for _, coins in zones[:self.max_zones]]

    def lire_zone(self, image: Image, coins: np.ndarray) -> tuple[str, float]:
        largeur = int(round(max(np.linalg.norm(coins[0] - coins[1]), np.linalg.norm(coins[3] - coins[2]))))
        hauteur = int(round(max(np.linalg.norm(coins[0] - coins[3]), np.linalg.norm(coins[1] - coins[2]))))
        if largeur < 4 or hauteur < 4:
            return "", 0.0
        arrivee = np.float32([[0, 0], [largeur, 0], [largeur, hauteur], [0, hauteur]])
        zone = cv2.warpPerspective(image, cv2.getPerspectiveTransform(coins.astype(np.float32), arrivee),
                                   (largeur, hauteur), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if hauteur >= 1.5 * largeur:  # texte vertical
            zone = np.rot90(zone)
            largeur, hauteur = hauteur, largeur
        l = min(max(math.ceil(48 * largeur / hauteur), 16), 640)
        entree = cv2.resize(zone, (l, 48)).astype(np.float32) / 255.0
        entree = ((entree - 0.5) / 0.5).transpose(2, 0, 1)[None]
        probabilites = self.lecture.run(None, {self.lecture.get_inputs()[0].name: entree})[0][0]
        probabilites = probabilites * self.admis  # décodage restreint aux caractères d'une immatriculation
        indices, valeurs = probabilites.argmax(axis=1), probabilites.max(axis=1)
        texte, confiances, precedent = "", [], 0
        for indice, valeur in zip(indices, valeurs):
            if indice != 0 and indice != precedent:
                texte += self.caracteres[indice]
                confiances.append(float(valeur))
            precedent = indice
        return texte, float(np.mean(confiances)) if confiances else 0.0


def ordonner(coins: np.ndarray) -> np.ndarray:
    """Range quatre coins dans l'ordre haut gauche, haut droit, bas droit, bas gauche."""
    coins = coins[np.argsort(coins[:, 0])]
    gauche, droite = coins[:2], coins[2:]
    gauche = gauche[np.argsort(gauche[:, 1])]
    droite = droite[np.argsort(droite[:, 1])]
    return np.array([gauche[0], droite[0], droite[1], gauche[1]], dtype=np.float32)


def assembler(textes: list[Texte]) -> list[tuple[str, float]]:
    """Textes candidats : chaque zone seule, et chaque paire de zones voisines sur la même ligne.

    Le quartier et le numéro sont parfois peints assez loin l'un de l'autre pour former deux zones.
    """
    candidats = [(t.texte, t.confiance) for t in textes]
    for gauche in textes:
        for droite in textes:
            xg, yg, lg, hg = gauche.boite
            xd, yd, ld, hd = droite.boite
            recouvrement = min(yg + hg, yd + hd) - max(yg, yd)
            if gauche is not droite and xd > xg and recouvrement > 0.5 * min(hg, hd) and xd - (xg + lg) < 3 * hg:
                candidats.append((gauche.texte + " " + droite.texte, min(gauche.confiance, droite.confiance)))
    return candidats


class ExpertOCR:
    nom = "ocr"

    def __init__(self, reglages: Reglages, dossier: Path = MODELES, fils: int | None = None, marge: float = 0.03,
                 fichier_detection: str = "ocr_detection.onnx", fichier_lecture: str = "ocr_lecture.onnx"):
        self.reglages = reglages
        self.lecteur = LecteurDeTexte(dossier, fils, fichier_detection=fichier_detection,
                                      fichier_lecture=fichier_lecture)
        self.marge = marge
        self.votes: dict[int, Vote] = {}

    def lire_immatriculation(self, image: Image) -> tuple[str | None, float, list[Texte]]:
        """Meilleure immatriculation au format français lue sur l'image, avec sa confiance."""
        textes = self.lecteur.lire(image)
        meilleure, meilleure_confiance = None, 0.0
        for texte, confiance in assembler(textes):
            lecture = interpreter(texte)
            if lecture is not None and confiance * lecture.poids > meilleure_confiance:
                meilleure, meilleure_confiance = lecture.texte, confiance * lecture.poids
        return meilleure, meilleure_confiance, textes

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        return self.lire_recadrage(fiche, recadrer(image, fiche.suivi.boite, self.marge))

    def lire_recadrage(self, fiche: FicheNavire, recadrage: Image) -> Resultat:
        """Lit un recadrage du navire déjà fait : la chaîne s'en sert pour donner l'image la plus nette."""
        lecture, confiance, textes = self.lire_immatriculation(recadrage)
        valeurs = {"textes": [t.texte for t in textes],
                   "hors_format": [t.texte for t in textes if interpreter(t.texte) is None],
                   "detection_ms": round(self.lecteur.durees_ms["detection"], 1),
                   "lecture_ms": round(self.lecteur.durees_ms["lecture"], 1)}
        vote = self.votes.setdefault(fiche.id_piste, Vote())
        if lecture is not None:
            vote.ajouter(lecture, confiance)
        r = self.reglages
        candidate, confiance_vote, validee = vote.resultat(r.lectures_pour_valider, r.part_min_vote)
        valeurs.update(lue=lecture, candidate=candidate, confiance=round(confiance_vote, 3),
                       lectures=len(vote.lectures))
        if not validee:
            valeurs["raison"] = "aucune immatriculation au format" if candidate is None else "vote en cours"
            return Resultat(False, valeurs)
        return Resultat(True, {"immatriculation": candidate, **valeurs})

    def oublier(self, id_piste: int) -> None:
        self.votes.pop(id_piste, None)

    def renommer(self, ancien: int, nouveau: int) -> None:
        if ancien in self.votes:
            self.votes[nouveau] = self.votes.pop(ancien)
