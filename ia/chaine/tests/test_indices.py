import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chaine.indices import (Mesure, accord_fragments, accord_noms, classer_textes, distance_edition,
                            estimer_mesure, fragment_compatible, longueurs_incompatibles, noms_proches,
                            trajet_impossible)
from chaine.reidentification import PROBABLE, SUR, MemoireNavires, ReglagesReid, normaliser

from .test_reidentification import DIM, memoire_avec, navire, ressemblant, vue

PLAQUE = "BR 538217"


class TestEcriture(unittest.TestCase):
    def test_distance_edition(self):
        self.assertEqual(distance_edition("KOFRIGAN", "KOFRIGAN"), 0)
        self.assertEqual(distance_edition("KOFRIGAN", "KOFRIGAM"), 1)
        self.assertEqual(distance_edition("", "ABC"), 3)

    def test_classer_noms_et_fragments(self):
        noms, fragments = classer_textes({"KOFRIGAN": 2, "BR5387": 1, "BR 53821": 2, "132": 3, "2": 1, "FAX": 1})
        self.assertEqual(noms, {"KOFRIGAN": 2})
        self.assertEqual(fragments, {"BR5387": 1, "BR53821": 2})   # espaces ignorés, chiffres seuls et « FAX » écartés

    def test_noms_proches_tolere_une_faute_de_lecture(self):
        self.assertTrue(noms_proches("KOFRIGAN", "KOFRIGAM"))
        self.assertFalse(noms_proches("KOFRIGAN", "MARIEJEANNE"))

    def test_accord_noms(self):
        self.assertEqual(accord_noms({"KOFRIGAN": 2}, {"KOFRIGAN": 1}), 1.0)
        self.assertEqual(accord_noms({"KOFRIGAN": 1}, {"KOFRIGAN": 3}), 0.5)           # lu une fois : demi-poids
        self.assertEqual(accord_noms({"KOFRIGAN": 2}, {"MARIEJEANNE": 2}), -1.0)       # deux noms bien lus, différents
        self.assertEqual(accord_noms({"KOFRIGAN": 1}, {"MARIEJEANNE": 3}), 0.0)        # une seule lecture : pas de malus
        self.assertEqual(accord_noms({}, {"KOFRIGAN": 3}), 0.0)

    def test_fragment_compatible_avec_l_immatriculation(self):
        self.assertTrue(fragment_compatible("BR5387", PLAQUE))      # chiffres du milieu perdus, une faute
        self.assertTrue(fragment_compatible("BR53821", PLAQUE))
        self.assertTrue(fragment_compatible("BR53827", PLAQUE))     # un chiffre faux
        self.assertFalse(fragment_compatible("GV5387", PLAQUE))     # autre quartier
        self.assertFalse(fragment_compatible("BR9999", PLAQUE))
        self.assertFalse(fragment_compatible("BR538", PLAQUE))      # trop court : trop de navires conviendraient
        self.assertFalse(fragment_compatible("BR5387", None))

    def test_un_fragment_ne_contredit_jamais(self):
        self.assertEqual(accord_fragments({"BR9999": 3}, PLAQUE), 0.0)
        self.assertEqual(accord_fragments({"BR5387": 1}, PLAQUE), 1.0)


