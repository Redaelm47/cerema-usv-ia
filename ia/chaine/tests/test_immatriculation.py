import unittest

from chaine.experts.immatriculation import QUARTIERS, Vote, interpreter


class TestFormat(unittest.TestCase):
    def test_ecritures_courantes(self):
        for texte in ("GV 123456", "GV123456", "GV.123456", "gv-123456", " GV  123456 ", "MARIE GV 123456",
                      "GV 123 456", "GV 123456 LE GUILVINEC", "GV 123456H"):
            lecture = interpreter(texte)
            self.assertEqual((lecture.texte, lecture.corrections, lecture.quartier_connu), ("GV 123456", 0, True), texte)

    def test_textes_qui_ne_sont_pas_des_immatriculations(self):
        for texte in ("", "LE PETIT MOUSSE", "GV 12345", "123456", "SOS 112", "D 564", "ABCDEFGH", "GV 12E456",
                      "GV1234567", "Tel Fax05 46 50 52 66", "TEL 05 46 50 52 66", "IMO 8224406"):
            self.assertIsNone(interpreter(texte), texte)

    def test_confusions_corrigees_selon_la_position(self):
        lecture = interpreter("6V I23456")   # 6 lu pour G, I pour 1
        self.assertEqual((lecture.texte, lecture.corrections), ("GV 123456", 2))
        self.assertIsNone(interpreter("6V I2345O"))   # trois corrections : trop pour y croire
        self.assertEqual(interpreter("L0 546713").texte, "LO 546713")
        self.assertEqual(interpreter("CC 9II290").texte, "CC 911290")

    def test_une_correction_baisse_la_confiance(self):
        self.assertLess(interpreter("GV I23456").poids, interpreter("GV 123456").poids)

    def test_quartier_inconnu_garde_mais_moins_sur(self):
        self.assertNotIn("ZZ", QUARTIERS)
        lecture = interpreter("ZZ 123456")
        self.assertEqual((lecture.texte, lecture.quartier_connu), ("ZZ 123456", False))
        self.assertLess(lecture.poids, 1.0)

    def test_quartier_inconnu_refuse_s_il_faut_corriger(self):
        self.assertIsNone(interpreter("ZZ I23456"))


class TestVote(unittest.TestCase):
    def test_sans_lecture(self):
        self.assertEqual(Vote().resultat(), (None, 0.0, False))

    def test_une_seule_lecture_ne_suffit_pas(self):
        vote = Vote()
        vote.ajouter("GV 123456", 0.99)
        candidate, confiance, validee = vote.resultat()
        self.assertEqual((candidate, validee), ("GV 123456", False))
        self.assertAlmostEqual(confiance, 0.99)

    def test_deux_lectures_identiques_valident(self):
        vote = Vote()
        vote.ajouter("GV 123456", 0.9)
        vote.ajouter("GV 123456", 0.8)
        candidate, confiance, validee = vote.resultat()
        self.assertEqual((candidate, validee), ("GV 123456", True))
        self.assertAlmostEqual(confiance, 0.85)

    def test_deux_lectures_differentes_ne_valident_pas(self):
        vote = Vote()
        vote.ajouter("GV 123456", 0.9)
        vote.ajouter("GV 128456", 0.8)
        self.assertFalse(vote.resultat()[2])

    def test_la_majorite_l_emporte_sur_une_erreur(self):
        vote = Vote()
        for texte, confiance in (("GV 128456", 0.6), ("GV 123456", 0.9), ("GV 123456", 0.9)):
            vote.ajouter(texte, confiance)
        candidate, confiance, validee = vote.resultat()
        self.assertEqual((candidate, validee), ("GV 123456", True))
        self.assertLess(confiance, 0.9)   # le désaccord baisse la confiance

    def test_vote_par_caractere(self):
        """Chaque lecture a une erreur différente : le vote retrouve l'immatriculation, sans la valider."""
        vote = Vote()
        for texte in ("GV 123450", "GV 723456", "CV 123456"):
            vote.ajouter(texte, 0.8)
        candidate, _, validee = vote.resultat()
        self.assertEqual((candidate, validee), ("GV 123456", False))
        vote.ajouter("GV 123456", 0.8)
        vote.ajouter("GV 123456", 0.8)
        self.assertEqual(vote.resultat()[::2], ("GV 123456", True))


if __name__ == "__main__":
    unittest.main()
