"""Ré-identification : reconnaître un navire déjà signalé pendant la mission (ou une mission précédente).

Le suivi donne un numéro de piste par navire, mais un navire masqué, sorti du champ ou revu plus tard
revient sous un nouveau numéro. La mémoire des navires garde, pour chaque navire déjà alerté, son
immatriculation (si elle a été lue), ses types et quelques signatures visuelles (les vecteurs de 768
nombres que l'expert type calcule déjà avec DINOv2, sans calcul supplémentaire).

Principe de prudence, repris de ARCHITECTURE.md : l'apparence seule ne prouve pas l'identité (deux
fileyeurs bleus se ressemblent trop). La ré-identification ne fusionne donc JAMAIS deux fiches et ne
remplace jamais l'OCR. Elle sert à trois choses :

1. **Signaler** : l'alerte d'un navire ressemblant à un navire déjà signalé porte un champ `deja_vu`
   (immatriculation probable, similarité, niveau de certitude). L'opérateur voit « probablement GV 642410 ».
2. **Lire moins** : si l'OCR lit une fois exactement l'immatriculation que la ressemblance propose, deux
   indices indépendants concordent : une seule lecture suffit au lieu de deux.
3. **Ne pas réapprocher** : un navire trop petit pour être lu, reconnu avec certitude comme un navire
   déjà identifié, reçoit une alerte partielle sans nouvelle approche (option, voir `Reglages`).

Et une vérification dans l'autre sens : une immatriculation lue sur un navire qui ne ressemble pas du
tout au navire qui portait la même immatriculation est signalée (`apparence_coherente: false`).

Ce module ne dépend que de NumPy : il se teste sans modèle ni image.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .indices import (Mesure, accord_fragments, accord_noms, classer_textes, longueurs_incompatibles,
                      trajet_impossible)

PROBABLE = "probable"
SUR = "sur"
IMMATRICULATION = "immatriculation"


@dataclass
class ReglagesReid:
    """Seuils de la ré-identification. Valeurs de départ tirées de la mesure de ARCHITECTURE.md
    (25 photos de navires de pêche, une vue contre une vue) : à recaler avec `outils/mesurer_reid.py`."""
    seuil_probable: float = 0.85      # 82 % des paires du même navire, 1 % de paires de navires différents
    seuil_sur: float = 0.90           # aucune confusion mesurée, 55 % des paires du même navire
    marge: float = 0.03               # écart minimal avec le meilleur navire d'une AUTRE identité
    seuil_incoherence: float = 0.60   # sous ce seuil, même immatriculation mais apparence incompatible
    largeur_min_px: float = 80.0      # recadrage plus petit : signature trop pauvre, non gardée
    signatures_par_piste: int = 8     # signatures gardées pour une piste en cours
    signatures_par_navire: int = 12   # signatures gardées pour un navire en mémoire
    redondance: float = 0.97          # une signature aussi proche d'une signature gardée n'apporte rien
    max_navires: int = 500            # au-delà, le navire vu le moins récemment est oublié

    # Indices complémentaires (indices.py). Valeurs de départ prudentes, NON recalées : à mesurer avec
    # `outils/mesurer_reid.py` sur des images de plusieurs navires avant de s'y fier.
    plancher_dino: float = 0.75       # sous cette ressemblance visuelle, aucun indice ne rattrape un candidat
    bonus_max: float = 0.08           # somme des bonus plafonnée : aucun indice, ni leur somme, ne fait un « sûr »
    couleur_centre: float = 0.85      # similarité de couleur neutre ; au-dessus bonus, en dessous malus
    couleur_gain: float = 0.5
    couleur_bonus_max: float = 0.02
    couleur_malus_max: float = 0.04   # deux navires de couleurs très différentes : on rétrograde, on n'exclut pas
    bonus_nom: float = 0.06           # même nom lu sur la coque (moitié si lu une fois)
    malus_nom: float = 0.03           # deux noms bien lus et différents
    bonus_fragment: float = 0.04      # fragment d'immatriculation compatible avec celle du navire en mémoire
    couleurs_par_piste: int = 4
    couleurs_par_navire: int = 4
    rapport_longueur_max: float = 1.8 # longueurs minimales plus éloignées : navires différents
    vitesse_max_m_s: float = 20.0     # vitesse qu'un navire ne dépasse pas (environ 40 nœuds)


@dataclass
class NavireConnu:
    numero: int                        # numéro propre à la mémoire, distinct des numéros de piste
    immatriculation: str | None
    types: list[str]
    signatures: np.ndarray             # n x d, lignes de norme 1
    premiere_alerte_t: float
    derniere_alerte_t: float
    pistes: list[int] = field(default_factory=list)
    ressemble_a: int | None = None     # navire auquel il a été trouvé identique par l'apparence seule
    # Indices complémentaires (indices.py)
    couleurs: np.ndarray | None = None  # n x d : signatures de couleur par bandes, lignes de norme 1
    noms: dict[str, int] = field(default_factory=dict)        # noms lus sur la coque, nombre de lectures
    fragments: dict[str, int] = field(default_factory=dict)   # débuts d'immatriculation mal lus
    longueur_m: float | None = None    # plus grande longueur minimale mesurée
    mesure: Mesure | None = None       # dernière position connue (mission en cours seulement)

    def resume(self) -> dict[str, Any]:
        return {"numero": self.numero, "immatriculation": self.immatriculation, "types": list(self.types),
                "signatures": int(len(self.signatures)), "premiere_alerte_t": round(self.premiere_alerte_t, 2),
                "derniere_alerte_t": round(self.derniere_alerte_t, 2), "pistes": list(self.pistes),
                "ressemble_a": self.ressemble_a, "noms": dict(self.noms), "fragments": dict(self.fragments),
                "longueur_m": None if self.longueur_m is None else round(self.longueur_m, 1),
                "couleurs": 0 if self.couleurs is None else int(len(self.couleurs))}


@dataclass
class ProfilPiste:
    """Indices complémentaires d'une piste en cours (la signature DINOv2 est dans `MemoireNavires.en_cours`)."""
    couleurs: np.ndarray | None = None
    textes: dict[str, int] = field(default_factory=dict)   # textes hors format lus sur la coque
    longueur_m: float | None = None
    mesure: Mesure | None = None