class TestTailleEtTrajet(unittest.TestCase):
    def mesure(self, **champs):
        return estimer_mesure(10.0, champs.pop("boite", (900.0, 400.0, 400.0, 150.0)), 2000.0, 66.0,
                              champs.pop("position", (0.0, 0.0)), champs.pop("cap", 0.0),
                              champs.pop("distance", 500.0))

    def test_sans_distance_mesuree_rien_n_est_estime(self):
        m = self.mesure(distance=None)
        self.assertEqual((m.position_m, m.distance_m, m.longueur_m), (None, None, None))

    def test_longueur_en_metres(self):
        m = self.mesure()   # 400 px à 500 m, focale = 1000 / tan(33°)
        focale = 1000.0 / np.tan(np.radians(33.0))
        self.assertAlmostEqual(m.longueur_m, 500.0 * 400.0 / focale, places=3)

    def test_position_droit_devant_et_sur_le_cote(self):
        devant = self.mesure(boite=(800.0, 400.0, 400.0, 150.0))        # centré : cap relatif nul
        self.assertAlmostEqual(devant.position_m[0], 0.0, places=3)
        self.assertAlmostEqual(devant.position_m[1], 500.0, places=3)
        droite = self.mesure(boite=(1500.0, 400.0, 400.0, 150.0))
        self.assertGreater(droite.position_m[0], 0.0)                   # navire à droite d'un drone qui vise le nord

    def test_longueurs_incompatibles(self):
        self.assertTrue(longueurs_incompatibles(10.0, 25.0))
        self.assertFalse(longueurs_incompatibles(20.0, 30.0))           # un navire vu de biais paraît plus court
        self.assertFalse(longueurs_incompatibles(None, 25.0))

    def test_trajet_impossible(self):
        avant = Mesure(0.0, (0.0, 0.0), 300.0, 20.0)
        loin_tot = Mesure(10.0, (3000.0, 0.0), 300.0, 20.0)
        self.assertTrue(trajet_impossible(avant, loin_tot))             # 3 km en 10 s
        self.assertFalse(trajet_impossible(avant, Mesure(10.0, (100.0, 0.0), 300.0, 20.0)))
        self.assertFalse(trajet_impossible(avant, Mesure(600.0, (3000.0, 0.0), 300.0, 20.0)))   # dix minutes : possible
        self.assertFalse(trajet_impossible(avant, Mesure(10.0)))        # position inconnue : on n'écarte pas
        self.assertFalse(trajet_impossible(None, loin_tot))


def couleur(forme):
    """Signature de couleur synthétique (3 bandes de 4 valeurs), de norme 1."""
    return normaliser(np.asarray(forme, dtype=np.float32))


BLEU, ROUGE = couleur([1, 0, 0, 0] * 3), couleur([0, 0, 1, 0] * 3)


