import unittest

import cv2
import numpy as np

from chaine.experts.qualite import FiltreQualite
from chaine.reglages import Reglages

from .outils import fiche_confirmee


def image_nette(largeur=600, hauteur=200):
    """Damier fin et texte : beaucoup de contours."""
    image = np.full((hauteur, largeur, 3), 60, np.uint8)
    image[::8, :] = 200
    image[:, ::8] = 200
    cv2.putText(image, "GV 123456", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4)
    return image


def lancer(image, reglages=None):
    fiche = fiche_confirmee()
    fiche.suivi.boite = (0.0, 0.0, float(image.shape[1]), float(image.shape[0]))
    return FiltreQualite(reglages or Reglages()).lancer(fiche, image)


class TestFiltreQualite(unittest.TestCase):
    def test_image_nette_acceptee(self):
        resultat = lancer(image_nette())
        self.assertTrue(resultat.reussi)
        self.assertGreater(resultat.valeurs["nettete"], Reglages().nettete_min)

    def test_image_floue_rejetee(self):
        resultat = lancer(cv2.GaussianBlur(image_nette(), (0, 0), 6))
        self.assertFalse(resultat.reussi)
        self.assertEqual(resultat.valeurs["raison"], "image floue")

    def test_la_nettete_baisse_avec_le_flou(self):
        nettetes = [lancer(cv2.GaussianBlur(image_nette(), (0, 0), s) if s else image_nette()).valeurs["nettete"]
                    for s in (0, 1, 2, 4)]
        self.assertEqual(nettetes, sorted(nettetes, reverse=True))

    def test_image_unie_rejetee(self):
        resultat = lancer(np.full((200, 600, 3), 128, np.uint8))
        self.assertEqual((resultat.reussi, resultat.valeurs["raison"]), (False, "contraste trop faible"))

    def test_recadrage_trop_petit_rejete(self):
        resultat = lancer(image_nette(40, 10))
        self.assertEqual((resultat.reussi, resultat.valeurs["raison"]), (False, "recadrage trop petit"))

    def test_boite_hors_de_l_image(self):
        fiche = fiche_confirmee()
        fiche.suivi.boite = (5000.0, 5000.0, 300.0, 100.0)
        self.assertFalse(FiltreQualite(Reglages()).lancer(fiche, image_nette()).reussi)

    def test_grande_image_mesuree_a_taille_reduite(self):
        self.assertTrue(lancer(cv2.resize(image_nette(), (2400, 800), interpolation=cv2.INTER_NEAREST)).reussi)


if __name__ == "__main__":
    unittest.main()
