import json
import unittest

from chaine import contrats
from chaine.fiche import FicheNavire, Observation
from chaine.sources import ScenarioSimule


class TestContrat1(unittest.TestCase):
    def test_aller_retour(self):
        message = contrats.observations(12.4, [Observation(7, (1000, 800, 412, 137), 0.81)])
        self.assertEqual(message, {"t": 12.4, "pistes": [{"id_piste": 7, "boite": [1000, 800, 412, 137],
                                                           "confiance": 0.81}]})
        t, pistes = contrats.lire_observations(json.loads(json.dumps(message)))
        self.assertEqual((t, pistes), (12.4, [Observation(7, (1000.0, 800.0, 412.0, 137.0), 0.81)]))

    def test_image_sans_navire(self):
        self.assertEqual(contrats.lire_observations({"t": 3, "pistes": []}), (3.0, []))

    def test_messages_hors_contrat_refuses(self):
        for message in ({"pistes": []}, {"t": 1.0}, {"t": 1.0, "pistes": [{"id_piste": 1, "confiance": 0.5}]},
                        {"t": 1.0, "pistes": [{"id_piste": 1, "boite": [1, 2, 3], "confiance": 0.5}]},
                        {"t": 1.0, "pistes": [{"id_piste": 1, "boite": [1, 2, -3, 4], "confiance": 0.5}]},
                        {"t": "abc", "pistes": []}):
            with self.assertRaises(contrats.ContratInvalide):
                contrats.lire_observations(message)

    def test_le_scenario_simule_respecte_le_contrat(self):
        for message, _ in ScenarioSimule(duree_s=25.0):
            contrats.lire_observations(message)
            self.assertEqual(set(message), {"t", "pistes"})


class TestContrat2(unittest.TestCase):
    def test_fiche_en_trois_blocs(self):
        fiche = FicheNavire.creer(7, 0.0)
        fiche.observer(0.2, Observation(7, (1000, 800, 602, 201), 0.81))
        contrat = json.loads(json.dumps(fiche.contrat()))
        self.assertEqual(list(contrat), ["id_piste", "suivi", "experts", "decision"])
        self.assertEqual(list(contrat["suivi"]), ["premiere_vue", "derniere_vue", "images_consecutives", "boite",
                                                  "confiance", "vitesse_px_s"])
        self.assertEqual(list(contrat["experts"]), ["types", "confiance_type", "immatriculation",
                                                    "confiance_immatriculation"])
        self.assertEqual(list(contrat["decision"]), ["etat", "tentatives", "debut_approche"])

    def test_valeurs_inconnues(self):
        contrat = FicheNavire.creer(7, 0.0).contrat()
        self.assertEqual(contrat["experts"]["types"], [])
        self.assertIsNone(contrat["experts"]["immatriculation"])
        self.assertEqual(contrat["decision"], {"etat": "nouvelle", "tentatives": {}, "debut_approche": None})


class TestContrat3(unittest.TestCase):
    def test_alerte(self):
        fiche = FicheNavire.creer(7, 0.0)
        fiche.experts.types = ["chalutier"]
        fiche.experts.immatriculation = "GV 123456"
        fiche.experts.confiance_immatriculation = 0.883
        self.assertEqual(contrats.message_alerte(47.6, fiche, True, "immatriculation lue"),
                         {"genre": "alerte", "t": 47.6, "id_piste": 7, "complete": True, "types": ["chalutier"],
                          "immatriculation": "GV 123456", "confiance_immatriculation": 0.88,
                          "raison": "immatriculation lue"})

    def test_decision(self):
        self.assertEqual(contrats.message_decision(0.6, 7, "approche", "navire trop petit pour lire"),
                         {"genre": "decision", "t": 0.6, "id_piste": 7, "action": "approche",
                          "raison": "navire trop petit pour lire"})
        with self.assertRaises(contrats.ContratInvalide):
            contrats.message_decision(0.6, 7, "filtre_qualite", "")

    def test_etat(self):
        self.assertEqual(contrats.message_etat(48.0, "patrouille", 0.82, 2, 61.5),
                         {"genre": "etat", "t": 48.0, "mode": "patrouille", "batterie": 0.82, "navires_suivis": 2,
                          "temperature_pi": 61.5})
        with self.assertRaises(contrats.ContratInvalide):
            contrats.message_etat(48.0, "retour", 0.82, 2, None)


if __name__ == "__main__":
    unittest.main()
