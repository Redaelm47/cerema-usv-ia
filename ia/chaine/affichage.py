"""Vidéo annotée : dessine sur chaque image la boîte et la fiche de chaque navire suivi."""
import cv2

from .fiche import Etat, FicheNavire

COULEURS = {  # BGR
    Etat.NOUVELLE: (160, 160, 160),
    Etat.CONFIRMEE: (235, 150, 40),
    Etat.EN_APPROCHE: (0, 140, 255),
    Etat.ALERTEE: (80, 190, 60),
    Etat.PERDUE: (120, 120, 120),
}


class VideoAnnotee:
    def __init__(self, chemin: str, images_par_s: float = 25.0):
        self.chemin = chemin
        self.images_par_s = images_par_s
        self._ecrivain = None

    def _texte(self, image, texte: str, origine: tuple[int, int], couleur, echelle: float) -> None:
        cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * echelle, (0, 0, 0),
                    max(int(4 * echelle), 2), cv2.LINE_AA)
        cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * echelle, couleur,
                    max(int(1.5 * echelle), 1), cv2.LINE_AA)

    def ecrire(self, image, fiches: list[FicheNavire], t: float, drone=None) -> None:
        image = image.copy()
        echelle = max(image.shape[1] / 1280, 0.5)
        for fiche in fiches:
            if fiche.suivi.derniere_vue != t:
                continue
            x, y, largeur, hauteur = (int(v) for v in fiche.suivi.boite)
            couleur = COULEURS[fiche.decision.etat]
            cv2.rectangle(image, (x, y), (x + largeur, y + hauteur), couleur, max(int(2 * echelle), 1))
            experts = fiche.experts
            lignes = [f"#{fiche.id_piste} {fiche.decision.etat.value}  {largeur} px",
                      f"type: {'/'.join(experts.types) or '?'}   immat: {experts.immatriculation or '?'}"]
            for i, texte in enumerate(reversed(lignes)):
                origine = (x, max(y - int((8 + 22 * i) * echelle), int(20 * echelle)))
                self._texte(image, texte, origine, couleur, echelle)
        if drone is not None:
            bandeau = f"t {t:5.1f} s   {drone.mode}   batterie {drone.batterie:.0%}"
            if drone.distance_m is not None:
                bandeau += f"   distance {drone.distance_m:.0f} m"
            self._texte(image, bandeau, (int(12 * echelle), int(26 * echelle)), (255, 255, 255), echelle)
        if self._ecrivain is None:
            hauteur_image, largeur_image = image.shape[:2]
            self._ecrivain = cv2.VideoWriter(self.chemin, cv2.VideoWriter_fourcc(*"mp4v"), self.images_par_s,
                                             (largeur_image, hauteur_image))
        self._ecrivain.write(image)

    def fermer(self) -> None:
        if self._ecrivain is not None:
            self._ecrivain.release()
