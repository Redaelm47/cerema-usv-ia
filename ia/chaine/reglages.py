"""Seuils de la chaîne et état du drone. Valeurs de départ, à ajuster sur les essais."""
from dataclasses import dataclass


@dataclass
class Reglages:
    # Suivi
    # Les experts ne partent que sur un navire détecté sûrement sur 5 images d'affilée : une vague, un caillou ou un
    # reflet ne tient pas aussi longtemps (essais de Guillaume, ia/detection/programs/test_expert_trigger.py).
    images_confirmation: int = 5        # images d'affilée, toutes sûres, avant de confirmer une piste
    duree_confirmation_s: float = 0.2   # et durée minimale de la piste (à 50 images/s, cinq images durent 0,1 s)
    confiance_confirmation: float = 0.55 # détection sûre : 55 % pour best4_2 ; le programme le règle selon le détecteur
    delai_perte_s: float = 5.0          # sans observation pendant ce délai, la piste est perdue
    delai_reprise_s: float = 2.0        # un nouveau numéro au même endroit dans ce délai reprend la fiche
    recouvrement_reprise: float = 0.3   # recouvrement minimal des boîtes (intersection sur union)
    delai_oubli_s: float = 60.0         # une fiche perdue ou alertée, plus vue depuis ce délai, est effacée

    # Décideur
    largeur_min_type_px: float = 64.0   # en dessous, le navire est trop petit pour être classé
    seuil_ocr_px: float = 600.0         # largeur du navire à partir de laquelle on tente de lire ; cible de l'approche
    # Essais précoces : on tente aussi de lire avant ce seuil, sans attendre que le navire soit gros. Sur la scène
    # Blender la plaque est lue dès ~120-145 px, soit 10 s plus tôt qu'à 300 px (jamais à 600 px sans zoom).
    seuil_ocr_essai_px: float = 120.0
    max_essais_ocr_precoces: int = 4    # budget à part : un échec sur un petit navire ne prive pas des essais à 600 px
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

    # Ré-identification (actives seulement si la chaîne a une mémoire des navires, option --reid)
    reid_eviter_reapproche: bool = True   # navire reconnu avec certitude et déjà identifié : pas de nouvelle approche
    reid_valider_une_lecture: bool = True # une lecture égale à l'immatriculation reconnue suffit au vote

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
    # Mesures facultatives du drone, pour la taille réelle et la trajectoire des navires (indices.py). Absentes
    # (None) dans la simulation : la distance estimée par l'approche vient d'une longueur supposée, elle ne mesure rien.
    position_m: tuple[float, float] | None = None   # position du drone (est, nord), repère de la mission
    cap_deg: float | None = None                    # cap du drone depuis le nord, sens horaire
    distance_navire_m: float | None = None          # distance MESURÉE au navire `cible` (radar, télémètre, AIS...)
