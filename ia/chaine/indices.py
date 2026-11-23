"""Indices complémentaires de la ré-identification : écriture, taille réelle, trajectoire.

La signature visuelle (DINOv2) ne dit pas tout : deux fileyeurs bleus se ressemblent. Ces indices la
complètent, avec la même prudence : ils ne prouvent jamais une identité, seule l'immatriculation lue et
validée le fait. Ils jouent deux rôles :

- **score** : le nom lu sur la coque, un fragment d'immatriculation, la couleur par bandes ajoutent ou
  retirent quelques centièmes à la ressemblance (voir `ReglagesReid`, bornés pour qu'aucun ne suffise seul) ;
- **veto** : une taille réelle très différente, ou un trajet impossible depuis la dernière position connue,
  écartent un candidat.

Taille et trajectoire demandent des mesures que le drone doit fournir (`Contexte.distance_navire_m`,
`position_m`, `cap_deg`) : la distance estimée par l'approche simulée vient d'une longueur supposée par
type, elle ne peut donc pas servir à mesurer le navire (raisonnement circulaire). Sans ces mesures, ces
deux indices sont inactifs et le reste fonctionne comme avant.

Ce module ne dépend que de la bibliothèque standard : il se teste sans modèle ni image.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

FRAGMENT = re.compile(r"^([A-Z]{2})([0-9]{3,6})$")   # « BR5387 » : début d'immatriculation, lecture incomplète


def compacter(texte: str) -> str:
    """Majuscules, sans espace ni ponctuation."""
    return re.sub(r"[^A-Z0-9]", "", texte.upper())


def distance_edition(a: str, b: str) -> int:
    """Distance de Levenshtein."""
    if len(a) < len(b):
        a, b = b, a
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i]
        for j, cb in enumerate(b, 1):
            courante.append(min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (ca != cb)))
        precedente = courante
    return precedente[-1]


# Écriture

def classer_textes(textes: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
    """Textes lus sur la coque (texte -> nombre de lectures) -> (noms, fragments d'immatriculation).

    Un nom est un texte presque entièrement alphabétique d'au moins quatre caractères. Un fragment est
    deux lettres puis trois à six chiffres, sans le format complet. Le reste (« 132 », « 2 ») est ignoré.
    """
    noms: dict[str, int] = {}
    fragments: dict[str, int] = {}
    for texte, n in textes.items():
        brut = compacter(texte)
        if FRAGMENT.match(brut):
            fragments[brut] = fragments.get(brut, 0) + n
        elif len(brut) >= 4 and sum(c.isalpha() for c in brut) >= 0.8 * len(brut):
            noms[brut] = noms.get(brut, 0) + n
    return noms, fragments


def noms_proches(a: str, b: str, seuil: float = 0.8) -> bool:
    """Deux lectures du même nom : 1 - distance d'édition rapportée à la longueur, au moins `seuil`."""
    return 1.0 - distance_edition(a, b) / max(len(a), len(b)) >= seuil


def accord_noms(piste: dict[str, int], navire: dict[str, int], lectures_sures: int = 2) -> float:
    """+1 : un nom de la piste correspond à un nom du navire (0,5 si lu une seule fois côté piste) ;
    -1 : les deux côtés ont un nom lu au moins `lectures_sures` fois et aucun ne correspond ; 0 sinon."""
    if not piste or not navire:
        return 0.0
    meilleur = 0.0
    for a, na in piste.items():
        for b, nb in navire.items():
            if noms_proches(a, b):
                meilleur = max(meilleur, 1.0 if na >= lectures_sures else 0.5)
    if meilleur > 0:
        return meilleur
    sures_piste = any(n >= lectures_sures for n in piste.values())
    sures_navire = any(n >= lectures_sures for n in navire.values())
    return -1.0 if sures_piste and sures_navire else 0.0


def fragment_compatible(fragment: str, immatriculation: str | None) -> bool:
    """Le fragment (« BR5387 ») peut-il être une lecture partielle de l'immatriculation (« BR 538217 ») ?

    Mêmes deux lettres de quartier, et les chiffres lus se retrouvent dans ceux de l'immatriculation à une
    faute près. Il faut au moins quatre chiffres : avec moins, trop d'immatriculations conviendraient.
    """
    if not immatriculation:
        return False
    plaque = compacter(immatriculation)
    if len(plaque) < 8 or fragment[:2] != plaque[:2]:
        return False
    lus, chiffres = fragment[2:], plaque[2:]
    if len(lus) < 4:
        return False
    return any(distance_edition(lus, chiffres[i:i + n]) <= 1
               for n in (len(lus) - 1, len(lus), len(lus) + 1)
               for i in range(len(chiffres) - n + 1) if n > 0)


def accord_fragments(fragments: dict[str, int], immatriculation: str | None) -> float:
    """1 si un fragment lu est compatible avec l'immatriculation du navire, sinon 0. Jamais négatif : un
    fragment mal lu ne doit pas écarter le bon navire."""
    return 1.0 if any(fragment_compatible(f, immatriculation) for f in fragments) else 0.0


# Taille réelle et trajectoire

@dataclass
class Mesure:
    """Ce que l'on sait de la position et de la taille d'un navire à un instant. Champs absents : None."""
    t: float
    position_m: tuple[float, float] | None = None   # est, nord, dans un repère propre à la mission
    distance_m: float | None = None                 # distance du drone au navire
    longueur_m: float | None = None                 # largeur apparente convertie en mètres


def estimer_mesure(t: float, boite: tuple[float, float, float, float], largeur_image_px: float,
                   champ_horizontal_deg: float, position_drone_m: tuple[float, float] | None,
                   cap_drone_deg: float | None, distance_navire_m: float | None) -> Mesure:
    """Position et longueur du navire, par le modèle du sténopé, à partir d'une distance MESURÉE.

    La largeur apparente est une longueur minimale (un navire vu de biais paraît plus court). Sans
    distance mesurée, on ne sait rien de la taille ni de la position : la mesure est vide.
    """
    if not distance_navire_m or distance_navire_m <= 0:
        return Mesure(t)
    focale_px = (largeur_image_px / 2) / math.tan(math.radians(champ_horizontal_deg) / 2)
    x, _, largeur, _ = boite
    longueur = distance_navire_m * largeur / focale_px
    position = None
    if position_drone_m is not None and cap_drone_deg is not None:
        relatif = math.degrees(math.atan((x + largeur / 2 - largeur_image_px / 2) / focale_px))
        azimut = math.radians(cap_drone_deg + relatif)   # depuis le nord, dans le sens horaire
        position = (position_drone_m[0] + distance_navire_m * math.sin(azimut),
                    position_drone_m[1] + distance_navire_m * math.cos(azimut))
    return Mesure(t, position, distance_navire_m, longueur)


def longueurs_incompatibles(a: float | None, b: float | None, rapport: float = 1.8) -> bool:
    """Deux longueurs minimales dont le rapport dépasse `rapport` : deux navires de tailles différentes."""
    if not a or not b:
        return False
    return max(a, b) / min(a, b) > rapport


def trajet_impossible(ancienne: Mesure | None, nouvelle: Mesure | None, vitesse_max_m_s: float = 20.0,
                      incertitude_relative: float = 0.25, incertitude_fixe_m: float = 20.0) -> bool:
    """Le navire vu en `ancienne` peut-il être celui vu en `nouvelle` ?

    Faux (donc trajet possible) dès qu'une position manque. La marge couvre l'erreur de distance (une part
    des distances au navire) et celle de position du drone.
    """
    if ancienne is None or nouvelle is None or ancienne.position_m is None or nouvelle.position_m is None:
        return False
    dt = nouvelle.t - ancienne.t
    if dt < 0:
        return False
    ecart = math.dist(ancienne.position_m, nouvelle.position_m)
    marge = incertitude_relative * ((ancienne.distance_m or 0.0) + (nouvelle.distance_m or 0.0)) + incertitude_fixe_m
    return ecart > vitesse_max_m_s * dt + marge
