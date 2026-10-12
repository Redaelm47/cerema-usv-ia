import unittest

from chaine.experts.approche import DroneSimule, ExpertApprocheSimulee, estimer_cap_et_distance
from chaine.reglages import Reglages

from .outils import fiche_confirmee

R = Reglages()


def fiche_a(x, largeur):
    fiche = fiche_confirmee(largeur)
    fiche.suivi.boite = (x, 800.0, largeur, largeur / 3)
    return fiche


class TestEstimation(unittest.TestCase):
    def test_navire_au_centre_cap_nul(self):
        cap, _ = estimer_cap_et_distance(fiche_a(2028 - 100, 200.0), 4056, 66.0, 15.0)
        self.assertAlmostEqual(cap, 0.0)

    def test_navire_au_bord_demi_champ(self):
        cap, _ = estimer_cap_et_distance(fiche_a(4056 - 1, 2.0), 4056, 66.0, 15.0)
        self.assertAlmostEqual(cap, 33.0, places=1)
        cap, _ = estimer_cap_et_distance(fiche_a(-1.0, 2.0), 4056, 66.0, 15.0)
        self.assertAlmostEqual(cap, -33.0, places=1)

    def test_la_distance_est_inverse_de_la_largeur(self):
        _, loin = estimer_cap_et_distance(fiche_a(1000, 100.0), 4056, 66.0, 15.0)
        _, pres = estimer_cap_et_distance(fiche_a(1000, 400.0), 4056, 66.0, 15.0)
        self.assertAlmostEqual(loin / pres, 4.0)
        self.assertAlmostEqual(loin, 15.0 * 3122.8 / 100.0, places=0)   # focale de 3123 px pour 66 degrés


class TestDroneSimule(unittest.TestCase):
    def test_patrouille(self):
        drone = DroneSimule()
        contexte = drone.contexte(10.0)
        self.assertEqual((contexte.mode, contexte.distance_m, drone.rapprochement), ("patrouille", None, 1.0))

    def test_avance_puis_s_arrete_a_la_distance_d_arret(self):
        drone = DroneSimule(vitesse_m_s=3.0)
        drone.contexte(0.0)
        drone.approcher(7, distance_m=300.0, distance_arret_m=90.0)
        self.assertEqual(drone.contexte(10.0).distance_m, 270.0)
        self.assertEqual(drone.contexte(10.0).mode, "approche")
        self.assertAlmostEqual(drone.rapprochement, 300.0 / 270.0)
        self.assertEqual(drone.contexte(500.0).distance_m, 90.0)

    def test_la_batterie_baisse_plus_vite_en_approche(self):
        patrouille, approche = DroneSimule(), DroneSimule()
        for drone in (patrouille, approche):
            drone.contexte(0.0)
        approche.approcher(7, 300.0, 90.0)
        self.assertLess(approche.contexte(60.0).batterie, patrouille.contexte(60.0).batterie)
        self.assertLess(patrouille.batterie, 1.0)

    def test_retour_en_patrouille(self):
        drone = DroneSimule()
        drone.approcher(7, 300.0, 90.0)
        drone.patrouiller()
        self.assertEqual((drone.mode, drone.cible, drone.rapprochement), ("patrouille", None, 1.0))


class TestExpertApproche(unittest.TestCase):
    def test_consigne(self):
        drone = DroneSimule()
        fiche = fiche_a(1000.0, 150.0)
        resultat = ExpertApprocheSimulee(drone, R).lancer(fiche, None)
        self.assertTrue(resultat.reussi)
        self.assertEqual(set(resultat.valeurs), {"cap_relatif_deg", "distance_estimee_m", "distance_arret_m"})
        self.assertLess(resultat.valeurs["cap_relatif_deg"], 0)   # navire à gauche du centre
        self.assertEqual(drone.cible, fiche.id_piste)
        # À la distance d'arrêt, le navire dépasse juste le seuil de lecture.
        grossissement = resultat.valeurs["distance_estimee_m"] / resultat.valeurs["distance_arret_m"]
        self.assertGreater(150.0 * grossissement, R.seuil_ocr_px)
        self.assertLess(150.0 * grossissement, 1.2 * R.seuil_ocr_px)

    def test_jamais_sous_la_distance_minimale(self):
        drone = DroneSimule()
        reglages = Reglages(distance_min_m=200.0)
        resultat = ExpertApprocheSimulee(drone, reglages).lancer(fiche_a(1000.0, 150.0), None)
        self.assertEqual(resultat.valeurs["distance_arret_m"], 200.0)
        self.assertAlmostEqual(drone.contexte(0.0).distance_m, resultat.valeurs["distance_estimee_m"], places=1)
        self.assertEqual(drone.contexte(10000.0).distance_m, 200.0)

    def test_la_longueur_supposee_depend_du_type(self):
        cargo, peche = fiche_a(1000.0, 150.0), fiche_a(1000.0, 150.0)
        cargo.experts.types, peche.experts.types = ["cargo"], ["peche"]
        distance = lambda fiche: ExpertApprocheSimulee(DroneSimule(), R).lancer(fiche, None).valeurs["distance_estimee_m"]
        self.assertAlmostEqual(distance(cargo) / distance(peche), 10.0, places=2)

    def test_une_seule_approche_a_la_fois(self):
        drone = DroneSimule()
        expert = ExpertApprocheSimulee(drone, R)
        premier, second = fiche_confirmee(150.0, id_piste=1), fiche_confirmee(150.0, id_piste=2)
        self.assertTrue(expert.lancer(premier, None).reussi)
        self.assertFalse(expert.lancer(second, None).reussi)
        expert.terminer(second)            # ne libère pas l'approche d'un autre navire
        self.assertEqual(drone.cible, 1)
        expert.terminer(premier)
        self.assertEqual(drone.mode, "patrouille")


if __name__ == "__main__":
    unittest.main()
