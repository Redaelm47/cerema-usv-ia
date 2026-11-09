import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chaine.chaine import Chaine
from chaine.experts import ExpertApprocheFactice, ExpertOCRFactice, Resultat
from chaine.reglages import Reglages
from chaine.reidentification import (IMMATRICULATION, PROBABLE, SUR, MemoireNavires, ReglagesReid, ajouter_diverse,
                                     normaliser, similarite, types_compatibles)

from .outils import observations

DIM = 768
GENERATEUR = np.random.default_rng(0)


def navire():
    """Apparence d'un navire : un vecteur aléatoire (en grande dimension, deux tirages sont presque orthogonaux)."""
    return normaliser(GENERATEUR.normal(size=DIM))


def vue(base, bruit=0.25):
    """Une vue du navire : son apparence plus un bruit. bruit=0.25 donne une similarité d'environ 0,94."""
    return normaliser(base + bruit * normaliser(GENERATEUR.normal(size=DIM)))


def ressemblant(base, cible):
    """Un autre navire dont la vue a une similarité `cible` avec `base`."""
    autre = normaliser(GENERATEUR.normal(size=DIM))
    autre = normaliser(autre - (autre @ base) * base)
    return normaliser(cible * base + np.sqrt(1 - cible ** 2) * autre)


def memoire_avec(*navires, reglages=None):
    """Mémoire contenant les navires donnés : (piste, apparence, immatriculation, types)."""
    memoire = MemoireNavires(reglages)
    for piste, base, immat, types in navires:
        for _ in range(3):
            memoire.ajouter_vue(piste, vue(base), 200)
        memoire.enregistrer(piste, float(piste), immat, types)
    return memoire


class TestOutils(unittest.TestCase):
    def test_normaliser_refuse_les_vecteurs_invalides(self):
        self.assertIsNone(normaliser([]))
        self.assertIsNone(normaliser(np.zeros(4)))
        self.assertIsNone(normaliser([1.0, np.nan]))
        self.assertIsNone(normaliser([1.0, np.inf]))
        self.assertAlmostEqual(float(np.linalg.norm(normaliser([3.0, 4.0]))), 1.0, places=6)

    def test_similarite_moyenne_des_meilleures_vues(self):
        a, b = np.eye(3)[:1], np.eye(3)[[0, 1]]
        self.assertAlmostEqual(similarite(a, b), 1.0)
        self.assertAlmostEqual(similarite(np.eye(3)[[0, 2]], b), 0.5)
        self.assertTrue(np.isnan(similarite(np.zeros((0, 3)), b)))

    def test_ajouter_diverse_ignore_les_doublons_et_reste_bornee(self):
        base = navire()
        ensemble = ajouter_diverse(None, base, 3, 0.97)
        self.assertEqual(len(ajouter_diverse(ensemble, base, 3, 0.97)), 1)  # doublon ignoré
        for _ in range(10):
            ensemble = ajouter_diverse(ensemble, navire(), 3, 0.97)
        self.assertEqual(len(ensemble), 3)

    def test_ajouter_diverse_retire_la_vue_la_plus_redondante(self):
        a, b, c = np.eye(3)
        proche_de_a = normaliser(a + 0.3 * b)
        ensemble = ajouter_diverse(ajouter_diverse(ajouter_diverse(None, a, 3, 0.99), b, 3, 0.99), c, 3, 0.99)
        ensemble = ajouter_diverse(ensemble, proche_de_a, 3, 0.99)
        # a ou proche_de_a est retiré, b et c (les vues les plus différentes) restent
        self.assertTrue(any(np.allclose(v, b) for v in ensemble) and any(np.allclose(v, c) for v in ensemble))

    def test_types_compatibles(self):
        self.assertTrue(types_compatibles(["peche"], ["peche"]))
        self.assertFalse(types_compatibles(["peche"], ["voilier"]))
        self.assertTrue(types_compatibles(["peche", "vedette"], ["vedette"]))  # type hésitant : pas d'exclusion
        self.assertTrue(types_compatibles([], ["voilier"]))
        self.assertTrue(types_compatibles(None, ["voilier"]))