class TestMemoireAvecIndices(unittest.TestCase):
    def memoire(self, **indices):
        """Un navire en mémoire (apparence `base`) avec ses indices, et sa base pour les pistes suivantes."""
        base = navire()
        memoire = MemoireNavires()
        for _ in range(3):
            memoire.ajouter_vue(1, vue(base), 200, indices.get("couleur"))
        memoire.noter_piste(1, textes=indices.get("textes"), mesure=indices.get("mesure"))
        memoire.enregistrer(1, 1.0, indices.get("immat", PLAQUE), ["peche"])
        return memoire, base

    def piste(self, memoire, base, similarite_visuelle, **indices):
        cible = ressemblant(base, similarite_visuelle)
        for _ in range(3):
            memoire.ajouter_vue(7, vue(cible, 0.05), 200, indices.get("couleur"))
        memoire.noter_piste(7, textes=indices.get("textes"), mesure=indices.get("mesure"))
        return memoire.rechercher(7, ["peche"])

    def test_sans_indices_comme_avant(self):
        memoire, base = self.memoire()
        trouve = self.piste(memoire, base, 0.95)
        self.assertEqual(trouve.niveau, SUR)
        self.assertEqual(trouve.indices["bonus"], 0.0)

    def test_couleur_differente_retrograde_un_sur(self):
        memoire, base = self.memoire(couleur=BLEU)
        meme = self.piste(memoire, base, 0.915, couleur=BLEU)
        self.assertEqual(meme.niveau, SUR)
        memoire.oublier(7)
        autre = self.piste(memoire, base, 0.915, couleur=ROUGE)      # même forme, autre couleur
        self.assertEqual(autre.niveau, PROBABLE)
        self.assertLess(autre.similarite, meme.similarite)

    def test_le_nom_aide_a_reconnaitre(self):
        memoire, base = self.memoire(textes={"KOFRIGAN": 2})
        sans = self.piste(memoire, base, 0.83)
        self.assertIsNone(sans)                                         # 0,83 : sous le seuil probable
        memoire.oublier(7)
        avec = self.piste(memoire, base, 0.83, textes={"KOFRIGAN": 2})  # même nom : 0,83 + 0,06
        self.assertIsNotNone(avec)
        self.assertEqual(avec.niveau, PROBABLE)
        self.assertEqual(avec.indices["nom"], 1.0)

    def test_un_fragment_d_immatriculation_aide(self):
        memoire, base = self.memoire()
        memoire.oublier(7)
        trouve = self.piste(memoire, base, 0.83, textes={"BR5387": 1})
        self.assertIsNotNone(trouve)
        self.assertEqual(trouve.indices["fragment"], 1.0)

    def test_les_indices_ne_font_jamais_un_sur_a_eux_seuls(self):
        memoire, base = self.memoire(couleur=BLEU, textes={"KOFRIGAN": 3})
        trouve = self.piste(memoire, base, 0.83, couleur=BLEU, textes={"KOFRIGAN": 3, "BR5387": 2})
        self.assertLessEqual(trouve.indices["bonus"], ReglagesReid().bonus_max + 1e-9)
        self.assertEqual(trouve.niveau, PROBABLE)

    def test_sous_le_plancher_visuel_rien_ne_rattrape(self):
        memoire, base = self.memoire(textes={"KOFRIGAN": 3})
        trouve = self.piste(memoire, base, 0.70, textes={"KOFRIGAN": 3, "BR5387": 2})
        self.assertIsNone(trouve)

    def test_deux_noms_differents_font_baisser_la_ressemblance(self):
        memoire, base = self.memoire(textes={"KOFRIGAN": 3})
        sans = self.piste(memoire, base, 0.97)
        memoire.oublier(7)
        avec = self.piste(memoire, base, 0.97, textes={"MARIEJEANNE": 2})
        self.assertLess(avec.similarite, sans.similarite)

    def test_longueur_tres_differente_ecarte(self):
        memoire, base = self.memoire(mesure=Mesure(1.0, None, 300.0, 12.0))
        trouve = self.piste(memoire, base, 0.95, mesure=Mesure(5.0, None, 300.0, 40.0))
        self.assertIsNone(trouve)
        memoire.oublier(7)
        self.assertIsNotNone(self.piste(memoire, base, 0.95, mesure=Mesure(5.0, None, 300.0, 15.0)))

    def test_trajet_impossible_ecarte(self):
        memoire, base = self.memoire(mesure=Mesure(1.0, (0.0, 0.0), 300.0, 20.0))
        impossible = self.piste(memoire, base, 0.95, mesure=Mesure(5.0, (4000.0, 0.0), 300.0, 20.0))
        self.assertIsNone(impossible)
        memoire.oublier(7)
        self.assertIsNotNone(self.piste(memoire, base, 0.95, mesure=Mesure(5.0, (50.0, 0.0), 300.0, 20.0)))

    def test_renommer_garde_le_profil(self):
        memoire, base = self.memoire(textes={"KOFRIGAN": 2})
        memoire.noter_piste(7, textes={"KOFRIGAN": 2})
        memoire.renommer(7, 9)
        self.assertIn(9, memoire.profils)
        self.assertNotIn(7, memoire.profils)

    def test_enregistrer_cumule_les_indices_sur_une_meme_immatriculation(self):
        memoire, base = self.memoire(couleur=BLEU, textes={"KOFRIGAN": 2})
        memoire.ajouter_vue(7, vue(base), 200, BLEU)
        memoire.noter_piste(7, textes={"KOFRIGAN": 1, "BR5387": 1}, mesure=Mesure(9.0, None, 200.0, 18.0))
        navire_connu = memoire.enregistrer(7, 9.0, PLAQUE, ["peche"])
        self.assertEqual(navire_connu.noms, {"KOFRIGAN": 3})
        self.assertEqual(navire_connu.fragments, {"BR5387": 1})
        self.assertEqual(navire_connu.longueur_m, 18.0)

    def test_sauvegarde_et_rechargement(self):
        memoire, base = self.memoire(couleur=BLEU, textes={"KOFRIGAN": 2},
                                     mesure=Mesure(1.0, (5.0, 5.0), 300.0, 22.0))
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "navires"
            memoire.sauver(chemin)
            rechargee = MemoireNavires.charger(chemin)
        n = rechargee.navires[1]
        self.assertEqual((n.noms, n.longueur_m), ({"KOFRIGAN": 2}, 22.0))
        self.assertTrue(np.allclose(n.couleurs, memoire.navires[1].couleurs))
        self.assertIsNone(n.mesure)    # position d'une autre mission : oubliée au rechargement

    def test_lecture_d_une_memoire_de_version_1(self):
        memoire, _ = self.memoire()
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "navires"
            memoire.sauver(chemin)
            meta = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
            meta["version"] = 1
            for n in meta["navires"]:
                for cle in ("noms", "fragments", "longueur_m", "couleurs"):
                    n.pop(cle, None)
            chemin.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
            ancienne = MemoireNavires.charger(chemin)
        n = ancienne.navires[1]
        self.assertEqual((n.noms, n.longueur_m, n.couleurs), ({}, None, None))


if __name__ == "__main__":
    unittest.main()
