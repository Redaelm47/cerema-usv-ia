import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chaine import contrats
from chaine.chaine import Chaine, recouvrement
from chaine.experts import (DroneSimule, ExpertApprocheFactice, ExpertApprocheSimulee, ExpertOCRFactice,
                            ExpertTypeFactice, Resultat)
from chaine.fiche import Etat, Observation
from chaine.journal import Journal
from chaine.reglages import Contexte, Reglages
from chaine.sources import ScenarioSimule

from .outils import observations


def chaine_factice(reglages=None, **experts):
    reglages = reglages or Reglages(seuil_ocr_essai_px=float("inf"))
    liste = [experts.pop("type", ExpertTypeFactice()), experts.pop("ocr", ExpertOCRFactice(reglages)),
             experts.pop("approche", ExpertApprocheFactice()), *experts.values()]
    return Chaine(liste, reglages)


class ExpertScripte:
    """Renvoie les résultats donnés, dans l'ordre, puis répète le dernier."""

    def __init__(self, nom, *resultats):
        self.nom = nom
        self.resultats = list(resultats)
        self.lancements = 0

    def lancer(self, fiche, image):
        self.lancements += 1
        return self.resultats.pop(0) if len(self.resultats) > 1 else self.resultats[0]


class TestScenario(unittest.TestCase):
    def test_scenario_simule_de_bout_en_bout(self):
        reglages, drone = Reglages(seuil_ocr_essai_px=float("inf")), DroneSimule()
        chaine = Chaine([ExpertTypeFactice(), ExpertOCRFactice(reglages), ExpertApprocheSimulee(drone, reglages)],
                        reglages, drone=drone)
        for message, image in ScenarioSimule(drone):
            chaine.pas(message, image)
        self.assertEqual([a["id_piste"] for a in chaine.alertes], [9, 7])
        self.assertTrue(all(a["complete"] for a in chaine.alertes))
        self.assertFalse([l for l in chaine.journal.lignes if l["piste"] == 3])  # la fausse détection n'a rien déclenché
        self.assertEqual(drone.mode, "patrouille")                               # l'approche est terminée
        self.assertEqual([l["action"] for l in chaine.journal.lignes if l["piste"] == 7],
                         ["expert_type", "approche", "expert_ocr", "alerte_complete"])

    def test_messages_du_contrat_3(self):
        reglages, drone = Reglages(seuil_ocr_essai_px=float("inf")), DroneSimule()
        chaine = Chaine([ExpertTypeFactice(), ExpertOCRFactice(reglages), ExpertApprocheSimulee(drone, reglages)],
                        reglages, drone=drone)
        for message, image in ScenarioSimule(drone):
            chaine.pas(message, image)
        messages = chaine.emetteur.messages
        cles = {"alerte": {"genre", "t", "id_piste", "complete", "types", "immatriculation",
                           "confiance_immatriculation", "raison"},
                "decision": {"genre", "t", "id_piste", "action", "raison"},
                "etat": {"genre", "t", "mode", "batterie", "navires_suivis", "temperature_pi"}}
        for message in messages:
            self.assertEqual(set(message), cles[message["genre"]])
            json.dumps(message)
        self.assertEqual({m["action"] for m in messages if m["genre"] == "decision"},
                         {"expert_type", "expert_ocr", "approche", "alerte_complete"})
        self.assertTrue({m["action"] for m in messages if m["genre"] == "decision"} <= set(contrats.ACTIONS))
        etats = [m for m in messages if m["genre"] == "etat"]
        self.assertEqual({m["mode"] for m in etats}, {"patrouille", "approche"})
        self.assertEqual(len(etats), 151)                      # un par seconde sur 150 s
        self.assertEqual(max(m["navires_suivis"] for m in etats), 2)
        self.assertLess(etats[-1]["batterie"], etats[0]["batterie"])
        self.assertEqual(len([m for m in messages if m["genre"] == "alerte"]), 2)

    def test_journal_ecrit_dans_un_fichier(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "journal.jsonl"
            reglages = Reglages(seuil_ocr_essai_px=float("inf"))
            chaine = Chaine([ExpertTypeFactice(), ExpertOCRFactice(reglages), ExpertApprocheFactice()], reglages,
                            Journal(chemin))
            for i in range(8):
                chaine.pas(observations(i * 0.5, (1, 700.0)))
            chaine.journal.fermer()
            lignes = [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l["action"] for l in lignes], ["expert_type", "expert_ocr", "alerte_complete"])
        self.assertEqual(list(lignes[0]["fiche"]), ["id_piste", "suivi", "experts", "decision"])
        self.assertIn("duree_ms", lignes[0])
        self.assertTrue(lignes[1]["reussi"])


