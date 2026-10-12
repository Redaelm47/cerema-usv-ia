"""Associateur : donne à chaque boîte détectée un numéro qui reste le même d'une image à l'autre.

Principe de ByteTrack, réécrit en NumPy pour tourner sur le Pi sans PyTorch :
- chaque piste prédit où sa boîte devrait être (position et vitesse lissée) ;
- les détections sûres sont d'abord associées aux pistes, puis les détections douteuses aux pistes restantes ;
- une détection sûre que rien n'explique ouvre une nouvelle piste ;
- une piste qui n'est plus vue reste en mémoire quelques secondes, pour reprendre son numéro si le navire revient.

L'associateur ne regarde que la position et la taille des boîtes, jamais l'apparence. Dans le doute (deux
pistes possibles pour une boîte, ou deux boîtes pour une piste), il n'associe pas : mieux vaut un numéro de
plus que deux navires sous le même numéro.
"""
from dataclasses import dataclass, field

import numpy as np

Boite = tuple[float, float, float, float]  # x, y, largeur, hauteur


@dataclass
class ReglagesSuivi:
    confiance_haute: float = 0.25     # détection sûre : peut ouvrir une piste
    confiance_basse: float = 0.05     # détection douteuse : ne peut que prolonger une piste
    memoire_s: float = 4.0            # durée pendant laquelle une piste perdue peut reprendre son numéro
    portee: float = 1.5               # écart toléré entre prédiction et détection, en tailles de boîte
    portee_par_s: float = 1.0         # ce que la portée gagne par seconde sans voir le navire
    portee_min_px: float = 40.0       # plancher de la portée : les petites boîtes sautent de plusieurs fois leur taille
    rapport_taille_max: float = 2.0   # une boîte deux fois plus grande ou plus petite n'est pas le même navire
    marge_ambiguite: float = 0.6      # un second candidat à moins de 1/0,6 fois la distance du premier : doute
    recouvrement_min: float = 0.2      # en dessous, on ne compte que sur la distance des centres
    duree_doublon_s: float = 1.0      # pas de nouvelle piste sur un navire suivi il y a moins longtemps que cela
    images_doublon: int = 5           # images d'affilée sous une piste plus sûre avant d'être supprimée
    duree_prediction_s: float = 0.5   # durée pendant laquelle une piste perdue continue sur sa lancée
    lissage_vitesse: float = 0.3


@dataclass
class Piste:
    id_piste: int
    boite: Boite
    confiance: float
    vue: float                                   # date de la dernière détection
    vitesse: np.ndarray = field(default_factory=lambda: np.zeros(2))  # pixels par seconde
    centre_predit: np.ndarray | None = None
    cachee: int = 0                              # images d'affilée passées sous une piste plus sûre

    @property
    def centre(self) -> np.ndarray:
        x, y, l, h = self.boite
        return np.array([x + l / 2, y + h / 2])

    @property
    def taille(self) -> float:
        return float(np.hypot(self.boite[2], self.boite[3]))


