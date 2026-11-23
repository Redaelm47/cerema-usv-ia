"""Tests de la signature de couleur et de l'outil de comparaison, sur des images synthétiques."""
import unittest

import numpy as np

from chaine.couleur import DIMENSION, fusionner, signature_couleur, similarite_couleur
from chaine.outils.comparer_couleur import auc, comparer, confusion_a_rappel


def coque(bgr, taille=(80, 160), bruit=0, graine=0):
    image = np.empty((*taille, 3), np.uint8)
    image[:] = bgr
    if bruit:
        rng = np.random.default_rng(graine)
        image = np.clip(image.astype(int) + rng.integers(-bruit, bruit + 1, image.shape), 0, 255).astype(np.uint8)
    return image


BLEU, ROUGE, BLANC, NOIR = (200, 60, 20), (30, 30, 200), (240, 240, 240), (10, 10, 10)


class TestSignatureCouleur(unittest.TestCase):
    def test_norme_et_dimension(self):
        v = signature_couleur(coque(BLEU))
        self.assertEqual(v.shape, (DIMENSION,))
        self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=5)

    def test_meme_couleur_ressemble(self):
        a, b = signature_couleur(coque(BLEU, bruit=10)), signature_couleur(coque(BLEU, taille=(120, 240), bruit=10, graine=1))
        self.assertGreater(similarite_couleur(a, b), 0.95)

    def test_couleurs_differentes_se_distinguent(self):
        bleu, rouge = signature_couleur(coque(BLEU)), signature_couleur(coque(ROUGE))
        self.assertLess(similarite_couleur(bleu, rouge), 0.2)

    def test_blanc_noir_et_couleur_se_distinguent(self):
        blanc, noir, bleu = (signature_couleur(coque(c)) for c in (BLANC, NOIR, BLEU))
        self.assertLess(similarite_couleur(blanc, noir), 0.2)
        self.assertLess(similarite_couleur(blanc, bleu), 0.2)

    def test_le_bord_est_ignore(self):
        image = coque(BLEU)
        image[:, :10] = ROUGE   # bande sur le bord : de l'eau, du ciel, un autre navire
        self.assertGreater(similarite_couleur(signature_couleur(image), signature_couleur(coque(BLEU))), 0.99)

    def test_image_inutilisable(self):
        self.assertIsNone(signature_couleur(np.zeros((2, 2, 3), np.uint8)))
        self.assertIsNone(signature_couleur(None))


class TestComparaison(unittest.TestCase):
    def test_fusion(self):
        a, b = np.array([0.9, 0.5]), np.array([0.5, 0.9])
        np.testing.assert_allclose(fusionner(a, b, 0.0), a)
        np.testing.assert_allclose(fusionner(a, b, 1.0), b)
        np.testing.assert_allclose(fusionner(a, b, 0.5), [0.7, 0.7])

    def test_auc_extremes(self):
        meme = np.array([True, True, False, False])
        self.assertEqual(auc(np.array([0.9, 0.8, 0.3, 0.2]), meme), 1.0)
        self.assertEqual(auc(np.array([0.1, 0.2, 0.8, 0.9]), meme), 0.0)

    def test_confusion_a_rappel(self):
        meme = np.array([True] * 5 + [False] * 5)
        notes = np.array([0.9, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1])
        self.assertEqual(confusion_a_rappel(notes, meme), 0.0)

    def test_la_couleur_corrige_deux_navires_de_meme_signature_dino(self):
        """Deux navires dont DINOv2 donne la même signature, mais de couleurs différentes."""
        rng = np.random.default_rng(0)
        base = rng.normal(size=768)
        dino = {}
        for nom in ("a", "b", "c", "d"):
            vues = base + rng.normal(scale=0.05, size=(3, 768))   # tous presque identiques pour DINOv2
            dino[nom] = (vues / np.linalg.norm(vues, axis=1, keepdims=True)).astype(np.float32)
        teintes = {"a": BLEU, "b": ROUGE, "c": BLANC, "d": NOIR}
        couleurs = {n: np.stack([signature_couleur(coque(teintes[n], bruit=8, graine=i)) for i in range(3)])
                    for n in dino}
        lignes = {l["methode"]: l for l in comparer(dino, couleurs)}
        self.assertLess(lignes["DINOv2 seul"]["auc"], 0.7)
        self.assertGreater(lignes["couleur seule"]["auc"], 0.99)
        self.assertGreater(lignes["mélange 30% couleur"]["auc"], lignes["DINOv2 seul"]["auc"])


if __name__ == "__main__":
    unittest.main()