class TestRegles(unittest.TestCase):
    def test_detection_isolee_ignoree(self):
        chaine = chaine_factice()
        chaine.pas(observations(0.0, (1, 40.0)))
        chaine.pas(observations(0.2))
        chaine.pas(observations(0.4, (1, 40.0)))
        self.assertEqual(chaine.journal.lignes, [])

    def test_un_seul_expert_par_image(self):
        chaine = chaine_factice()
        for i in range(5):   # les deux pistes sont confirmées à la 5e image : un seul expert part
            chaine.pas(observations(i * 0.2, (1, 100.0), (2, 100.0)))
        self.assertEqual(len(chaine.journal.lignes), 1)
        chaine.pas(observations(1.0, (1, 100.0), (2, 100.0)))
        self.assertEqual(len(chaine.journal.lignes), 2)

    def test_observations_hors_contrat_refusees(self):
        with self.assertRaises(contrats.ContratInvalide):
            chaine_factice().pas({"t": 0.0})

    def test_batterie_basse_pas_d_approche(self):
        chaine = chaine_factice()
        for i in range(6):
            chaine.pas(observations(i * 0.2, (1, 100.0)), contexte=Contexte(batterie=0.1))
        self.assertEqual(len(chaine.alertes), 1)
        self.assertFalse(chaine.alertes[0]["complete"])
        self.assertEqual(chaine.alertes[0]["raison"], "batterie trop basse")
        self.assertNotIn("approche", chaine.fiches[1].decision.tentatives)

    def test_approche_trop_longue_abandonnee(self):
        chaine = chaine_factice(Reglages(duree_max_approche_s=10.0))
        t = 0.0
        while t < 15.0 and not chaine.alertes:
            chaine.pas(observations(t, (1, 100.0 + t)))  # le navire grossit trop lentement
            t += 0.2
        self.assertEqual(chaine.alertes[0]["raison"], "durée maximale d'approche dépassée")
        self.assertEqual(chaine.alertes[0]["types"], ["chalutier"])

    def test_navire_qui_s_eloigne_approche_abandonnee(self):
        chaine = chaine_factice()
        t = 0.0
        while t < 40.0 and not chaine.alertes:
            chaine.pas(observations(t, (1, 100.0)))  # le navire ne grossit jamais
            t += 0.2
        self.assertEqual(chaine.alertes[0]["raison"], "le navire s'éloigne plus vite que le drone")

    def test_navire_perdu_pendant_l_approche(self):
        terminees = []
        chaine = chaine_factice(approche=ExpertApprocheFactice(sur_fin=terminees.append))
        for i in range(7):   # confirmée à la 5e image, puis l'approche
            chaine.pas(observations(i * 0.2, (1, 100.0)))
        self.assertEqual(chaine.fiches[1].decision.etat, Etat.EN_APPROCHE)
        chaine.pas(observations(10.0))
        self.assertEqual(chaine.alertes[0]["raison"], "piste perdue")
        self.assertEqual(terminees, [1])

    def test_type_hesitant_transmis_dans_l_alerte(self):
        reglages = Reglages(seuil_ocr_essai_px=float("inf"))
        chaine = chaine_factice(reglages, type=ExpertTypeFactice(("chalutier", "vedette"), 0.55))
        for i in range(12):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertEqual(chaine.alertes[0]["types"], ["chalutier", "vedette"])
        self.assertTrue(chaine.alertes[0]["complete"])
        self.assertEqual(chaine.fiches[1].decision.tentatives["type"], reglages.max_tentatives_type)

    def test_lecture_non_validee_transmise_dans_l_alerte_partielle(self):
        reglages = Reglages(seuil_ocr_essai_px=float("inf"))
        ocr = ExpertScripte("ocr", Resultat(False, {"candidate": "GV 123456", "confiance": 0.4, "raison": "vote en cours"}))
        chaine = chaine_factice(reglages, ocr=ocr)
        for i in range(30):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertEqual(ocr.lancements, reglages.max_tentatives_ocr)
        alerte = chaine.alertes[0]
        self.assertEqual((alerte["complete"], alerte["immatriculation"], alerte["confiance_immatriculation"],
                          alerte["raison"]), (False, "GV 123456", 0.4, "immatriculation illisible"))

    def test_lecture_validee_au_troisieme_essai(self):
        ocr = ExpertScripte("ocr", Resultat(False, {"candidate": None, "confiance": 0.0}),
                            Resultat(False, {"candidate": "GV 123456", "confiance": 0.8}),
                            Resultat(True, {"immatriculation": "GV 123456", "candidate": "GV 123456", "confiance": 0.85}))
        chaine = chaine_factice(ocr=ocr)
        for i in range(12):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertEqual(ocr.lancements, 3)
        self.assertEqual((chaine.alertes[0]["complete"], chaine.alertes[0]["immatriculation"]), (True, "GV 123456"))

    def test_fiches_effacees_apres_le_delai_d_oubli(self):
        chaine = chaine_factice()
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertEqual(chaine.fiches[1].decision.etat, Etat.ALERTEE)
        chaine.pas(observations(100.0))
        self.assertEqual(chaine.fiches, {})


