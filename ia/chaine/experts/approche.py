"""Approche simulée : pas de MAVLink ni d'ArduPilot pour l'instant.

L'expert estime le cap et la distance du navire depuis l'image et donne une consigne à un drone simulé.
Le drone simulé avance vers le navire, s'arrête à la distance de sécurité et consomme sa batterie.
Les sources d'images lisent `drone.rapprochement` pour grossir le navire d'autant.
"""
import math

from ..fiche import FicheNavire
from ..reglages import Contexte, Reglages
from .base import Image, Resultat

# Longueur supposée du navire selon son type, en mètres, pour estimer la distance. Ordres de grandeur.
LONGUEUR_M = {"peche": 15.0, "chalutier": 20.0, "voilier": 10.0, "cargo": 150.0, "ferry": 120.0,
              "vedette": 10.0, "pneumatique": 6.0}
LONGUEUR_PAR_DEFAUT_M = 15.0


def temperature_pi() -> float | None:
    """Température du processeur du Raspberry Pi, None sur une autre machine."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000.0
    except (OSError, ValueError):
        return None


class DroneSimule:
    """État du drone : mode, batterie, distance au navire approché. Remplacé plus tard par l'autopilote."""

    def __init__(self, vitesse_m_s: float = 3.0, batterie: float = 1.0,
                 conso_patrouille_par_s: float = 0.00005, conso_approche_par_s: float = 0.0004):
        self.vitesse_m_s = vitesse_m_s
        self.batterie = batterie
        self.conso_patrouille_par_s = conso_patrouille_par_s
        self.conso_approche_par_s = conso_approche_par_s
        self.dans_la_zone = True
        self.cible: int | None = None          # numéro de la piste approchée
        self.distance_m: float | None = None
        self.distance_depart_m: float | None = None
        self.distance_arret_m = 0.0
        self._t: float | None = None

    @property
    def mode(self) -> str:
        return "patrouille" if self.cible is None else "approche"

    @property
    def rapprochement(self) -> float:
        """Rapport entre la distance de départ et la distance actuelle : 2 = navire deux fois plus gros."""
        if self.cible is None or not self.distance_m:
            return 1.0
        return self.distance_depart_m / self.distance_m

    def approcher(self, id_piste: int, distance_m: float, distance_arret_m: float) -> None:
        self.cible = id_piste
        self.distance_m = self.distance_depart_m = distance_m
        self.distance_arret_m = min(distance_arret_m, distance_m)

    def patrouiller(self) -> None:
        self.cible = self.distance_m = self.distance_depart_m = None

    def avancer(self, t: float) -> None:
        dt = 0.0 if self._t is None else max(t - self._t, 0.0)
        self._t = t
        if self.cible is None:
            self.batterie -= self.conso_patrouille_par_s * dt
        else:
            self.batterie -= self.conso_approche_par_s * dt
            self.distance_m = max(self.distance_m - self.vitesse_m_s * dt, self.distance_arret_m)
        self.batterie = max(self.batterie, 0.0)

    def contexte(self, t: float) -> Contexte:
        self.avancer(t)
        return Contexte(batterie=self.batterie, dans_la_zone=self.dans_la_zone, mode=self.mode, cible=self.cible,
                        distance_m=self.distance_m, temperature_pi=temperature_pi())


def estimer_cap_et_distance(fiche: FicheNavire, largeur_image_px: float, champ_horizontal_deg: float,
                            longueur_m: float) -> tuple[float, float]:
    """Cap relatif (degrés, positif à droite) et distance (mètres) du navire, par le modèle du sténopé.

    Estimation grossière : elle suppose le navire vu de côté et de longueur connue.
    """
    focale_px = (largeur_image_px / 2) / math.tan(math.radians(champ_horizontal_deg) / 2)
    x, _, largeur, _ = fiche.suivi.boite
    cap_deg = math.degrees(math.atan((x + largeur / 2 - largeur_image_px / 2) / focale_px))
    distance_m = longueur_m * focale_px / max(largeur, 1.0)
    return cap_deg, distance_m


class ExpertApprocheSimulee:
    nom = "approche"

    def __init__(self, drone: DroneSimule, reglages: Reglages):
        self.drone = drone
        self.reglages = reglages

    def lancer(self, fiche: FicheNavire, image: Image) -> Resultat:
        if self.drone.cible is not None and self.drone.cible != fiche.id_piste:
            return Resultat(False, {"raison": "une autre approche est en cours"})
        reglages = self.reglages
        largeur_image = image.shape[1] if image is not None else reglages.largeur_image_px
        types = fiche.experts.types
        longueur_m = LONGUEUR_M.get(types[0], LONGUEUR_PAR_DEFAUT_M) if types else LONGUEUR_PAR_DEFAUT_M
        cap_deg, distance_m = estimer_cap_et_distance(fiche, largeur_image, reglages.champ_horizontal_deg, longueur_m)
        # Distance à laquelle le navire atteindrait le seuil de lecture, sans jamais passer sous la distance minimale.
        distance_lecture_m = distance_m * fiche.largeur_px / (1.1 * reglages.seuil_ocr_px)
        distance_arret_m = max(distance_lecture_m, reglages.distance_min_m)
        self.drone.approcher(fiche.id_piste, distance_m, distance_arret_m)
        return Resultat(True, {"cap_relatif_deg": round(cap_deg, 1), "distance_estimee_m": round(distance_m, 1),
                               "distance_arret_m": round(distance_arret_m, 1)})

    def terminer(self, fiche: FicheNavire) -> None:
        if self.drone.cible == fiche.id_piste:
            self.drone.patrouiller()
