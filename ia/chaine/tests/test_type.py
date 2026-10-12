import tempfile
import unittest
from pathlib import Path

import numpy as np

from chaine.experts.ocr import MODELES
from chaine.experts.type import COTE, ExpertType, Tete, preparer

from .outils import fiche_confirmee

MODELES_PRESENTS = (MODELES / "dinov2_vits14.onnx").exists() and (MODELES / "tete_type_dinov2.npz").exists()


def tete(seuil=0.2):
    """Tête à trois types sur des signatures à deux nombres."""
    dossier = tempfile.mkdtemp()
    chemin = Path(dossier) / "tete_type.npz"
    np.savez(chemin, types=np.array(["peche", "voilier", "cargo"]), seuil=np.float32(seuil),
             poids=np.float32([[4, 0], [0, 4], [-4, -4]]), biais=np.zeros(3, np.float32))
    return Tete(chemin)


class TestTete(unittest.TestCase):
    def test_probabilites(self):
        p = tete().probabilites(np.float32([1, 0]))
        self.assertAlmostEqual(float(p.sum()), 1.0, places=5)
        self.assertEqual(int(p.argmax()), 0)

    def test_un_seul_type_quand_l_expert_est_sur(self):
        t = tete()
        self.assertEqual(t.ensemble(t.probabilites(np.float32([1, 0]))), ["peche"])

    def test_plusieurs_types_quand_il_hesite(self):
        t = tete()
        self.assertEqual(t.ensemble(t.probabilites(np.float32([0.5, 0.45]))), ["peche", "voilier"])

    def test_jamais_vide(self):
        t = tete(seuil=0.99)
        self.assertEqual(t.ensemble(t.probabilites(np.float32([0.5, 0.45]))), ["peche"])

    def test_tete_absente(self):
        with self.assertRaises(FileNotFoundError):
            Tete(Path("/nulle/part/tete_type.npz"))


class TestPreparation(unittest.TestCase):
    def test_navire_entier_dans_un_carre(self):
        entree = preparer(np.full((100, 400, 3), 255, np.uint8))    # recadrage quatre fois plus large que haut
        self.assertEqual(entree.shape, (1, 3, COTE, COTE))
        self.assertEqual(entree.dtype, np.float32)
        self.assertTrue((entree[0, :, :80] == 0).all())             # bandes neutres en haut et en bas
        self.assertTrue((entree[0, :, 100:124] > 1).all())          # le navire au milieu

    def test_petit_recadrage_agrandi(self):
        self.assertEqual(preparer(np.zeros((12, 30, 3), np.uint8)).shape, (1, 3, COTE, COTE))


@unittest.skipUnless(MODELES_PRESENTS, "modèles absents : telecharger_modeles puis entrainer_tete_type")
class TestExpertType(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expert = ExpertType()
        rng = np.random.default_rng(0)
        cls.image = rng.integers(0, 255, (300, 600, 3), dtype=np.uint8)

    def fiche(self, id_piste=1):
        fiche = fiche_confirmee(id_piste=id_piste)
        fiche.suivi.boite = (50.0, 50.0, 400.0, 150.0)
        return fiche

    def test_resultat_au_format_attendu(self):
        self.expert.cumuls.clear()
        resultat = self.expert.lancer(self.fiche(), self.image)
        self.assertTrue(resultat.reussi)
        types = resultat.valeurs["types"]
        self.assertGreaterEqual(len(types), 1)
        self.assertTrue(set(types) <= set(self.expert.tete.types))
        self.assertAlmostEqual(sum(resultat.valeurs["probabilites"].values()), 1.0, places=2)
        self.assertEqual(resultat.valeurs["confiance"], max(resultat.valeurs["probabilites"].values()))

    def test_signature_de_norme_1(self):
        signature = self.expert.signature.calculer(self.image)
        self.assertEqual(signature.shape, (768,))
        self.assertAlmostEqual(float(np.linalg.norm(signature)), 1.0, places=5)

    def test_moyenne_sur_les_essais_de_la_meme_piste(self):
        self.expert.cumuls.clear()
        self.expert.lancer(self.fiche(1), self.image)
        self.expert.lancer(self.fiche(1), self.image[:, ::-1].copy())
        self.assertEqual(self.expert.cumuls[1][1], 2)
        self.expert.oublier(1)
        self.assertNotIn(1, self.expert.cumuls)

    def test_boite_hors_de_l_image(self):
        fiche = self.fiche()
        fiche.suivi.boite = (5000.0, 5000.0, 100.0, 40.0)
        self.assertFalse(self.expert.lancer(fiche, self.image).reussi)


if __name__ == "__main__":
    unittest.main()
