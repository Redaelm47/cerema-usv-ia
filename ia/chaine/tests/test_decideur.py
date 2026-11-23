import unittest

from chaine.decideur import Action, actualiser_etat, decider
from chaine.fiche import Etat, FicheNavire, Observation
from chaine.garde_fous import approche_a_abandonner, approche_autorisee
from chaine.reglages import Contexte, Reglages

from .outils import fiche_confirmee

R = Reglages(seuil_ocr_essai_px=float("inf"))
T = 1.0


def action(fiche, t=T, contexte=None, reglages=R):
    return decider(fiche, t, contexte or Contexte(), reglages)


def fiche_typee(largeur=40.0, t=T):
    fiche = fiche_confirmee(largeur, t)
    fiche.experts.types = ["chalutier"]
    return fiche


def fiche_en_approche(largeur=200.0, debut=T, t=T):
    fiche = fiche_typee(largeur, t)
    fiche.decision.etat = Etat.EN_APPROCHE
    fiche.decision.debut_approche = debut
    fiche.decision.tentatives["approche"] = 1
    fiche.interne.largeur_debut_approche = 200.0
    return fiche


class TestLecturePrecoce(unittest.TestCase):
    """On tente de lire avant le seuil d'approche, avec un budget d'essais à part."""
    P = Reglages()

    def test_essai_precoce_sur_un_navire_moyen(self):
        fiche = fiche_typee(largeur=150.0)
        self.assertEqual(action(fiche, reglages=self.P)[0], Action.EXPERT_OCR)

    def test_pas_d_essai_sous_le_seuil_precoce(self):
        fiche = fiche_typee(largeur=self.P.seuil_ocr_essai_px - 10)
        self.assertEqual(action(fiche, reglages=self.P)[0], Action.APPROCHE)

    def test_budget_precoce_epuise_puis_approche(self):
        fiche = fiche_typee(largeur=150.0)
        fiche.decision.tentatives["ocr_precoce"] = self.P.max_essais_ocr_precoces
        self.assertEqual(action(fiche, reglages=self.P)[0], Action.APPROCHE)

    def test_les_essais_precoces_ne_privent_pas_des_essais_a_gros_navire(self):
        fiche = fiche_typee(largeur=self.P.seuil_ocr_px)
        fiche.decision.tentatives["ocr_precoce"] = self.P.max_essais_ocr_precoces
        self.assertEqual(action(fiche, reglages=self.P)[0], Action.EXPERT_OCR)

    def test_immatriculation_lue_tot_evite_l_approche(self):
        fiche = fiche_typee(largeur=150.0)
        fiche.experts.immatriculation = "BR 538217"
        self.assertEqual(action(fiche, reglages=self.P)[0], Action.ALERTE_COMPLETE)


