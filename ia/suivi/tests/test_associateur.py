"""Associateur : numéros stables, et jamais deux navires sous le même numéro."""
import unittest

from suivi.associateur import Associateur, ReglagesSuivi, part_couverte, recouvrement
from suivi.suivi import Suivi, observations


def boite(cx, cy, l=60.0, h=30.0, confiance=0.8):
    return (cx - l / 2, cy - h / 2, l, h, confiance)


def numeros(pistes):
    return sorted(p.id_piste for p in pistes)


class TestAssociateur(unittest.TestCase):
    def test_un_navire_garde_son_numero(self):
        a = Associateur()
        vus = [numeros(a.mettre_a_jour([boite(100 + 4 * i, 200)], i / 15)) for i in range(60)]
        self.assertTrue(all(v == [1] for v in vus))

    def test_deux_navires_ont_deux_numeros(self):
        a = Associateur()
        for i in range(30):
            pistes = a.mettre_a_jour([boite(100 + 3 * i, 200), boite(900 - 3 * i, 600)], i / 15)
        self.assertEqual(numeros(pistes), [1, 2])

    def test_une_detection_douteuse_prolonge_une_piste_mais_n_en_ouvre_pas(self):
        a = Associateur()
        self.assertEqual(a.mettre_a_jour([boite(100, 200, confiance=0.1)], 0.0), [])
        a.mettre_a_jour([boite(100, 200, confiance=0.8)], 0.1)
        self.assertEqual(numeros(a.mettre_a_jour([boite(104, 200, confiance=0.1)], 0.2)), [1])

    def test_un_navire_perdu_reprend_son_numero_au_meme_endroit(self):
        a = Associateur()
        for i in range(10):
            a.mettre_a_jour([boite(500, 300)], i / 15)
        for i in range(10, 40):  # deux secondes sans détection
            a.mettre_a_jour([], i / 15)
        self.assertEqual(numeros(a.mettre_a_jour([boite(520, 310)], 40 / 15)), [1])

    def test_un_petit_navire_qui_saute_garde_son_numero(self):
        # Caméra qui bouge : la boîte se déplace d'environ sa taille, sans recouvrement d'une image à l'autre.
        a = Associateur()
        centres = [(500, 300), (530, 290), (495, 310), (525, 325), (500, 295)]
        vus = [numeros(a.mettre_a_jour([boite(cx, cy, 30, 15)], i / 15)) for i, (cx, cy) in enumerate(centres)]
        self.assertTrue(all(v == [1] for v in vus))

    def test_le_tangage_de_la_camera_ne_change_pas_le_numero(self):
        # caméra à ras de l'eau : le navire monte et descend de plus que sa hauteur d'une image à l'autre
        hauts = [0, 90, -60, 120, -110, 40, -130, 80, 0, -90] * 3
        for reglages, attendu in ((ReglagesSuivi(), 1), (ReglagesSuivi(poids_vertical=1.0, vitesse_verticale=True), None)):
            a = Associateur(reglages)
            ids = set()
            for i, dy in enumerate(hauts):
                ids |= set(numeros(a.mettre_a_jour([boite(800 + 2 * i, 600 + dy, l=120, h=40)], i / 10)))
            if attendu:
                self.assertEqual(len(ids), attendu)
            else:
                self.assertGreater(len(ids), 1)  # l'ancien réglage perdait le navire

    def test_le_tangage_ne_fusionne_pas_deux_navires_cote_a_cote(self):
        a = Associateur()
        for i, dy in enumerate([0, 80, -80, 60, -60, 0] * 3):
            pistes = a.mettre_a_jour([boite(600, 500 + dy, l=100, h=40), boite(900, 500 + dy, l=100, h=40)], i / 10)
        self.assertEqual(numeros(pistes), [1, 2])

    def test_un_navire_oublie_apres_la_memoire_recoit_un_nouveau_numero(self):
        a = Associateur(ReglagesSuivi(memoire_s=4.0))
        a.mettre_a_jour([boite(500, 300)], 0.0)
        self.assertEqual(numeros(a.mettre_a_jour([boite(500, 300)], 5.0)), [2])

    def test_un_navire_ailleurs_dans_l_image_n_herite_pas_du_numero(self):
        a = Associateur()
        for i in range(10):
            a.mettre_a_jour([boite(200, 300)], i / 15)
        self.assertEqual(numeros(a.mettre_a_jour([boite(1500, 300)], 1.0)), [2])

    def test_un_navire_de_taille_tres_differente_n_herite_pas_du_numero(self):
        a = Associateur()
        for i in range(10):
            a.mettre_a_jour([boite(500, 300, 60, 30)], i / 15)
        for i in range(10, 25):
            a.mettre_a_jour([], i / 15)
        self.assertEqual(numeros(a.mettre_a_jour([boite(500, 300, 300, 150)], 25 / 15)), [2])

    def test_dans_le_doute_pas_d_association(self):
        # Une piste perdue, deux navires qui apparaissent à égale distance : aucun ne reprend le numéro.
        a = Associateur()
        for i in range(10):
            a.mettre_a_jour([boite(500, 300)], i / 15)
        for i in range(10, 25):
            a.mettre_a_jour([], i / 15)
        pistes = a.mettre_a_jour([boite(440, 300), boite(560, 300)], 25 / 15)
        self.assertNotIn(1, numeros(pistes))

    def test_deux_navires_qui_se_croisent_gardent_chacun_leur_numero(self):
        # Routes parallèles en sens inverse, 80 px d'écart vertical : les boîtes ne se recouvrent jamais.
        a = Associateur()
        positions = {}
        for i in range(120):
            pistes = a.mettre_a_jour([boite(100 + 8 * i, 300), boite(1060 - 8 * i, 380)], i / 15)
            for p in pistes:
                positions.setdefault(p.id_piste, []).append(p.boite[1])
        self.assertEqual(sorted(positions), [1, 2])
        for hauteurs in positions.values():  # chaque numéro est resté sur la même route
            self.assertEqual(len(set(hauteurs)), 1)

    def test_une_seconde_boite_sur_le_meme_navire_n_ouvre_pas_de_piste(self):
        a = Associateur()
        a.mettre_a_jour([boite(500, 300, 300, 150)], 0.0)
        pistes = a.mettre_a_jour([boite(500, 300, 300, 150), boite(520, 280, 120, 60, confiance=0.5)], 0.1)
        self.assertEqual(numeros(pistes), [1])

    def test_deux_boites_superposees_sur_la_premiere_image_donnent_une_piste(self):
        a = Associateur()
        pistes = a.mettre_a_jour([boite(500, 300, 300, 150), boite(520, 280, 120, 60, confiance=0.5)], 0.0)
        self.assertEqual(numeros(pistes), [1])
        self.assertEqual(pistes[0].boite[2], 300)

    def test_recouvrement_et_part_couverte(self):
        self.assertEqual(recouvrement((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(recouvrement((0, 0, 10, 10), (20, 0, 10, 10)), 0.0)
        self.assertEqual(part_couverte((2, 2, 4, 4), (0, 0, 10, 10)), 1.0)
        self.assertAlmostEqual(part_couverte((0, 0, 10, 10), (2, 2, 4, 4)), 0.16)


class TestContrat1(unittest.TestCase):
    def test_format_du_message(self):
        a = Associateur()
        message = observations(1.23456, a.mettre_a_jour([boite(100, 200)], 1.23456))
        self.assertEqual(message, {"t": 1.235, "pistes": [{"id_piste": 1, "boite": [70.0, 185.0, 60.0, 30.0],
                                                             "confiance": 0.8}]})

    def test_le_message_est_accepte_par_la_chaine(self):
        from chaine.contrats import lire_observations
        a = Associateur()
        t, pistes = lire_observations(observations(0.5, a.mettre_a_jour([boite(100, 200)], 0.5)))
        self.assertEqual((t, pistes[0].id_piste, pistes[0].boite), (0.5, 1, (70.0, 185.0, 60.0, 30.0)))

    def test_un_message_par_image_meme_sans_navire(self):
        class Detecteur:
            def detecter(self, image):
                return [boite(100, 200)] if image == "navire" else []
        images = [(0.0, "mer", None), (0.1, "navire", None), (0.2, "mer", None), (0.3, "capteur", [boite(104, 200)])]
        messages = [m for m, _ in Suivi(images, Detecteur())]
        self.assertEqual([len(m["pistes"]) for m in messages], [0, 1, 0, 1])
        self.assertEqual(messages[3]["pistes"][0]["id_piste"], 1)  # boîtes fournies par la caméra : même numéro


if __name__ == "__main__":
    unittest.main()