class TestMemoire(unittest.TestCase):
    def test_vue_trop_petite_ou_invalide_ecartee(self):
        memoire = MemoireNavires()
        self.assertFalse(memoire.ajouter_vue(1, navire(), 40))
        self.assertFalse(memoire.ajouter_vue(1, np.zeros(DIM), 200))
        self.assertTrue(memoire.ajouter_vue(1, navire(), 200))
        with self.assertRaises(ValueError):
            memoire.ajouter_vue(1, np.ones(10), 200)

    def test_meme_navire_reconnu_avec_certitude(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", ["peche"]))
        memoire.ajouter_vue(7, vue(a), 200)
        trouve = memoire.rechercher(7, ["peche"])
        self.assertIsNotNone(trouve)
        self.assertEqual((trouve.niveau, trouve.navire.immatriculation), (SUR, "GV 111111"))
        self.assertEqual(trouve.message()["immatriculation"], "GV 111111")

    def test_navire_inconnu_non_reconnu(self):
        memoire = memoire_avec((1, navire(), "GV 111111", ["peche"]))
        memoire.ajouter_vue(7, vue(navire()), 200)
        self.assertIsNone(memoire.rechercher(7))

    def test_piste_sans_signature(self):
        memoire = memoire_avec((1, navire(), "GV 111111", []))
        self.assertIsNone(memoire.rechercher(7))

    def test_niveau_probable_entre_les_deux_seuils(self):
        a = navire()
        memoire = MemoireNavires()
        memoire.ajouter_vue(1, a, 200)
        memoire.enregistrer(1, 1.0, "GV 111111", [])
        memoire.ajouter_vue(7, ressemblant(a, 0.87), 200)
        trouve = memoire.rechercher(7)
        self.assertEqual(trouve.niveau, PROBABLE)
        self.assertAlmostEqual(trouve.similarite, 0.87, places=3)

    def test_sous_le_seuil_rien(self):
        a = navire()
        memoire = MemoireNavires()
        memoire.ajouter_vue(1, a, 200)
        memoire.enregistrer(1, 1.0, "GV 111111", [])
        memoire.ajouter_vue(7, ressemblant(a, 0.80), 200)
        self.assertIsNone(memoire.rechercher(7))

    def test_deux_navires_distincts_trop_ressemblants_aucun_choix(self):
        a = navire()
        b = ressemblant(a, 0.99)  # deux fileyeurs bleus
        memoire = MemoireNavires()
        for piste, base, immat in ((1, a, "GV 111111"), (2, b, "GV 222222")):
            memoire.ajouter_vue(piste, base, 200)
            memoire.enregistrer(piste, float(piste), immat, [])
        memoire.ajouter_vue(7, a, 200)
        self.assertIsNone(memoire.rechercher(7))

    def test_meme_identite_ne_compte_pas_dans_la_marge(self):
        a = navire()
        memoire = MemoireNavires()
        memoire.ajouter_vue(1, vue(a), 200)
        premier = memoire.enregistrer(1, 1.0, None, [])
        memoire.ajouter_vue(2, vue(a), 200)
        trouve = memoire.rechercher(2)
        self.assertEqual(trouve.niveau, SUR)
        second = memoire.enregistrer(2, 2.0, None, [], trouve)
        self.assertEqual(second.ressemble_a, premier.numero)  # relié, pas fusionné
        self.assertEqual(len(memoire.navires), 2)
        memoire.ajouter_vue(3, vue(a), 200)
        self.assertIsNotNone(memoire.rechercher(3))  # les deux entrées du même navire ne s'annulent pas

    def test_type_certain_different_exclu(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", ["peche"]))
        memoire.ajouter_vue(7, vue(a), 200)
        self.assertIsNone(memoire.rechercher(7, ["voilier"]))
        self.assertIsNotNone(memoire.rechercher(7, ["voilier", "peche"]))

    def test_navire_visible_en_meme_temps_exclu(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", []))
        memoire.ajouter_vue(7, vue(a), 200)
        self.assertIsNone(memoire.rechercher(7, exclure_pistes={1}))
        self.assertIsNotNone(memoire.rechercher(7, exclure_pistes={3}))

    def test_verifier_immatriculation(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", []))
        memoire.ajouter_vue(7, vue(a), 200)
        memoire.ajouter_vue(8, vue(navire()), 200)
        self.assertIsNone(memoire.verifier(7, "GV 999999"))
        coherent = memoire.verifier(7, "GV 111111")
        self.assertEqual((coherent.niveau, coherent.apparence_coherente), (IMMATRICULATION, True))
        self.assertFalse(memoire.verifier(8, "GV 111111").apparence_coherente)
        sans_vue = memoire.verifier(9, "GV 111111")
        self.assertIsNone(sans_vue.apparence_coherente)
        self.assertIsNone(sans_vue.message()["similarite"])

    def test_enregistrer_complete_une_immatriculation_connue(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", ["peche", "vedette"]))
        memoire.ajouter_vue(7, vue(a, 0.6), 200)
        navire_connu = memoire.enregistrer(7, 9.0, "GV 111111", ["peche"])
        self.assertEqual(len(memoire.navires), 1)
        self.assertEqual(navire_connu.pistes, [1, 7])
        self.assertEqual(navire_connu.types, ["peche"])  # le type certain remplace le type hésitant
        self.assertEqual(navire_connu.derniere_alerte_t, 9.0)
        self.assertNotIn(7, memoire.en_cours)

    def test_enregistrer_sans_rien_pour_reconnaitre(self):
        memoire = MemoireNavires()
        self.assertIsNone(memoire.enregistrer(1, 1.0, None, ["peche"]))
        self.assertIsNotNone(memoire.enregistrer(2, 1.0, "GV 111111", []))  # immatriculation seule : gardée

    def test_taille_bornee(self):
        memoire = MemoireNavires(ReglagesReid(max_navires=3))
        for piste in range(5):
            memoire.ajouter_vue(piste, navire(), 200)
            memoire.enregistrer(piste, float(piste), None, [])
        self.assertEqual(sorted(n.pistes[0] for n in memoire.navires.values()), [2, 3, 4])

    def test_renommer_et_oublier(self):
        memoire = MemoireNavires()
        memoire.ajouter_vue(1, navire(), 200)
        memoire.renommer(1, 4)
        self.assertEqual(list(memoire.en_cours), [4])
        memoire.oublier(4)
        self.assertEqual(memoire.en_cours, {})

    def test_sauver_et_charger(self):
        a = navire()
        memoire = memoire_avec((1, a, "GV 111111", ["peche"]), (2, navire(), None, []))
        memoire.ajouter_vue(9, navire(), 200)  # piste en cours : non sauvée
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "memoire" / "navires"
            memoire.sauver(chemin)
            relue = MemoireNavires.charger(chemin)
        self.assertEqual(len(relue.navires), 2)
        self.assertEqual(relue.en_cours, {})
        self.assertTrue(all(n.pistes == [] for n in relue.navires.values()))  # numéros d'une autre mission
        relue.ajouter_vue(1, vue(a), 200)
        self.assertEqual(relue.rechercher(1, ["peche"]).navire.immatriculation, "GV 111111")
        relue.ajouter_vue(5, navire(), 200)
        self.assertEqual(relue.enregistrer(5, 1.0, None, []).numero, 3)  # pas de numéro réutilisé


class ExpertTypeSignature:
    """Expert type factice qui rend aussi une signature : l'apparence du navire de chaque piste, bruitée."""
    nom = "type"

    def __init__(self, apparences, types=("peche",)):
        self.apparences = apparences
        self.types = list(types)

    def lancer(self, fiche, image):
        return Resultat(True, {"types": list(self.types), "confiance": 0.9,
                               "signature": vue(self.apparences[fiche.id_piste]), "largeur_recadrage": 200})


class ExpertOCRScripte:
    nom = "ocr"

    def __init__(self, *resultats):
        self.resultats = list(resultats)

    def lancer(self, fiche, image):
        return self.resultats.pop(0) if len(self.resultats) > 1 else self.resultats[0]


def derouler(chaine, debut, fin, *pistes, pas=0.1):
    t = debut
    while t < fin - 1e-9:
        chaine.pas(observations(round(t, 2), *pistes))
        t += pas
    return round(t, 2)


class TestChaineAvecReid(unittest.TestCase):
    def chaine(self, apparences, ocr=None, reid=True, reglages=None):
        reglages = reglages or Reglages()
        experts = [ExpertTypeSignature(apparences), ocr or ExpertOCRFactice(reglages, "GV 111111"),
                   ExpertApprocheFactice()]
        return Chaine(experts, reglages, reid=MemoireNavires() if reid else None)

    def test_navire_revu_trop_loin_pas_de_nouvelle_approche(self):
        a = navire()
        chaine = self.chaine({1: a, 5: a})
        t = derouler(chaine, 0.0, 2.0, (1, 700))           # lu de près, alerte complète
        self.assertTrue(chaine.alertes[-1]["complete"])
        self.assertNotIn("deja_vu", chaine.alertes[-1])    # premier passage : rien en mémoire
        derouler(chaine, t + 10, t + 12, (5, 100))         # revu plus tard, trop petit pour lire
        alerte = chaine.alertes[-1]
        self.assertEqual((alerte["id_piste"], alerte["complete"]), (5, False))
        self.assertEqual(alerte["deja_vu"]["immatriculation"], "GV 111111")
        self.assertEqual(alerte["deja_vu"]["niveau"], SUR)
        self.assertIsNone(alerte["immatriculation"])       # l'apparence ne prouve pas l'identité
        self.assertNotIn("approche", [l["action"] for l in chaine.journal.lignes if l["piste"] == 5])
        self.assertIn("reidentification", [l["action"] for l in chaine.journal.lignes if l["piste"] == 5])
        self.assertTrue(all("signature" not in l.get("details", {}) for l in chaine.journal.lignes))

    def test_sans_reid_le_comportement_ne_change_pas(self):
        a = navire()
        chaine = self.chaine({1: a, 5: a}, reid=False)
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 100))
        self.assertIn("approche", [l["action"] for l in chaine.journal.lignes if l["piste"] == 5])
        self.assertTrue(all("deja_vu" not in a for a in chaine.alertes))

    def test_option_reapproche_desactivee(self):
        a = navire()
        chaine = self.chaine({1: a, 5: a}, reglages=Reglages(reid_eviter_reapproche=False))
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 100))
        self.assertIn("approche", [l["action"] for l in chaine.journal.lignes if l["piste"] == 5])

    def test_autre_navire_trop_loin_approche_normale(self):
        chaine = self.chaine({1: navire(), 5: navire()})
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 100))
        self.assertIn("approche", [l["action"] for l in chaine.journal.lignes if l["piste"] == 5])

    def test_une_lecture_suffit_si_elle_confirme_la_ressemblance(self):
        a = navire()
        une_lecture = Resultat(False, {"lue": "GV 111111", "candidate": "GV 111111", "confiance": 0.8,
                                       "raison": "vote en cours"})
        reglages = Reglages()
        chaine = self.chaine({1: a, 5: a}, ocr=ExpertOCRScripte(
            Resultat(True, {"immatriculation": "GV 111111", "confiance": 0.9}), une_lecture), reglages=reglages)
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 700))
        alerte = chaine.alertes[-1]
        self.assertEqual((alerte["id_piste"], alerte["complete"], alerte["immatriculation"]), (5, True, "GV 111111"))
        self.assertEqual(alerte["deja_vu"]["niveau"], IMMATRICULATION)
        self.assertTrue(alerte["deja_vu"]["apparence_coherente"])
        lectures = [l for l in chaine.journal.lignes if l["piste"] == 5 and l["action"] == "expert_ocr"]
        self.assertEqual(len(lectures), 1)
        self.assertEqual(lectures[0]["details"]["raison"], "lecture confirmée par la ré-identification")

    def test_une_lecture_differente_ne_suffit_pas(self):
        a = navire()
        autre = Resultat(False, {"lue": "GV 111112", "candidate": "GV 111112", "confiance": 0.8,
                                 "raison": "vote en cours"})
        chaine = self.chaine({1: a, 5: a}, ocr=ExpertOCRScripte(
            Resultat(True, {"immatriculation": "GV 111111", "confiance": 0.9}), autre))
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 11, (5, 700))
        self.assertEqual(chaine.alertes[-1]["id_piste"], 1)  # piste 5 toujours en lecture

    def test_meme_immatriculation_apparence_differente_signalee(self):
        chaine = self.chaine({1: navire(), 5: navire()})
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 700))
        alerte = chaine.alertes[-1]
        self.assertEqual((alerte["id_piste"], alerte["complete"]), (5, True))
        self.assertFalse(alerte["deja_vu"]["apparence_coherente"])
        incoherences = [l for l in chaine.journal.lignes if l["action"] == "reidentification" and l["piste"] == 5]
        self.assertEqual(len(incoherences), 1)
        self.assertFalse(incoherences[0]["reussi"])

    def test_deux_navires_identiques_visibles_ensemble_jamais_confondus(self):
        a = navire()
        chaine = self.chaine({1: a, 2: a})
        t = derouler(chaine, 0.0, 3.0, (1, 700), (2, 100))
        self.assertTrue(chaine.alertes and chaine.alertes[0]["id_piste"] == 1)  # 1 en mémoire avant la fin de 2
        self.assertIn("approche", [l["action"] for l in chaine.journal.lignes if l["piste"] == 2])
        chaine.cloturer(t)
        alerte_2 = [x for x in chaine.alertes if x["id_piste"] == 2]
        self.assertTrue(alerte_2)
        self.assertNotIn("deja_vu", alerte_2[0])
        self.assertNotIn("reidentification", [l["action"] for l in chaine.journal.lignes if l["piste"] == 2])

    def test_reprise_de_piste_garde_les_signatures(self):
        chaine = self.chaine({1: navire(), 4: navire()})
        derouler(chaine, 0.0, 0.6, (1, 100))
        self.assertIn(1, chaine.reid.en_cours)
        derouler(chaine, 0.6, 0.8, (4, 100))  # même endroit, nouveau numéro : la fiche continue
        self.assertIn(4, chaine.reid.en_cours)
        self.assertNotIn(1, chaine.reid.en_cours)