@dataclass
class Correspondance:
    """Navire de la mémoire auquel une piste ressemble."""
    navire: NavireConnu
    similarite: float                  # ressemblance visuelle corrigée par les indices (couleur, écriture)
    niveau: str                        # PROBABLE, SUR ou IMMATRICULATION
    marge: float | None = None         # écart avec le meilleur navire d'une autre identité (None : aucun autre)
    apparence_coherente: bool | None = None  # seulement au niveau IMMATRICULATION
    indices: dict[str, float] = field(default_factory=dict)  # détail : dino, couleur, nom, fragment, bonus

    def message(self) -> dict[str, Any]:
        """Champ `deja_vu` de l'alerte (ajout au contrat 3)."""
        champ = {"immatriculation": self.navire.immatriculation, "niveau": self.niveau,
                 "similarite": None if np.isnan(self.similarite) else round(float(self.similarite), 3),
                 "premiere_alerte_t": round(self.navire.premiere_alerte_t, 2)}
        if self.apparence_coherente is not None:
            champ["apparence_coherente"] = self.apparence_coherente
        return champ

    def journal(self) -> dict[str, Any]:
        return {**self.message(), "navire": self.navire.numero,
                "marge": None if self.marge is None else round(float(self.marge), 3),
                "pistes_precedentes": list(self.navire.pistes),
                "indices": {k: round(float(v), 3) for k, v in self.indices.items()}}


def normaliser(vecteur: Any) -> np.ndarray | None:
    """Vecteur 1D de norme 1, ou None s'il est vide, non fini ou nul."""
    v = np.asarray(vecteur, dtype=np.float32).reshape(-1)
    if v.size == 0 or not np.all(np.isfinite(v)):
        return None
    norme = float(np.linalg.norm(v))
    if norme < 1e-8:
        return None
    return v / norme


def similarite(requete: np.ndarray, galerie: np.ndarray) -> float:
    """Similarité d'un ensemble de vues (piste) à un autre (navire en mémoire).

    Pour chaque vue de la piste, la vue la plus proche du navire ; puis la moyenne. Prendre le maximum sur
    toutes les paires gonflerait les fausses ressemblances quand les deux ensembles grossissent.
    """
    if len(requete) == 0 or len(galerie) == 0:
        return float("nan")
    return float((requete @ galerie.T).max(axis=1).mean())


