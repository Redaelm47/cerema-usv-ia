"""Seuils de la chaîne et état du drone. Valeurs de départ, à ajuster sur les essais."""
from dataclasses import dataclass


@dataclass
class Reglages:
    # Suivi
    images_confirmation: int = 3        # images d'affilée avant de confirmer une piste
    duree_confirmation_s: float = 0.2   # et durée minimale de la piste (à 50 images/s, trois images ne suffisent pas)
    confiance_confirmation: float = 0.3 # confiance minimale de la détection pour confirmer
    delai_perte_s: float = 5.0          # sans observation pendant ce délai, la piste est perdue
    delai_reprise_s: float = 2.0        # un nouveau numéro au même endroit dans ce délai reprend la fiche
    recouvrement_reprise: float = 0.3   # recouvrement minimal des boîtes (intersection sur union)
    delai_oubli_s: float = 60.0         # une fiche perdue ou alertée, plus vue depuis ce délai, est effacée

    # Décideur
    largeur_min_type_px: float = 64.0   # en dessous, le navire est trop petit pour être classé
    seuil_ocr_px: float = 600.0         # largeur du navire à partir de laquelle on tente de lire
    max_tentatives_type: int = 2
    essais_pour_ecarter: int = 2        # essais de l'expert type qui doivent dire « pas un navire » avant d'écarter la piste
    max_tentatives_ocr: int = 6
    intervalle_essais_s: float = 0.4    # entre deux essais du même expert sur le même navire
    croissance_nouvel_essai_type: float = 1.5  # type hésitant : nouvel essai si le navire a grossi d'autant
    max_approches: int = 1              # pas de seconde approche sur le même navire

    # Filtre qualité
    nettete_min: float = 40.0           # variance du laplacien en dessous de laquelle l'image est floue
    contraste_min: float = 8.0          # écart-type des niveaux de gris
    cote_min_px: int = 16               # plus petit côté du recadrage
    max_rejets_qualite: int = 5         # rejets d'affilée qui comptent pour une tentative ratée

    # Expert OCR : vote sur plusieurs images de la même piste
    lectures_pour_valider: int = 2      # lectures identiques demandées, sur des images différentes
    part_min_vote: float = 0.6          # part minimale du caractère gagnant, à chaque position
    lectures_texte_hors_format: int = 2 # un texte lu autant de fois, sans être une immatriculation, est transmis
    max_textes_alerte: int = 3          # nombre de textes hors format joints à une alerte

    # Garde-fous de l'approche
    duree_max_approche_s: float = 120.0
    batterie_min_approche: float = 0.3  # part de batterie en dessous de laquelle on n'approche plus
    energie_max_approche: float = 0.10  # part de batterie qu'une approche peut consommer
    distance_min_m: float = 30.0        # distance au navire jamais franchie
    delai_eloignement_s: float = 20.0   # après ce délai d'approche, le navire doit avoir grossi
    croissance_min_approche: float = 1.05

    # Caméra, pour estimer cap et distance
    champ_horizontal_deg: float = 66.0
    largeur_image_px: int = 4056        # utilisée quand aucune image n'est fournie

    # Messages
    periode_etat_s: float = 1.0         # un message d'état du drone par période


@dataclass
class Contexte:
    """État du drone au moment de décider. Simulé pour l'instant, plus tard lu sur l'autopilote (MAVLink)."""
    batterie: float = 1.0               # entre 0 et 1
    dans_la_zone: bool = True           # le drone est dans la zone autorisée
    mode: str = "patrouille"            # patrouille ou approche
    cible: int | None = None            # numéro de la piste approchée
    distance_m: float | None = None     # distance estimée au navire approché
    temperature_pi: float | None = None