class TestEtats(unittest.TestCase):
    def test_confirmation_apres_trois_images(self):
        fiche = FicheNavire.creer(1, 0.0)
        for i in range(3):
            self.assertEqual(fiche.decision.etat, Etat.NOUVELLE)
            self.assertEqual(action(fiche, 0.2 * i)[0], Action.ATTENDRE)
            fiche.observer(0.2 * i, Observation(1, (0, 0, 40, 13), 0.8))
            actualiser_etat(fiche, 0.2 * i, R)
        self.assertEqual(fiche.decision.etat, Etat.CONFIRMEE)

    def test_trois_images_trop_rapprochees_ne_confirment_pas(self):
        """À 50 images par seconde, trois images durent 40 ms : une vague suffit à les produire."""
        fiche = FicheNavire.creer(1, 0.0)
        for i in range(3):
            fiche.observer(0.02 * i, Observation(1, (0, 0, 40, 13), 0.8))
            actualiser_etat(fiche, 0.02 * i, R)
        self.assertEqual(fiche.decision.etat, Etat.NOUVELLE)
        fiche.observer(R.duree_confirmation_s, Observation(1, (0, 0, 40, 13), 0.8))
        actualiser_etat(fiche, R.duree_confirmation_s, R)
        self.assertEqual(fiche.decision.etat, Etat.CONFIRMEE)

    def test_detection_peu_sure_ne_confirme_pas(self):
        fiche = FicheNavire.creer(1, 0.0)
        for i in range(5):
            fiche.observer(0.2 * i, Observation(1, (0, 0, 40, 13), R.confiance_confirmation - 0.1))
            actualiser_etat(fiche, 0.2 * i, R)
        self.assertEqual(fiche.decision.etat, Etat.NOUVELLE)

    def test_une_image_manquee_remet_le_compte_a_zero(self):
        fiche = FicheNavire.creer(1, 0.0)
        for t, vue in ((0.0, True), (0.2, True), (0.4, False), (0.6, True), (0.8, True)):
            fiche.observer(t, Observation(1, (0, 0, 40, 13), 0.8)) if vue else fiche.manquer()
            actualiser_etat(fiche, t, R)
        self.assertEqual(fiche.decision.etat, Etat.NOUVELLE)

    def test_piste_perdue_apres_le_delai(self):
        fiche = fiche_confirmee()
        fiche.manquer()
        actualiser_etat(fiche, T + R.delai_perte_s - 0.1, R)
        self.assertEqual(fiche.decision.etat, Etat.CONFIRMEE)
        actualiser_etat(fiche, T + R.delai_perte_s + 0.1, R)
        self.assertEqual(fiche.decision.etat, Etat.PERDUE)

    def test_alertee_ne_change_plus(self):
        fiche = fiche_confirmee()
        fiche.decision.etat = Etat.ALERTEE
        actualiser_etat(fiche, 100.0, R)
        self.assertEqual(fiche.decision.etat, Etat.ALERTEE)
        self.assertEqual(action(fiche, 100.0), (Action.ATTENDRE, "alerte déjà envoyée"))

    def test_piste_perdue_sans_rien_savoir(self):
        fiche = fiche_confirmee()
        fiche.decision.etat = Etat.PERDUE
        self.assertEqual(action(fiche, 10.0), (Action.ATTENDRE, "piste perdue"))

    def test_piste_perdue_en_cours_d_identification(self):
        fiche = fiche_typee()
        fiche.decision.etat = Etat.PERDUE
        self.assertEqual(action(fiche, 10.0), (Action.ALERTE_PARTIELLE, "piste perdue"))

    def test_navire_absent_de_l_image(self):
        self.assertEqual(action(fiche_confirmee(700.0), T + 0.2), (Action.ATTENDRE, "navire absent de cette image"))


class TestQuatreQuestions(unittest.TestCase):
    def test_1_type_inconnu(self):
        self.assertEqual(action(fiche_confirmee(700.0)), (Action.EXPERT_TYPE, "type inconnu"))
        self.assertEqual(action(fiche_confirmee(R.largeur_min_type_px)), (Action.EXPERT_TYPE, "type inconnu"))

    def test_1_le_type_passe_avant_l_alerte(self):
        fiche = fiche_confirmee(700.0)
        fiche.experts.immatriculation = "GV 123456"
        self.assertEqual(action(fiche)[0], Action.EXPERT_TYPE)

    def test_1_navire_trop_petit_pour_etre_classe(self):
        self.assertEqual(action(fiche_confirmee(R.largeur_min_type_px - 1))[0], Action.APPROCHE)

    def test_1_tentatives_de_type_epuisees(self):
        fiche = fiche_confirmee(700.0)
        fiche.decision.tentatives["type"] = R.max_tentatives_type
        fiche.interne.largeur_dernier_type = 700.0
        self.assertEqual(action(fiche)[0], Action.EXPERT_OCR)

    def test_1_type_hesitant_reessaye_quand_le_navire_a_grossi(self):
        fiche = fiche_confirmee(100.0)
        fiche.experts.types = ["chalutier", "vedette"]
        fiche.decision.tentatives["type"] = R.max_tentatives_type
        fiche.interne.largeur_dernier_type = 100.0
        self.assertEqual(action(fiche)[0], Action.APPROCHE)
        fiche.suivi.boite = (100.0, 100.0, 160.0, 50.0)
        self.assertEqual(action(fiche), (Action.EXPERT_TYPE, "type hésitant, navire plus gros"))

    def test_2_immatriculation_lue(self):
        fiche = fiche_typee(40.0)
        fiche.experts.immatriculation = "GV 123456"
        self.assertEqual(action(fiche), (Action.ALERTE_COMPLETE, "immatriculation lue"))

    def test_3_navire_assez_gros(self):
        self.assertEqual(action(fiche_typee(R.seuil_ocr_px)), (Action.EXPERT_OCR, "navire assez gros pour lire"))
        self.assertNotEqual(action(fiche_typee(R.seuil_ocr_px - 1))[0], Action.EXPERT_OCR)

    def test_3_tentatives_de_lecture_epuisees(self):
        fiche = fiche_typee(700.0)
        fiche.decision.tentatives["ocr"] = R.max_tentatives_ocr
        self.assertEqual(action(fiche), (Action.ALERTE_PARTIELLE, "immatriculation illisible"))

    def test_4_approche_permise(self):
        self.assertEqual(action(fiche_typee(40.0)), (Action.APPROCHE, "navire trop petit pour lire"))

    def test_4_approche_refusee(self):
        self.assertEqual(action(fiche_typee(40.0), contexte=Contexte(batterie=0.1)),
                         (Action.ALERTE_PARTIELLE, "batterie trop basse"))

    def test_4_une_seule_approche_a_la_fois(self):
        occupe = Contexte(mode="approche", cible=99)
        self.assertEqual(action(fiche_typee(40.0), contexte=occupe), (Action.ATTENDRE, "une autre approche est en cours"))
        self.assertEqual(action(fiche_typee(700.0), contexte=occupe)[0], Action.EXPERT_OCR)   # lire reste possible

    def test_attente_entre_deux_essais_du_meme_expert(self):
        fiche = fiche_typee(700.0)
        fiche.decision.tentatives["ocr"] = 1
        fiche.interne.dernier_essai["ocr"] = T - 0.1
        self.assertEqual(action(fiche), (Action.ATTENDRE, "attente avant un nouvel essai"))
        fiche.interne.dernier_essai["ocr"] = T - R.intervalle_essais_s
        self.assertEqual(action(fiche)[0], Action.EXPERT_OCR)