class Associateur:
    def __init__(self, reglages: ReglagesSuivi | None = None):
        self.reglages = reglages or ReglagesSuivi()
        self.pistes: list[Piste] = []
        self._prochain = 1
        self._t: float | None = None

    def mettre_a_jour(self, detections: list[tuple[float, float, float, float, float]], t: float) -> list[Piste]:
        """Détections (x, y, largeur, hauteur, confiance) de l'image à la date `t` -> pistes vues sur cette image."""
        r = self.reglages
        dt = 0.0 if self._t is None else max(t - self._t, 0.0)
        self._t = t
        self.pistes = [p for p in self.pistes if t - p.vue <= r.memoire_s]
        for piste in self.pistes:
            # Une piste perdue depuis plus d'une demi-seconde n'avance plus : sa dernière vitesse est devenue
            # fausse. C'est la portée, qui grandit avec le temps, qui couvre son déplacement.
            if t - piste.vue <= r.duree_prediction_s:
                piste.centre_predit = piste.centre_predit + piste.vitesse * dt

        sures = [d for d in detections if d[4] >= r.confiance_haute]
        douteuses = [d for d in detections if r.confiance_basse <= d[4] < r.confiance_haute]
        libres = list(self.pistes)
        vues: list[Piste] = []
        for groupe in (sures, douteuses):
            paires, restantes = self._associer(libres, groupe, t)
            for piste, detection in paires:
                self._observer(piste, detection, t)
                libres.remove(piste)
                vues.append(piste)
            if groupe is sures:
                for detection in restantes:
                    recentes = [p for p in self.pistes if t - p.vue <= r.duree_doublon_s]
                    if self._seule(detection, recentes, sures):
                        piste = Piste(self._prochain, tuple(detection[:4]), detection[4], t)
                        piste.centre_predit = piste.centre
                        self._prochain += 1
                        self.pistes.append(piste)
                        vues.append(piste)
        return self._sans_doublons(vues)

    def _sans_doublons(self, vues: list[Piste]) -> list[Piste]:
        """Deux pistes posées l'une sur l'autre : seule la plus sûre est rendue.

        La moins sûre est supprimée si cela dure. Si c'étaient deux navires l'un devant l'autre, celui de
        derrière recevra un nouveau numéro en réapparaissant : un doublon, jamais une fusion.
        """
        rendues = []
        for piste in vues:
            cachee = any(autre is not piste and autre.confiance > piste.confiance
                         and max(part_couverte(piste.boite, autre.boite), part_couverte(autre.boite, piste.boite)) >= 0.5
                         for autre in vues)
            piste.cachee = piste.cachee + 1 if cachee else 0
            if not cachee:
                rendues.append(piste)
            elif piste.cachee >= self.reglages.images_doublon:
                self.pistes.remove(piste)
        return rendues

    def _portee(self, piste: Piste, t: float) -> float:
        r = self.reglages
        return max(piste.taille, r.portee_min_px) * (r.portee + r.portee_par_s * (t - piste.vue))

    def _associer(self, pistes: list[Piste], detections: list, t: float):
        """Paires (piste, détection), de la plus sûre à la moins sûre.

        Coût d'une paire : 1 - recouvrement quand la boîte prédite et la détection se recouvrent ; sinon
        1 + écart des centres rapporté à la portée. Une paire qui se recouvre passe donc toujours avant une
        paire seulement proche. Les paires seulement proches sont refusées s'il y a un doute.
        """
        r = self.reglages
        if not pistes or not detections:
            return [], list(detections)
        couts = np.full((len(pistes), len(detections)), np.inf)
        for i, piste in enumerate(pistes):
            l0, h0 = piste.boite[2], piste.boite[3]
            predite = (piste.centre_predit[0] - l0 / 2, piste.centre_predit[1] - h0 / 2, l0, h0)
            portee = self._portee(piste, t)
            for j, (x, y, l, h, _) in enumerate(detections):
                rapport = np.hypot(l, h) / max(piste.taille, 1e-6)
                if not 1 / r.rapport_taille_max <= rapport <= r.rapport_taille_max:
                    continue
                commun = recouvrement(predite, (x, y, l, h))
                ecart = np.linalg.norm(np.array([x + l / 2, y + h / 2]) - piste.centre_predit)
                if commun >= r.recouvrement_min:
                    couts[i, j] = 1 - commun
                elif ecart <= portee:
                    couts[i, j] = 1 + ecart / portee
        paires, pistes_prises, detections_prises = [], set(), set()
        for i, j in sorted(zip(*np.nonzero(np.isfinite(couts))), key=lambda ij: couts[ij]):
            if i in pistes_prises or j in detections_prises:
                continue
            pistes_prises.add(i)
            detections_prises.add(j)
            if couts[i, j] >= 1:
                # Doute : une autre piste libre, ou une autre détection libre, presque aussi proche.
                # Ni l'une ni l'autre n'est associée : la piste attend une image plus claire.
                autres = [couts[k, j] for k in range(len(pistes)) if k not in pistes_prises] + \
                         [couts[i, k] for k in range(len(detections)) if k not in detections_prises]
                if any(couts[i, j] - 1 > r.marge_ambiguite * (autre - 1) for autre in autres if np.isfinite(autre)):
                    continue
            paires.append((pistes[i], detections[j]))
        restantes = [d for j, d in enumerate(detections) if j not in detections_prises]
        return paires, restantes

    def _seule(self, detection, vues: list[Piste], sures: list) -> bool:
        """Une nouvelle piste ne s'ouvre pas sur une boîte posée sur un navire déjà suivi ou déjà détecté.

        Le détecteur rend parfois une seconde boîte sur une partie du même navire (la cabine, la proue).
        """
        def chevauche(autre: Boite) -> bool:
            return part_couverte(detection[:4], autre) >= 0.5 or part_couverte(autre, detection[:4]) >= 0.5
        if any(chevauche(piste.boite) for piste in vues):
            return False
        return not any(autre is not detection and autre[4] > detection[4] and chevauche(autre[:4]) for autre in sures)

    def _observer(self, piste: Piste, detection, t: float) -> None:
        r = self.reglages
        x, y, l, h, confiance = detection
        centre = np.array([x + l / 2, y + h / 2])
        duree = t - piste.vue
        if duree > 0:
            vitesse = (centre - piste.centre) / duree
            piste.vitesse = (1 - r.lissage_vitesse) * piste.vitesse + r.lissage_vitesse * vitesse
        piste.boite, piste.confiance, piste.vue, piste.centre_predit = (x, y, l, h), confiance, t, centre


def recouvrement(a: Boite, b: Boite) -> float:
    """Part commune de deux boîtes (intersection sur union)."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    commun = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
    union = a[2] * a[3] + b[2] * b[3] - commun
    return commun / union if union > 0 else 0.0


def part_couverte(a: Boite, b: Boite) -> float:
    """Part de la boîte `a` qui se trouve dans la boîte `b`."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    aire = a[2] * a[3]
    return max(x1 - x0, 0.0) * max(y1 - y0, 0.0) / aire if aire > 0 else 0.0
