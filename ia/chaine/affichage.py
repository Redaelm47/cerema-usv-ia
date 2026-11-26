"""Images annotées : dessine sur chaque image la boîte et la fiche de chaque navire suivi.

`VideoAnnotee` les écrit dans un fichier, `FenetreDirecte` les montre pendant que la chaîne tourne.
"""
import cv2

from .fiche import Etat, FicheNavire

COULEURS = {  # BGR
    Etat.NOUVELLE: (160, 160, 160),
    Etat.CONFIRMEE: (235, 150, 40),
    Etat.EN_APPROCHE: (0, 140, 255),
    Etat.ALERTEE: (80, 190, 60),
    Etat.PERDUE: (120, 120, 120),
}


def _texte(image, texte: str, origine: tuple[int, int], couleur, echelle: float) -> None:
    cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * echelle, (0, 0, 0),
                max(int(4 * echelle), 2), cv2.LINE_AA)
    cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * echelle, couleur,
                max(int(1.5 * echelle), 1), cv2.LINE_AA)


def annoter(image, fiches: list[FicheNavire], t: float, drone=None):
    """Copie de l'image avec les navires vus à l'instant t et, si donné, le bandeau du drone."""
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
            _texte(image, texte, origine, couleur, echelle)
    if drone is not None:
        bandeau = f"t {t:5.1f} s   {drone.mode}   batterie {drone.batterie:.0%}"
        if drone.distance_m is not None:
            bandeau += f"   distance {drone.distance_m:.0f} m"
        _texte(image, bandeau, (int(12 * echelle), int(26 * echelle)), (255, 255, 255), echelle)
    return image


class VideoAnnotee:
    def __init__(self, chemin: str, images_par_s: float = 25.0):
        self.chemin = chemin
        self.images_par_s = images_par_s
        self._ecrivain = None

    def ecrire(self, image) -> None:
        """Écrit une image déjà annotée (voir `annoter`)."""
        if self._ecrivain is None:
            hauteur_image, largeur_image = image.shape[:2]
            self._ecrivain = cv2.VideoWriter(self.chemin, cv2.VideoWriter_fourcc(*"mp4v"), self.images_par_s,
                                             (largeur_image, hauteur_image))
        self._ecrivain.write(image)

    def fermer(self) -> None:
        if self._ecrivain is not None:
            self._ecrivain.release()


class FenetreDirecte:
    """Fenêtre OpenCV qui montre les images annotées au fil de l'eau. Ordinateur seulement (pas sur le Pi sans écran).

    Q ou Échap dans la fenêtre arrête la chaîne proprement, comme Ctrl+C.
    """
    NOM = "Chaine USV - en direct (Q pour arreter)"

    def __init__(self, largeur_max: int = 1280):
        self.largeur_max = largeur_max
        self._ouverte = False

    def montrer(self, image) -> None:
        if not self._ouverte:
            cv2.namedWindow(self.NOM, cv2.WINDOW_NORMAL)
            hauteur, largeur = image.shape[:2]
            facteur = min(1.0, self.largeur_max / largeur)
            cv2.resizeWindow(self.NOM, int(largeur * facteur), int(hauteur * facteur))
            self._ouverte = True
        cv2.imshow(self.NOM, image)
        touche = cv2.waitKey(1) & 0xFF
        fermee = cv2.getWindowProperty(self.NOM, cv2.WND_PROP_VISIBLE) < 1
        if touche in (ord("q"), ord("Q"), 27) or fermee:
            raise KeyboardInterrupt

    def fermer(self) -> None:
        if self._ouverte:
            cv2.destroyWindow(self.NOM)
            self._ouverte = False


class FluxAnnote(VideoAnnotee):
    """Vue en direct : écrit chaque image annotée en JPEG sur un flux binaire (à lire avec `ffplay -f mjpeg`)."""

    def __init__(self, flux, largeur: int = 1280, qualite: int = 75):
        super().__init__("")
        self.flux, self.largeur, self.qualite = flux, largeur, qualite

    def ecrire(self, image, fiches: list[FicheNavire], t: float, drone=None) -> None:
        image = annoter(image, fiches, t, drone)
        if image.shape[1] > self.largeur:
            echelle = self.largeur / image.shape[1]
            image = cv2.resize(image, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_AREA)
        reussi, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.qualite])
        if reussi:
            self.flux.write(jpeg.tobytes())
            self.flux.flush()
