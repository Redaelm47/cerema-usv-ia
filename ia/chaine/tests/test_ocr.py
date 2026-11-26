import random
import unittest

import cv2
import numpy as np

from chaine.experts.ocr import MODELES, ExpertOCR, Texte, assembler, ordonner
from chaine.outils.immatriculations_synthetiques import dessiner
from chaine.reglages import Reglages

from .outils import fiche_confirmee

MODELES_PRESENTS = (MODELES / "ocr_detection.onnx").exists() and (MODELES / "ocr_lecture.onnx").exists()


def fiche_sur(image, id_piste=1):
    fiche = fiche_confirmee(id_piste=id_piste)
    fiche.suivi.boite = (0.0, 0.0, float(image.shape[1]), float(image.shape[0]))
    return fiche


class TestAssemblage(unittest.TestCase):
    def test_coins_ordonnes(self):
        coins = np.float32([[90, 40], [10, 12], [90, 10], [10, 42]])
        self.assertEqual(ordonner(coins).tolist(), [[10, 12], [90, 10], [90, 40], [10, 42]])

    def test_quartier_et_numero_dans_deux_zones_voisines(self):
        textes = [Texte("123456", 0.9, (200, 100, 180, 40)), Texte("GV", 0.8, (100, 102, 60, 40)),
                  Texte("MARIE", 0.9, (100, 20, 150, 40))]
        candidats = assembler(textes)
        self.assertIn(("GV 123456", 0.8), candidats)
        self.assertNotIn("MARIE 123456", [texte for texte, _ in candidats])  # pas sur la même ligne


@unittest.skipUnless(MODELES_PRESENTS, "modèles absents : python3 -m chaine.outils.telecharger_modeles")
class TestExpertOCR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reglages = Reglages()
        cls.expert = ExpertOCR(cls.reglages)

    def setUp(self):
        self.expert.votes.clear()

    def test_lit_une_immatriculation_nette(self):
        rng = random.Random(3)
        for verite in ("GV 642410", "CC 911290", "LO 546713"):
            lue, confiance, _ = self.expert.lire_immatriculation(dessiner(verite, 28, rng, degradation=0.3))
            self.assertEqual(lue, verite)
            self.assertGreater(confiance, 0.8)

    def test_vote_sur_plusieurs_images_de_la_meme_piste(self):
        rng = random.Random(4)
        images = [dessiner("BR 304512", 24, rng, degradation=0.5) for _ in range(2)]
        premier = self.expert.lancer(fiche_sur(images[0]), images[0])
        self.assertFalse(premier.reussi)                      # une seule lecture ne suffit pas
        self.assertEqual((premier.valeurs["candidate"], premier.valeurs["raison"]), ("BR 304512", "vote en cours"))
        second = self.expert.lancer(fiche_sur(images[1]), images[1])
        self.assertTrue(second.reussi)
        self.assertEqual((second.valeurs["immatriculation"], second.valeurs["lectures"]), ("BR 304512", 2))
        self.assertGreater(second.valeurs["confiance"], 0.8)

    def test_les_votes_de_deux_pistes_ne_se_melangent_pas(self):
        rng = random.Random(5)
        a, b = dessiner("BR 304512", 24, rng, 0.5), dessiner("DK 770031", 24, rng, 0.5)
        self.expert.lancer(fiche_sur(a, 1), a)
        resultat = self.expert.lancer(fiche_sur(b, 2), b)
        self.assertEqual((resultat.reussi, resultat.valeurs["candidate"], resultat.valeurs["lectures"]),
                         (False, "DK 770031", 1))
        self.expert.oublier(1)
        self.assertNotIn(1, self.expert.votes)

    def test_texte_etranger_au_format_refuse(self):
        image = np.full((300, 900, 3), (90, 50, 20), np.uint8)
        cv2.putText(image, "D 564 MARY ANN", (60, 180), cv2.FONT_HERSHEY_DUPLEX, 2.2, (255, 255, 255), 5, cv2.LINE_AA)
        resultat = self.expert.lancer(fiche_sur(image), image)
        self.assertFalse(resultat.reussi)
        self.assertEqual(resultat.valeurs["raison"], "aucune immatriculation au format")
        self.assertTrue(any("MARY" in texte for texte in resultat.valeurs["textes"]))   # le texte est bien lu

    def test_image_sans_texte(self):
        image = np.full((300, 900, 3), (120, 110, 100), np.uint8)
        resultat = self.expert.lancer(fiche_sur(image), image)
        self.assertEqual((resultat.reussi, resultat.valeurs["textes"], resultat.valeurs["candidate"]), (False, [], None))

    def test_les_durees_sont_mesurees(self):
        image = dessiner("GV 642410", 28, random.Random(6), 0.3)
        resultat = self.expert.lancer(fiche_sur(image), image)
        self.assertGreater(resultat.valeurs["detection_ms"], 0)
        self.assertGreater(resultat.valeurs["lecture_ms"], 0)


if __name__ == "__main__":
    unittest.main()