def ajouter_diverse(signatures: np.ndarray | None, nouvelle: np.ndarray, maximum: int,
                    redondance: float) -> np.ndarray:
    """Ajoute une signature à un ensemble borné, en privilégiant la diversité des vues.

    Une signature presque identique à une signature gardée est ignorée. Ensemble plein : on retire la
    signature la plus redondante (la plus proche d'une autre), ce qui garde des points de vue variés.
    """
    if signatures is None or len(signatures) == 0:
        return nouvelle[None].copy()
    if float((signatures @ nouvelle).max()) >= redondance:
        return signatures
    ensemble = np.vstack([signatures, nouvelle[None]])
    if len(ensemble) <= maximum:
        return ensemble
    proximites = ensemble @ ensemble.T
    np.fill_diagonal(proximites, -np.inf)
    return np.delete(ensemble, int(proximites.max(axis=1).argmax()), axis=0)


class MemoireNavires:
    """Les navires déjà alertés, et les signatures des pistes en cours."""

    def __init__(self, reglages: ReglagesReid | None = None):
        self.reglages = reglages or ReglagesReid()
        self.navires: dict[int, NavireConnu] = {}
        self.en_cours: dict[int, np.ndarray] = {}   # par piste : signatures accumulées
        self.profils: dict[int, ProfilPiste] = {}   # par piste : indices complémentaires
        self._prochain = 1
        self.dimension: int | None = None

    # Pistes en cours

    def ajouter_vue(self, id_piste: int, signature: Any, largeur_px: float, couleur: Any = None) -> bool:
        """Retient une signature de la piste (et sa couleur si fournie). Renvoie False si la signature est
        écartée (trop petite, invalide)."""
        r = self.reglages
        if largeur_px < r.largeur_min_px:
            return False
        v = normaliser(signature)
        if v is None:
            return False
        if self.dimension is None:
            self.dimension = int(v.size)
        elif v.size != self.dimension:
            raise ValueError(f"signature de dimension {v.size}, la mémoire attend {self.dimension}")
        self.en_cours[id_piste] = ajouter_diverse(self.en_cours.get(id_piste), v, r.signatures_par_piste,
                                                  r.redondance)
        c = normaliser(couleur) if couleur is not None else None
        if c is not None:
            profil = self.profils.setdefault(id_piste, ProfilPiste())
            if profil.couleurs is None or profil.couleurs.shape[1] == c.size:
                profil.couleurs = ajouter_diverse(profil.couleurs, c, r.couleurs_par_piste, r.redondance)
        return True

    def noter_piste(self, id_piste: int, textes: dict[str, int] | None = None, mesure: Mesure | None = None) -> None:
        """Indices de la piste : textes hors format lus sur la coque, dernière mesure de position et de taille."""
        profil = self.profils.setdefault(id_piste, ProfilPiste())
        if textes is not None:
            profil.textes = dict(textes)
        if mesure is not None:
            profil.mesure = mesure
            if mesure.longueur_m is not None:
                profil.longueur_m = max(profil.longueur_m or 0.0, mesure.longueur_m)

    def signatures(self, id_piste: int) -> np.ndarray:
        return self.en_cours.get(id_piste, np.zeros((0, self.dimension or 0), np.float32))

    def renommer(self, ancien: int, nouveau: int) -> None:
        if ancien in self.en_cours:
            self.en_cours[nouveau] = self.en_cours.pop(ancien)
        if ancien in self.profils:
            self.profils[nouveau] = self.profils.pop(ancien)

    def oublier(self, id_piste: int) -> None:
        self.en_cours.pop(id_piste, None)
        self.profils.pop(id_piste, None)

    # Indices complémentaires

    def _indices(self, profil: ProfilPiste | None, navire: NavireConnu) -> tuple[float, dict[str, float]]:
        """Correction de la ressemblance visuelle par la couleur et l'écriture, et détail de chaque indice."""
        r = self.reglages
        detail: dict[str, float] = {}
        if profil is None:
            return 0.0, detail
        bonus = 0.0
        if profil.couleurs is not None and navire.couleurs is not None \
                and profil.couleurs.shape[1] == navire.couleurs.shape[1]:
            s = similarite(profil.couleurs, navire.couleurs)
            detail["couleur"] = s
            bonus += float(np.clip((s - r.couleur_centre) * r.couleur_gain, -r.couleur_malus_max, r.couleur_bonus_max))
        noms, fragments = classer_textes(profil.textes)
        accord = accord_noms(noms, navire.noms)
        if accord:
            detail["nom"] = accord
            bonus += r.bonus_nom * accord if accord > 0 else r.malus_nom * accord
        if accord_fragments(fragments, navire.immatriculation):
            detail["fragment"] = 1.0
            bonus += r.bonus_fragment
        return min(bonus, r.bonus_max), detail

    def _exclu(self, profil: ProfilPiste | None, navire: NavireConnu) -> str | None:
        """Raison d'écarter un candidat d'après la taille réelle ou la trajectoire, None sinon."""
        if profil is None:
            return None
        r = self.reglages
        if longueurs_incompatibles(profil.longueur_m, navire.longueur_m, r.rapport_longueur_max):
            return "longueur"
        if trajet_impossible(navire.mesure, profil.mesure, r.vitesse_max_m_s):
            return "trajet"
        return None

    # Recherche

    def rechercher(self, id_piste: int, types: list[str] | None = None,
                   exclure_pistes: set[int] | frozenset[int] = frozenset()) -> Correspondance | None:
        """Navire déjà signalé auquel la piste ressemble, ou None.

        `exclure_pistes` : pistes visibles en même temps que celle-ci. Un navire de la mémoire encore suivi
        sous l'une d'elles est forcément un autre navire.
        Un navire de type certain différent est écarté. La marge se mesure contre le meilleur navire d'une
        autre identité (autre immatriculation, ou non relié par l'apparence) : si deux navires distincts
        ressemblent autant, on ne choisit pas.
        """
        r = self.reglages
        requete = self.signatures(id_piste)
        if len(requete) == 0:
            return None
        profil = self.profils.get(id_piste)
        scores = []
        for navire in self.navires.values():
            if exclure_pistes.intersection(navire.pistes) or not types_compatibles(types, navire.types):
                continue
            dino = similarite(requete, navire.signatures)
            # Les indices corrigent la ressemblance visuelle, ils ne la remplacent pas : sous le plancher, rien
            # ne rattrape un candidat. Taille et trajectoire écartent.
            if np.isnan(dino) or dino < r.plancher_dino or self._exclu(profil, navire):
                continue
            bonus, detail = self._indices(profil, navire)
            detail.update(dino=dino, bonus=bonus)
            scores.append((min(dino + bonus, 1.0), navire, detail))
        if not scores:
            return None
        scores.sort(key=lambda x: -x[0])
        meilleur_score, meilleur, detail = scores[0]
        if meilleur_score < r.seuil_probable:
            return None
        autres = [s for s, n, _ in scores[1:] if not self.meme_identite(meilleur, n)]
        marge = meilleur_score - autres[0] if autres else None
        if marge is not None and marge < r.marge:
            return None
        niveau = SUR if meilleur_score >= r.seuil_sur else PROBABLE
        return Correspondance(meilleur, meilleur_score, niveau, marge, indices=detail)

    def meme_identite(self, a: NavireConnu, b: NavireConnu) -> bool:
        if a.numero == b.numero:
            return True
        if a.immatriculation is not None and a.immatriculation == b.immatriculation:
            return True
        return a.ressemble_a == b.numero or b.ressemble_a == a.numero or (
            a.ressemble_a is not None and a.ressemble_a == b.ressemble_a)

    def par_immatriculation(self, immatriculation: str) -> NavireConnu | None:
        for navire in self.navires.values():
            if navire.immatriculation == immatriculation:
                return navire
        return None

    def verifier(self, id_piste: int, immatriculation: str) -> Correspondance | None:
        """Immatriculation lue : le navire qui la portait déjà ressemble-t-il à celui-ci ?"""
        navire = self.par_immatriculation(immatriculation)
        if navire is None:
            return None
        requete = self.signatures(id_piste)
        s = similarite(requete, navire.signatures)
        coherente = None if np.isnan(s) else bool(s >= self.reglages.seuil_incoherence)
        return Correspondance(navire, s, IMMATRICULATION, apparence_coherente=coherente)

    # Enregistrement à l'alerte

    def enregistrer(self, id_piste: int, t: float, immatriculation: str | None, types: list[str],
                    correspondance: Correspondance | None = None) -> NavireConnu | None:
        """Le navire de la piste vient d'être alerté : il entre en mémoire (ou complète son entrée).

        Une même immatriculation complète l'entrée existante. Sans immatriculation, le navire reçoit
        toujours sa propre entrée, reliée par `ressemble_a` si l'apparence l'a reconnu avec certitude :
        on ne fusionne jamais sur l'apparence. Une piste sans signature n'entre pas (rien pour la
        reconnaître), sauf si elle a une immatriculation.
        """
        r = self.reglages
        signatures = self.en_cours.pop(id_piste, None)
        profil = self.profils.pop(id_piste, None)
        if immatriculation is not None:
            navire = self.par_immatriculation(immatriculation)
            if navire is not None:
                for v in (signatures if signatures is not None else []):
                    navire.signatures = ajouter_diverse(navire.signatures, v, r.signatures_par_navire, r.redondance)
                self._completer(navire, profil)
                if len(types) == 1 or not navire.types:
                    navire.types = list(types)
                navire.derniere_alerte_t = t
                if id_piste not in navire.pistes:
                    navire.pistes.append(id_piste)
                return navire
        if signatures is None and immatriculation is None:
            return None
        lien = None
        if immatriculation is None and correspondance is not None and correspondance.niveau == SUR:
            lien = correspondance.navire.ressemble_a or correspondance.navire.numero
        vide = np.zeros((0, self.dimension or 0), np.float32)
        navire = NavireConnu(self._prochain, immatriculation, list(types),
                             signatures if signatures is not None else vide, t, t, [id_piste], lien)
        self._completer(navire, profil)
        self.navires[navire.numero] = navire
        self._prochain += 1
        self._limiter()
        return navire

    def _completer(self, navire: NavireConnu, profil: ProfilPiste | None) -> None:
        """Ajoute au navire en mémoire les indices complémentaires de la piste qui vient d'être alertée."""
        if profil is None:
            return
        r = self.reglages
        if profil.couleurs is not None:
            for c in profil.couleurs:
                if navire.couleurs is None or navire.couleurs.shape[1] == c.size:
                    navire.couleurs = ajouter_diverse(navire.couleurs, c, r.couleurs_par_navire, r.redondance)
        noms, fragments = classer_textes(profil.textes)
        for source, cible in ((noms, navire.noms), (fragments, navire.fragments)):
            for texte, n in source.items():
                cible[texte] = cible.get(texte, 0) + n
        if profil.longueur_m is not None:
            navire.longueur_m = max(navire.longueur_m or 0.0, profil.longueur_m)
        if profil.mesure is not None and (navire.mesure is None or profil.mesure.t >= navire.mesure.t):
            navire.mesure = profil.mesure

    def _limiter(self) -> None:
        while len(self.navires) > self.reglages.max_navires:
            ancien = min(self.navires.values(), key=lambda n: n.derniere_alerte_t)
            del self.navires[ancien.numero]

    def nouvelle_mission(self) -> None:
        """Mémoire rechargée d'une mission précédente : les numéros de piste et les dates ne valent plus."""
        self.en_cours.clear()
        self.profils.clear()
        for navire in self.navires.values():
            navire.pistes = []
            navire.mesure = None   # position et date d'une autre mission : repère et horloge différents

    # Sauvegarde entre deux missions

    def sauver(self, chemin: str | Path) -> None:
        """Deux fichiers : `<chemin>.json` (description lisible) et `<chemin>.npz` (signatures)."""
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        meta = {"version": 2, "dimension": self.dimension, "prochain": self._prochain,
                "navires": [n.resume() for n in self.navires.values()]}
        chemin.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tableaux = {f"n{n.numero}": n.signatures.astype(np.float32) for n in self.navires.values()}
        tableaux.update({f"c{n.numero}": n.couleurs.astype(np.float32)
                         for n in self.navires.values() if n.couleurs is not None})
        np.savez_compressed(chemin.with_suffix(".npz"), **tableaux)

    @classmethod
    def charger(cls, chemin: str | Path, reglages: ReglagesReid | None = None) -> "MemoireNavires":
        chemin = Path(chemin)
        memoire = cls(reglages)
        meta = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
        if meta.get("version") not in (1, 2):   # la version 1 n'a ni noms, ni couleurs, ni longueur
            raise ValueError(f"version de mémoire inconnue : {meta.get('version')}")
        memoire.dimension, memoire._prochain = meta["dimension"], int(meta["prochain"])
        with np.load(chemin.with_suffix(".npz")) as signatures:
            for n in meta["navires"]:
                memoire.navires[n["numero"]] = NavireConnu(
                    n["numero"], n["immatriculation"], list(n["types"]), signatures[f"n{n['numero']}"],
                    n["premiere_alerte_t"], n["derniere_alerte_t"], list(n["pistes"]), n.get("ressemble_a"),
                    couleurs=signatures[f"c{n['numero']}"] if f"c{n['numero']}" in signatures.files else None,
                    noms=dict(n.get("noms", {})), fragments=dict(n.get("fragments", {})),
                    longueur_m=n.get("longueur_m"))
        memoire.nouvelle_mission()
        return memoire


def types_compatibles(a: list[str] | None, b: list[str] | None) -> bool:
    """Incompatibles seulement si les deux types sont certains (un seul chacun) et différents."""
    return not (a and b and len(a) == 1 and len(b) == 1 and a[0] != b[0])