class ExpertOCRScripte(ExpertScripte):
    """Expert OCR qui note quel recadrage on lui donne à lire."""
    marge = 0.0

    def __init__(self, *resultats):
        super().__init__("ocr", *resultats)
        self.recadrages = []

    def lire_recadrage(self, fiche, recadrage):
        self.recadrages.append(recadrage)
        return self.lancer(fiche, None)


class NetteteLue:
    """Faux filtre qualité : la netteté est la valeur du premier pixel du recadrage."""
    nom = "qualite"

    def evaluer(self, recadrage):
        nettete = float(recadrage[0, 0, 0])
        return Resultat(nettete >= 40, {"nettete": nettete, "raison": "image floue"})

    def lancer(self, fiche, image):
        return Resultat(True, {"nettete": 100.0})


def image_de_nettete(valeur):
    return np.full((400, 1000, 3), valeur, np.uint8)


class TestImageLaPlusNette(unittest.TestCase):
    def test_l_ocr_lit_l_image_la_plus_nette_de_l_intervalle(self):
        ocr = ExpertOCRScripte(Resultat(False, {"candidate": None, "confiance": 0.0}))
        chaine = chaine_factice(Reglages(intervalle_essais_s=1.0), ocr=ocr, qualite=NetteteLue())
        nettetes = [30, 40, 50, 60, 70, 55,  # piste confirmée à la 5e image ; premier essai à la 6e, sur la 5e (70)
                    90, 60, 200, 80,         # une seconde plus tard : la plus nette de l'intervalle est 200
                    70, 60, 50, 120, 60, 60]
        for i, nettete in enumerate(nettetes):
            chaine.pas(observations(i * 0.25, (1, 700.0)), image_de_nettete(nettete))
        lus = [int(r[0, 0, 0]) for r in ocr.recadrages]
        self.assertEqual(lus[:2], [70, 200])
        self.assertEqual(lus[2], 120)
        lectures = [l for l in chaine.journal.lignes if l["action"] == "expert_ocr"]
        self.assertEqual(lectures[1]["details"]["image_lue_t"], 2.0)     # l'image nette, pas celle du moment
        self.assertEqual(lectures[1]["nettete"], 200.0)

    def test_si_meme_la_plus_nette_est_floue_l_ocr_n_est_pas_lance(self):
        ocr = ExpertOCRScripte(Resultat(False, {"candidate": None, "confiance": 0.0}))
        chaine = chaine_factice(ocr=ocr, qualite=NetteteLue())
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)), image_de_nettete(10))
        self.assertEqual(ocr.recadrages, [])
        self.assertIn("filtre_qualite", [l["action"] for l in chaine.journal.lignes])

    def test_expert_sans_lire_recadrage_reste_utilisable(self):
        chaine = chaine_factice(qualite=NetteteLue())      # l'expert OCR factice ne sait lire que l'image entière
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)), image_de_nettete(100))
        self.assertTrue(chaine.alertes[0]["complete"])


