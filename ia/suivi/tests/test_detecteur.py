"""Profils des détecteurs et seuil de la détection sûre, sans charger de réseau."""
import unittest

from suivi.detecteur import PAR_DEFAUT, PROFILS, profil
from suivi.suivi import Suivi


class Detecteur:
    def __init__(self, confiance=None):
        if confiance is not None:
            self.confiance = confiance

    def detecter(self, image):
        return []


class TestProfils(unittest.TestCase):
    def test_best4_2_par_defaut_a_55_pourcent(self):
        p = profil(PAR_DEFAUT)
        self.assertEqual(PAR_DEFAUT, "best4_2")
        self.assertEqual((p.classes, p.confiance), ((0,), 0.55))
        self.assertTrue(p.poids.exists(), p.poids)

    def test_un_fichier_prend_le_profil_de_son_nom(self):
        self.assertEqual(profil(PROFILS["yolo11n"].poids).classes, (8,))
        self.assertEqual(profil("/ailleurs/inconnu.pt").classes, (0,))


class TestSeuilDuSuivi(unittest.TestCase):
    def test_le_detecteur_fixe_la_detection_sure(self):
        suivi = Suivi(None, Detecteur(0.55))
        self.assertEqual(suivi.associateur.reglages.confiance_haute, 0.55)
        self.assertEqual(suivi.confiance_confirmation, 0.55)

    def test_sans_profil_les_seuils_d_avant(self):
        suivi = Suivi(None, Detecteur())
        self.assertEqual(suivi.associateur.reglages.confiance_haute, 0.25)
        self.assertEqual(suivi.confiance_confirmation, 0.3)

    def test_pas_rend_le_contrat_1(self):
        suivi = Suivi(None, Detecteur(0.55))
        self.assertEqual(suivi.pas(1.0, None, [(10, 10, 50, 20, 0.9)])["pistes"][0]["id_piste"], 1)
        self.assertEqual(suivi.pas(1.2, None, [(12, 10, 50, 20, 0.5)])["pistes"][0]["id_piste"], 1)  # douteuse : prolonge
        self.assertEqual(suivi.pas(5.0, None, [(400, 10, 50, 20, 0.5)])["pistes"], [])            # douteuse : n'ouvre pas


if __name__ == "__main__":
    unittest.main()