class TestApprocheEnCours(unittest.TestCase):
    def test_on_attend_que_le_navire_grossisse(self):
        self.assertEqual(action(fiche_en_approche()), (Action.ATTENDRE, "approche en cours"))

    def test_lecture_des_que_le_navire_est_assez_gros(self):
        self.assertEqual(action(fiche_en_approche(largeur=650.0))[0], Action.EXPERT_OCR)

    def test_illisible_malgre_l_approche(self):
        fiche = fiche_en_approche(largeur=650.0)
        fiche.decision.tentatives["ocr"] = R.max_tentatives_ocr
        self.assertEqual(action(fiche), (Action.ALERTE_PARTIELLE, "immatriculation illisible malgré l'approche"))


class TestGardeFous(unittest.TestCase):
    def test_autorisation(self):
        fiche = fiche_typee()
        self.assertEqual(approche_autorisee(fiche, Contexte(), R), (True, "approche autorisée"))
        self.assertEqual(approche_autorisee(fiche, Contexte(dans_la_zone=False), R),
                         (False, "drone hors de la zone autorisée"))
        self.assertEqual(approche_autorisee(fiche, Contexte(batterie=R.batterie_min_approche - 0.01), R),
                         (False, "batterie trop basse"))

    def test_pas_de_seconde_approche(self):
        fiche = fiche_typee()
        fiche.decision.tentatives["approche"] = 1
        self.assertEqual(approche_autorisee(fiche, Contexte(), R), (False, "navire déjà approché"))
        self.assertEqual(action(fiche), (Action.ALERTE_PARTIELLE, "navire déjà approché"))

    def test_abandons(self):
        cas = [
            (dict(), Contexte(dans_la_zone=False), T + 1, "sortie de la zone autorisée"),
            (dict(), Contexte(batterie=0.2), T + 1, "batterie trop basse"),
            (dict(), Contexte(batterie=1.0 - R.energie_max_approche - 0.01), T + 1,
             "énergie maximale d'approche dépassée"),
            (dict(largeur=400.0), Contexte(), T + R.duree_max_approche_s + 1, "durée maximale d'approche dépassée"),
            (dict(largeur=200.0), Contexte(), T + R.delai_eloignement_s + 1,
             "le navire s'éloigne plus vite que le drone"),
            (dict(largeur=400.0), Contexte(distance_m=R.distance_min_m), T + 1,
             "distance minimale atteinte sans pouvoir lire"),
        ]
        for parametres, contexte, t, raison in cas:
            fiche = fiche_en_approche(t=t, **parametres)
            self.assertEqual(approche_a_abandonner(fiche, t, contexte, R), (True, raison))
            self.assertEqual(action(fiche, t, contexte), (Action.ALERTE_PARTIELLE, raison))

    def test_approche_normale_non_abandonnee(self):
        fiche = fiche_en_approche(largeur=400.0, t=T + 30)
        self.assertEqual(approche_a_abandonner(fiche, T + 30, Contexte(batterie=0.95, distance_m=80.0), R), (False, ""))

    def test_aucune_action_n_attend_un_humain(self):
        """Quelle que soit la fiche, le décideur répond tout de suite par une action connue."""
        for largeur in (10.0, 100.0, 1000.0):
            for etat in Etat:
                fiche = fiche_typee(largeur)
                fiche.decision.etat = etat
                self.assertIn(action(fiche)[0], list(Action))


if __name__ == "__main__":
    unittest.main()
