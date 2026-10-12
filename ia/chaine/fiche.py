"""Fiche navire : ce que l'on sait d'un navire suivi. Une fiche par piste, trois blocs (contrat 2).

Chacun n'écrit que dans son bloc : `suivi` pour le suivi, `experts` et `decision` pour la chaîne.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

Boite = tuple[float, float, float, float]  # x, y, largeur, hauteur, en pixels pleine résolution


class Etat(str, Enum):
    NOUVELLE = "nouvelle"        # vue, pas encore confirmée
    CONFIRMEE = "confirmee"      # vue sur assez d'images d'affilée
    EN_APPROCHE = "en_approche"  # le drone se rapproche pour mieux voir
    ALERTEE = "alertee"          # alerte envoyée, plus rien à faire
    PERDUE = "perdue"            # plus vue depuis trop longtemps


@dataclass
class Observation:
    """Ce que le suivi fournit pour une piste sur une image (contrat 1)."""
    id_piste: int
    boite: Boite
    confiance: float


@dataclass
class Suivi:
    premiere_vue: float
    derniere_vue: float
    images_consecutives: int = 0
    boite: Boite = (0.0, 0.0, 0.0, 0.0)
    confiance: float = 0.0
    vitesse_px_s: float = 0.0    # déplacement apparent du centre de la boîte


@dataclass
class Experts:
    types: list[str] = field(default_factory=list)  # un seul élément = type connu, plusieurs = hésitation
    confiance_type: float = 0.0
    immatriculation: str | None = None
    confiance_immatriculation: float = 0.0


@dataclass
class Decision:
    etat: Etat = Etat.NOUVELLE
    tentatives: dict[str, int] = field(default_factory=dict)
    debut_approche: float | None = None


@dataclass
class Interne:
    """Mémoire de travail de la chaîne, hors contrat : écrite dans le journal, jamais envoyée."""
    dernier_essai: dict[str, float] = field(default_factory=dict)   # date du dernier essai de chaque expert
    rejets_qualite: dict[str, int] = field(default_factory=dict)    # rejets d'affilée du filtre qualité
    nettete: float | None = None
    largeur_dernier_type: float = 0.0
    textes_lus: dict[str, int] = field(default_factory=dict)  # textes lus sur la coque, et combien de fois
    lecture_candidate: str | None = None      # immatriculation lue mais pas encore validée par le vote
    confiance_candidate: float = 0.0
    largeur_debut_approche: float = 0.0
    batterie_debut_approche: float = 1.0
    consigne: dict[str, Any] | None = None    # dernière consigne d'approche


@dataclass
class FicheNavire:
    id_piste: int
    suivi: Suivi
    experts: Experts = field(default_factory=Experts)
    decision: Decision = field(default_factory=Decision)
    interne: Interne = field(default_factory=Interne)

    @classmethod
    def creer(cls, id_piste: int, t: float) -> "FicheNavire":
        return cls(id_piste, Suivi(premiere_vue=t, derniere_vue=t))

    @property
    def largeur_px(self) -> float:
        return self.suivi.boite[2]

    @property
    def type_connu(self) -> bool:
        return len(self.experts.types) == 1

    @property
    def immatriculation_connue(self) -> bool:
        return self.experts.immatriculation is not None

    def observer(self, t: float, obs: Observation) -> None:
        """Bloc suivi : nouvelle observation de la piste."""
        suivi = self.suivi
        dt = t - suivi.derniere_vue
        if dt > 0 and suivi.images_consecutives > 0:
            cx = obs.boite[0] + obs.boite[2] / 2
            cx_avant = suivi.boite[0] + suivi.boite[2] / 2
            suivi.vitesse_px_s = (cx - cx_avant) / dt
        suivi.boite = tuple(float(v) for v in obs.boite)
        suivi.confiance = float(obs.confiance)
        suivi.derniere_vue = t
        suivi.images_consecutives += 1

    def manquer(self) -> None:
        """Bloc suivi : la piste n'a pas été vue sur cette image."""
        self.suivi.images_consecutives = 0

    def contrat(self) -> dict[str, Any]:
        """La fiche au format du contrat 2."""
        s, e, d = self.suivi, self.experts, self.decision
        return {
            "id_piste": self.id_piste,
            "suivi": {
                "premiere_vue": round(s.premiere_vue, 2),
                "derniere_vue": round(s.derniere_vue, 2),
                "images_consecutives": s.images_consecutives,
                "boite": [round(v, 1) for v in s.boite],
                "confiance": round(s.confiance, 3),
                "vitesse_px_s": round(s.vitesse_px_s, 1),
            },
            "experts": {
                "types": list(e.types),
                "confiance_type": round(e.confiance_type, 3),
                "immatriculation": e.immatriculation,
                "confiance_immatriculation": round(e.confiance_immatriculation, 3),
            },
            "decision": {
                "etat": d.etat.value,
                "tentatives": dict(d.tentatives),
                "debut_approche": None if d.debut_approche is None else round(d.debut_approche, 2),
            },
        }