class TestTextesHorsFormat(unittest.TestCase):
    def test_texte_lu_plusieurs_fois_joint_a_l_alerte_partielle(self):
        ocr = ExpertScripte("ocr", Resultat(False, {"candidate": None, "confiance": 0.0, "hors_format": ["S703", "ab"]}),
                            Resultat(False, {"candidate": None, "confiance": 0.0, "hors_format": ["S703", "MARY ANN"]}),
                            Resultat(False, {"candidate": None, "confiance": 0.0, "hors_format": ["5703"]}))
        chaine = chaine_factice(ocr=ocr)
        for i in range(30):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        alerte = chaine.alertes[0]
        self.assertFalse(alerte["complete"])
        self.assertIsNone(alerte["immatriculation"])
        self.assertEqual(alerte["textes_lus"], ["5703", "S703"])   # du plus lu au moins lu ; « MARY ANN » vu une seule fois

    def test_sans_texte_l_alerte_garde_exactement_le_format_du_contrat(self):
        chaine = chaine_factice()
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertNotIn("textes_lus", chaine.alertes[0])


class TestReprisePiste(unittest.TestCase):
    """Le suivi change parfois le numéro d'un navire : la chaîne ne doit pas le prendre pour un nouveau navire."""

    def test_recouvrement(self):
        self.assertEqual(recouvrement((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(recouvrement((0, 0, 10, 10), (20, 20, 10, 10)), 0.0)
        self.assertAlmostEqual(recouvrement((0, 0, 10, 10), (5, 0, 10, 10)), 1 / 3)

    def test_navire_alerte_qui_change_de_numero(self):
        chaine = chaine_factice()
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        self.assertEqual(len(chaine.alertes), 1)
        for i in range(8, 20):
            chaine.pas(observations(i * 0.5, (2, 705.0)))   # même endroit, nouveau numéro
        self.assertEqual(len(chaine.alertes), 1)             # pas de seconde alerte
        self.assertEqual(list(chaine.fiches), [2])
        self.assertEqual(chaine.fiches[2].decision.etat, Etat.ALERTEE)
        self.assertEqual(chaine.journal.lignes[-1]["action"], "reprise_piste")

    def test_changement_de_numero_pendant_l_approche(self):
        reglages, drone = Reglages(seuil_ocr_essai_px=float("inf")), DroneSimule()
        chaine = Chaine([ExpertTypeFactice(), ExpertOCRFactice(reglages), ExpertApprocheSimulee(drone, reglages)],
                        reglages, drone=drone)
        for i in range(7):   # confirmée à la 5e image, type à la 6e, approche à la 7e
            chaine.pas(observations(i * 0.2, (1, 150.0)))
        self.assertEqual(drone.cible, 1)
        chaine.pas(observations(1.4, (2, 152.0)))
        self.assertEqual(drone.cible, 2)                     # l'approche continue sur le même navire
        self.assertEqual(chaine.fiches[2].decision.tentatives, {"type": 1, "approche": 1})

    def test_navire_different_ailleurs_dans_l_image(self):
        chaine = chaine_factice()
        for i in range(8):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        ailleurs = Observation(2, (2000.0, 900.0, 700.0, 230.0), 0.8)
        for i in range(8, 16):
            chaine.pas(observations(i * 0.5, ailleurs))
        self.assertEqual([a["id_piste"] for a in chaine.alertes], [1, 2])

    def test_deux_navires_visibles_ensemble_ne_sont_pas_confondus(self):
        chaine = chaine_factice()
        for i in range(4):
            chaine.pas(observations(i * 0.5, (1, 700.0)))
        chaine.pas(observations(2.0, (1, 700.0), (2, 690.0)))   # boîtes superposées mais vues en même temps
        self.assertEqual(sorted(chaine.fiches), [1, 2])


class TestFinDeMission(unittest.TestCase):
    def test_alerte_partielle_pour_les_navires_en_cours(self):
        chaine = chaine_factice()
        for i in range(5):
            chaine.pas(observations(i * 0.2, (1, 100.0)))
        self.assertEqual(chaine.alertes, [])
        chaine.cloturer(1.0)
        self.assertEqual([(a["complete"], a["raison"]) for a in chaine.alertes], [(False, "fin de la mission")])
        chaine.cloturer(1.2)
        self.assertEqual(len(chaine.alertes), 1)


class TestFiltreQualiteDansLaChaine(unittest.TestCase):
    IMAGE = np.zeros((400, 1000, 3), np.uint8)

    def test_image_rejetee_expert_non_lance(self):
        reglages = Reglages(seuil_ocr_essai_px=float("inf"))
        type_ = ExpertScripte("type", Resultat(True, {"types": ["chalutier"], "confiance": 0.9}))
        qualite = ExpertScripte("qualite", Resultat(False, {"raison": "image floue", "nettete": 3.0}),
                                Resultat(True, {"nettete": 80.0}))
        chaine = chaine_factice(reglages, type=type_, qualite=qualite)
        n = reglages.images_confirmation   # la piste est confirmée à la n-ième image sûre
        for i in range(n):
            chaine.pas(observations(i * 0.5, (1, 700.0)), self.IMAGE)
        self.assertEqual((type_.lancements, chaine.journal.lignes[0]["action"]), (0, "filtre_qualite"))
        self.assertEqual(chaine.fiches[1].decision.tentatives, {})
        self.assertEqual(chaine.emetteur.messages[-1]["genre"], "etat")   # un rejet n'est pas un message du contrat 3
        chaine.pas(observations(n * 0.5, (1, 700.0)), self.IMAGE)
        self.assertEqual(type_.lancements, 1)
        self.assertEqual(chaine.journal.lignes[-1]["nettete"], 80.0)

    def test_un_rejet_laisse_la_main_a_un_autre_navire(self):
        type_ = ExpertScripte("type", Resultat(True, {"types": ["chalutier"], "confiance": 0.9}))
        qualite = ExpertScripte("qualite", Resultat(False, {"raison": "image floue"}), Resultat(True, {}))
        chaine = chaine_factice(type=type_, qualite=qualite)
        for i in range(Reglages().images_confirmation):
            chaine.pas(observations(i * 0.5, (1, 700.0), (2, 700.0)), self.IMAGE)
        self.assertEqual([(l["piste"], l["action"]) for l in chaine.journal.lignes],
                         [(1, "filtre_qualite"), (2, "expert_type")])

    def test_pas_un_navire_deux_fois_piste_ecartee_sans_alerte(self):
        pas_navire = {"types": [], "navire": False, "confiance": 0.05}
        type_ = ExpertScripte("type", Resultat(True, {**pas_navire, "essais": 1}), Resultat(True, {**pas_navire, "essais": 2}))
        chaine = chaine_factice(type=type_)
        t = 0.0
        while t < 30.0:
            chaine.pas(observations(t, (1, 700.0)), self.IMAGE)
            t += 0.5
        chaine.cloturer(t)
        self.assertEqual(type_.lancements, 2)
        self.assertEqual(chaine.fiches[1].decision.etat, Etat.ECARTEE)
        self.assertEqual(chaine.alertes, [])
        self.assertEqual([l["action"] for l in chaine.journal.lignes], ["expert_type", "expert_type", "ecartee"])
        self.assertEqual({m["genre"] for m in chaine.emetteur.messages}, {"decision", "etat"})
        self.assertEqual(chaine.navires_suivis(t), 0)

    def test_un_seul_avis_pas_un_navire_ne_suffit_pas(self):
        type_ = ExpertScripte("type", Resultat(True, {"types": [], "navire": False, "confiance": 0.05, "essais": 1}),
                              Resultat(True, {"types": ["chalutier"], "navire": True, "confiance": 0.6, "essais": 2}))
        chaine = chaine_factice(type=type_)
        for i in range(8):   # confirmée à la 5e image, puis deux essais du type
            chaine.pas(observations(i * 0.5, (1, 700.0)), self.IMAGE)
        self.assertEqual(len(chaine.alertes), 1)
        self.assertTrue(chaine.alertes[0]["complete"])
        self.assertEqual(chaine.alertes[0]["types"], ["chalutier"])

    def test_images_toujours_floues_la_chaine_finit_par_alerter(self):
        reglages = Reglages(seuil_ocr_essai_px=float("inf"))
        qualite = ExpertScripte("qualite", Resultat(False, {"raison": "image floue", "nettete": 3.0}))
        chaine = chaine_factice(reglages, qualite=qualite)
        t = 0.0
        while t < 120.0 and not chaine.alertes:
            chaine.pas(observations(t, (1, 700.0)), self.IMAGE)
            t += 0.5
        self.assertEqual(len(chaine.alertes), 1)
        self.assertFalse(chaine.alertes[0]["complete"])
        self.assertEqual(chaine.fiches[1].decision.tentatives,
                         {"type": reglages.max_tentatives_type, "ocr": reglages.max_tentatives_ocr})


if __name__ == "__main__":
    unittest.main()