class TestContratStationSol(unittest.TestCase):
    def test_alerte_avec_deja_vu_acceptee_par_la_station_sol(self):
        chemin = Path(__file__).resolve().parents[3] / "station_sol" / "contrat.py"
        if not chemin.exists():
            self.skipTest("station_sol absente")
        spec = importlib.util.spec_from_file_location("contrat_station", chemin)
        contrat = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contrat)
        a = navire()
        chaine = TestChaineAvecReid().chaine({1: a, 5: a})
        t = derouler(chaine, 0.0, 2.0, (1, 700))
        derouler(chaine, t + 10, t + 12, (5, 100))
        self.assertIn("deja_vu", chaine.alertes[-1])
        for message in chaine.emetteur.messages:
            self.assertEqual(contrat.verifier(message), [], message)


if __name__ == "__main__":
    unittest.main()


class TestMesure(unittest.TestCase):
    def test_mesure_sur_signatures_synthetiques(self):
        from chaine.outils.mesurer_reid import evaluer_memoire, paires, proposer_seuils
        signatures = {f"N{i}": np.stack([vue(base, 0.3) for _ in range(4)])
                      for i, base in enumerate(navire() for _ in range(10))}
        p = paires(signatures)
        self.assertEqual((p["paires_meme_navire"], p["paires_differentes"]), (60, 720))
        r = evaluer_memoire(signatures, ReglagesReid(), tirages=3)
        self.assertEqual(r["taux_fausse_reconnaissance"], 0.0)
        self.assertGreater(r["taux_reconnaissance"], 0.9)
        self.assertEqual(r["requetes"], 3 * (5 * 2 + 5 * 4))
        self.assertIsNotNone(proposer_seuils(signatures, 2, 2)["seuil_sur_propose"])

    def test_mesure_detecte_les_confusions(self):
        from chaine.outils.mesurer_reid import evaluer_memoire
        a = navire()
        jumeaux = {f"N{i}": np.stack([vue(a, 0.3) for _ in range(4)]) for i in range(6)}
        r = evaluer_memoire(jumeaux, ReglagesReid(marge=0.0), tirages=2)
        self.assertGreater(r["taux_fausse_reconnaissance"], 0.5)
        r = evaluer_memoire(jumeaux, ReglagesReid(), tirages=2)  # la marge refuse de choisir entre des jumeaux
        self.assertEqual(r["connu_pris_pour_un_autre"], 0)
