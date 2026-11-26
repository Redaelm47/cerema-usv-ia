"""Boucle principale : observations du suivi -> fiches -> décideur -> un expert -> alerte.

Aucune étape n'attend un humain : chaque image est traitée jusqu'au bout avec ce que l'on sait.
"""
import time
from typing import TYPE_CHECKING, Any, Iterable, Protocol

from . import contrats
from .decideur import Action, actualiser_etat, decider
from .experts.base import Expert, Image, Resultat, recadrer
from .fiche import Boite, Etat, FicheNavire, Observation
from .indices import Mesure, estimer_mesure
from .journal import Journal
from .messages import Emetteur, EmetteurMemoire
from .reglages import Contexte, Reglages

if TYPE_CHECKING:  # NumPy n'est demandé que si la ré-identification est active
    from .reidentification import MemoireNavires

EXPERT_DE_L_ACTION = {Action.EXPERT_TYPE: "type", Action.EXPERT_OCR: "ocr", Action.APPROCHE: "approche"}
REGARDENT_L_IMAGE = ("type", "ocr")  # experts précédés du filtre qualité


def recouvrement(a: Boite, b: Boite) -> float:
    """Intersection sur union de deux boîtes x, y, largeur, hauteur."""
    largeur = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    hauteur = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if largeur <= 0 or hauteur <= 0:
        return 0.0
    return largeur * hauteur / (a[2] * a[3] + b[2] * b[3] - largeur * hauteur)


class Drone(Protocol):
    def contexte(self, t: float) -> Contexte: ...


class Chaine:
    def __init__(self, experts: Iterable[Expert], reglages: Reglages | None = None,
                 journal: Journal | None = None, emetteur: Emetteur | None = None, drone: Drone | None = None,
                 reid: "MemoireNavires | None" = None):
        self.experts = {e.nom: e for e in experts}
        self.reid = reid  # mémoire des navires déjà signalés ; None : pas de ré-identification
        self.reglages = reglages or Reglages()
        self.journal = journal or Journal()
        self.emetteur = emetteur or EmetteurMemoire()
        self.drone = drone
        self.fiches: dict[int, FicheNavire] = {}
        self.alertes: list[dict[str, Any]] = []
        self._dernier_etat: float | None = None
        # Par piste en attente de lecture : l'image la plus nette vue depuis le dernier essai
        # (date, recadrage, avis du filtre qualité).
        self._plus_nettes: dict[int, tuple[float, Image, Resultat]] = {}

    def pas(self, observations: dict[str, Any], image: Image = None, contexte: Contexte | None = None) -> None:
        """Traite une image : met à jour les fiches, puis lance au plus un expert.

        `observations` est le message du contrat 1, `image` l'image pleine résolution qui va avec.
        """
        t, pistes = contrats.lire_observations(observations)
        if contexte is None:
            contexte = self.drone.contexte(t) if self.drone is not None else Contexte()
        self._mettre_a_jour_les_fiches(t, pistes)
        self._retenir_les_images_nettes(t, image)

        expert_lance = False
        for fiche in sorted(self.fiches.values(), key=lambda f: f.suivi.premiere_vue):
            action, raison = decider(fiche, t, contexte, self.reglages)
            if action == Action.ATTENDRE:
                continue
            if action in EXPERT_DE_L_ACTION:
                if not expert_lance:  # un seul expert à la fois
                    expert_lance = self._lancer_expert(t, fiche, action, raison, image, contexte)
            else:
                self._alerter(t, fiche, action, raison)
        self._envoyer_etat(t, contexte)

    def cloturer(self, t: float) -> None:
        """Fin de la mission ou de la vidéo : alerte partielle pour chaque navire encore en cours d'identification."""
        for fiche in sorted(self.fiches.values(), key=lambda f: f.suivi.premiere_vue):
            if fiche.decision.etat in (Etat.CONFIRMEE, Etat.EN_APPROCHE):
                self._alerter(t, fiche, Action.ALERTE_PARTIELLE, "fin de la mission")

    # Fiches

    def _mettre_a_jour_les_fiches(self, t: float, pistes: list) -> None:
        vues = {obs.id_piste for obs in pistes}
        for obs in pistes:
            fiche = self.fiches.get(obs.id_piste)
            if fiche is None:
                fiche = self._reprendre(t, obs, vues) or FicheNavire.creer(obs.id_piste, t)
                self.fiches[obs.id_piste] = fiche
            fiche.observer(t, obs, self.reglages.confiance_confirmation)
        for id_piste, fiche in list(self.fiches.items()):
            if id_piste not in vues:
                fiche.manquer()
            actualiser_etat(fiche, t, self.reglages)
            oubliable = fiche.decision.etat in (Etat.ALERTEE, Etat.ECARTEE, Etat.NOUVELLE) or (
                fiche.decision.etat == Etat.PERDUE and decider(fiche, t, Contexte(), self.reglages)[0] == Action.ATTENDRE)
            if oubliable and t - fiche.suivi.derniere_vue > self.reglages.delai_oubli_s:
                del self.fiches[id_piste]
                if self.reid is not None:
                    self.reid.oublier(id_piste)

    def _reprendre(self, t: float, obs: Observation, vues: set[int]) -> FicheNavire | None:
        """Le suivi a donné un nouveau numéro à un navire déjà suivi : la fiche continue sous ce numéro.

        Reconnu par la position seule, et de façon stricte : une fiche disparue depuis moins de
        `delai_reprise_s`, dont la dernière boîte recouvre la nouvelle. Confondre deux navires ferait
        disparaître l'un des deux ; dans le doute, ou s'il y a plusieurs fiches possibles, le navire
        reçoit une nouvelle fiche, quitte à produire une alerte en double.
        Une règle plus souple (centres proches, sans recouvrement) a été essayée sur la scène Blender :
        elle ne réduisait pas les doublons d'un navire lointain, parce que la caméra bouge trop entre
        deux détections. Le remède est dans le suivi : compenser le mouvement de la caméra.
        """
        r = self.reglages
        possibles = [ancien for ancien, fiche in self.fiches.items()
                     if ancien not in vues and fiche.decision.etat not in (Etat.NOUVELLE, Etat.PERDUE)
                     and t - fiche.suivi.derniere_vue <= r.delai_reprise_s
                     and recouvrement(fiche.suivi.boite, obs.boite) >= r.recouvrement_reprise]
        if len(possibles) != 1:
            return None
        ancien = possibles[0]
        fiche = self.fiches.pop(ancien)
        if ancien in self._plus_nettes:
            self._plus_nettes[obs.id_piste] = self._plus_nettes.pop(ancien)
        fiche.id_piste = obs.id_piste
        for expert in self.experts.values():
            if hasattr(expert, "renommer"):
                expert.renommer(ancien, obs.id_piste)
        if self.reid is not None:
            self.reid.renommer(ancien, obs.id_piste)
        if self.drone is not None and getattr(self.drone, "cible", None) == ancien:
            self.drone.cible = obs.id_piste
        self._noter(t, fiche, "reprise_piste", f"la piste {ancien} continue sous le numéro {obs.id_piste}")
        return fiche

    def navires_suivis(self, t: float) -> int:
        """Navires confirmés encore visibles."""
        return sum(1 for f in self.fiches.values()
                   if f.decision.etat in (Etat.CONFIRMEE, Etat.EN_APPROCHE, Etat.ALERTEE)
                   and t - f.suivi.derniere_vue <= self.reglages.delai_perte_s)

    # Experts

    def _retenir_les_images_nettes(self, t: float, image: Image) -> None:
        """Pour chaque navire à lire, garde le recadrage le plus net vu depuis le dernier essai de lecture.

        Deux essais de lecture sont espacés de `intervalle_essais_s` : plutôt que de lire l'image qui tombe
        à ce moment-là, l'expert OCR recevra la plus nette de l'intervalle. Le coût est une mesure de
        netteté par navire et par image, sans réseau.
        """
        qualite, ocr = self.experts.get("qualite"), self.experts.get("ocr")
        if image is None or qualite is None or not hasattr(qualite, "evaluer") or not hasattr(ocr, "lire_recadrage"):
            return
        r = self.reglages
        for fiche in self.fiches.values():
            essais = fiche.decision.tentatives
            a_lire = (fiche.decision.etat in (Etat.CONFIRMEE, Etat.EN_APPROCHE) and fiche.suivi.derniere_vue == t
                      and not fiche.immatriculation_connue
                      and ((fiche.largeur_px >= r.seuil_ocr_px and essais.get("ocr", 0) < r.max_tentatives_ocr)
                           or (r.seuil_ocr_essai_px <= fiche.largeur_px < r.seuil_ocr_px
                               and essais.get("ocr_precoce", 0) < r.max_essais_ocr_precoces)))
            if not a_lire:
                self._plus_nettes.pop(fiche.id_piste, None)
                continue
            recadrage = recadrer(image, fiche.suivi.boite, getattr(ocr, "marge", 0.0))
            avis = qualite.evaluer(recadrage)
            retenue = self._plus_nettes.get(fiche.id_piste)
            if retenue is None or avis.valeurs.get("nettete", 0.0) > retenue[2].valeurs.get("nettete", 0.0):
                self._plus_nettes[fiche.id_piste] = (t, recadrage.copy(), avis)

    def _lancer_expert(self, t: float, fiche: FicheNavire, action: Action, raison: str, image: Image,
                       contexte: Contexte) -> bool:
        """Lance l'expert de l'action. Renvoie False si le filtre qualité a écarté l'image avant."""
        nom = EXPERT_DE_L_ACTION[action]
        decision, interne = fiche.decision, fiche.interne
        interne.dernier_essai[nom] = t

        nette = self._plus_nettes.pop(fiche.id_piste, None) if nom == "ocr" else None
        if nom in REGARDENT_L_IMAGE and image is not None and "qualite" in self.experts:
            qualite = nette[2] if nette else self.experts["qualite"].lancer(fiche, image)
            interne.nettete = qualite.valeurs.get("nettete")
            if not qualite.reussi:
                interne.rejets_qualite[nom] = interne.rejets_qualite.get(nom, 0) + 1
                if interne.rejets_qualite[nom] >= self.reglages.max_rejets_qualite:
                    interne.rejets_qualite[nom] = 0
                    self._compter_tentative(fiche, nom)
                self._noter(t, fiche, "filtre_qualite", f"{qualite.valeurs.get('raison')} (avant {action.value})",
                            reussi=False, details=qualite.valeurs)
                return False
            interne.rejets_qualite[nom] = 0

        self._compter_tentative(fiche, nom)
        debut = time.perf_counter()
        if nette:
            resultat: Resultat = self.experts[nom].lire_recadrage(fiche, nette[1])
        else:
            resultat = self.experts[nom].lancer(fiche, image)
        duree_ms = (time.perf_counter() - debut) * 1000

        valeurs = dict(resultat.valeurs)
        signature, largeur_recadrage = valeurs.pop("signature", None), valeurs.pop("largeur_recadrage", None)
        couleur = valeurs.pop("couleur", None)
        if nette:
            valeurs["image_lue_t"] = round(nette[0], 2)  # date de l'image choisie, la plus nette
        if nom == "type" and resultat.reussi:
            fiche.experts.types = list(valeurs["types"])
            fiche.experts.confiance_type = float(valeurs.get("confiance", 0.0))
            if signature is not None:
                self._reidentifier(t, fiche, signature, largeur_recadrage or fiche.largeur_px, couleur,
                                   self._mesure(t, fiche, image, contexte))
        elif nom == "ocr":
            if not resultat.reussi:
                resultat = self._lecture_confirmee_par_reid(fiche, resultat, valeurs)
            if resultat.reussi:
                fiche.experts.immatriculation = valeurs["immatriculation"]
                fiche.experts.confiance_immatriculation = float(valeurs.get("confiance", 0.0))
            for texte in valeurs.get("hors_format", []):
                if sum(c.isalnum() for c in texte) >= 3:
                    interne.textes_lus[texte] = interne.textes_lus.get(texte, 0) + 1
            interne.lecture_candidate = valeurs.get("candidate", valeurs.get("immatriculation"))
            interne.confiance_candidate = float(valeurs.get("confiance", 0.0))
            if self.reid is not None:   # noms et débuts d'immatriculation lus : indices de plus pour la mémoire
                self.reid.noter_piste(fiche.id_piste, textes=interne.textes_lus,
                                      mesure=self._mesure(t, fiche, image, contexte))
                self._signature_de_pres(t, fiche, image, contexte)
                self._rechercher_reid(t, fiche)
        elif nom == "approche" and resultat.reussi:
            decision.etat = Etat.EN_APPROCHE
            decision.debut_approche = t
            interne.largeur_debut_approche = fiche.largeur_px
            interne.batterie_debut_approche = contexte.batterie
            interne.consigne = dict(valeurs)

        self.emetteur.envoyer(contrats.message_decision(t, fiche.id_piste, action.value, raison))
        self._noter(t, fiche, action.value, raison, reussi=resultat.reussi, duree_ms=round(duree_ms, 2),
                    details=valeurs)
        if nom == "type" and resultat.reussi and not valeurs.get("navire", True) \
                and valeurs.get("essais", 1) >= self.reglages.essais_pour_ecarter:
            self._ecarter(t, fiche, valeurs["essais"])
        return True

    def _ecarter(self, t: float, fiche: FicheNavire, essais: int) -> None:
        """L'expert type a dit « pas un navire » sur assez d'essais : ni alerte, ni approche, rien vers la station sol."""
        if fiche.decision.debut_approche is not None and hasattr(self.experts.get("approche"), "terminer"):
            self.experts["approche"].terminer(fiche)
        for expert in self.experts.values():
            if hasattr(expert, "oublier"):
                expert.oublier(fiche.id_piste)
        fiche.decision.etat = Etat.ECARTEE
        self._noter(t, fiche, "ecartee", f"pas un navire selon l'expert type ({essais} essais)")

    def _compter_tentative(self, fiche: FicheNavire, nom: str) -> None:
        if nom == "ocr" and fiche.largeur_px < self.reglages.seuil_ocr_px:
            nom = "ocr_precoce"  # budget à part, voir Reglages.max_essais_ocr_precoces
        fiche.decision.tentatives[nom] = fiche.decision.tentatives.get(nom, 0) + 1
        if nom == "type":
            fiche.interne.largeur_dernier_type = fiche.largeur_px

    # Alertes et messages

    def _alerter(self, t: float, fiche: FicheNavire, action: Action, raison: str) -> None:
        if fiche.decision.debut_approche is not None and hasattr(self.experts.get("approche"), "terminer"):
            self.experts["approche"].terminer(fiche)
        for expert in self.experts.values():
            if hasattr(expert, "oublier"):
                expert.oublier(fiche.id_piste)
        complete = action == Action.ALERTE_COMPLETE
        lue = fiche.experts.immatriculation if complete else None  # seule une immatriculation validée prouve l'identité
        if not complete and fiche.interne.lecture_candidate and not fiche.immatriculation_connue:
            # Lecture non validée par le vote : transmise telle quelle, avec sa confiance, dans l'alerte partielle.
            fiche.experts.immatriculation = fiche.interne.lecture_candidate
            fiche.experts.confiance_immatriculation = fiche.interne.confiance_candidate
        fiche.decision.etat = Etat.ALERTEE
        deja_vu = self._memoriser(t, fiche, lue)
        alerte = contrats.message_alerte(t, fiche, complete, raison, self._textes_hors_format(fiche),
                                         deja_vu.message() if deja_vu else None)
        self.alertes.append(alerte)
        self.emetteur.envoyer(contrats.message_decision(t, fiche.id_piste, action.value, raison))
        self.emetteur.envoyer(alerte)
        self._noter(t, fiche, action.value, raison)

    # Ré-identification

    def _pistes_visibles(self, sauf: int) -> set[int]:
        """Pistes vues pendant la vie de la piste `sauf` : deux navires vus en même temps sont deux navires,
        quelle que soit leur ressemblance. Intervalles de vie qui se chevauchent, pas seulement l'image courante."""
        fiche = self.fiches.get(sauf)
        if fiche is None:
            return set()
        debut, fin = fiche.suivi.premiere_vue, fiche.suivi.derniere_vue
        return {f.id_piste for f in self.fiches.values()
                if f.id_piste != sauf and f.suivi.premiere_vue <= fin and debut <= f.suivi.derniere_vue}

    def _mesure(self, t: float, fiche: FicheNavire, image: Image, contexte: Contexte) -> Mesure | None:
        """Position et longueur du navire d'après la distance MESURÉE par le drone, None s'il n'y en a pas
        (simulation : la distance de l'approche vient d'une longueur supposée, voir indices.py)."""
        if contexte.cible != fiche.id_piste or not contexte.distance_navire_m:
            return None
        largeur_image = image.shape[1] if image is not None else self.reglages.largeur_image_px
        return estimer_mesure(t, fiche.suivi.boite, largeur_image, self.reglages.champ_horizontal_deg,
                              contexte.position_m, contexte.cap_deg, contexte.distance_navire_m)

    def _signature_de_pres(self, t: float, fiche: FicheNavire, image: Image, contexte: Contexte) -> None:
        """Le navire est assez gros pour être lu, donc assez gros pour une bonne signature : si la mémoire n'en a
        encore aucune (le type est souvent passé quand le navire est trop petit), on en prend une, avec la couleur.
        Sans cela, un navire dont l'immatriculation est lue entrerait en mémoire sans rien pour le reconnaître."""
        expert = self.experts.get("type")
        if (self.reid is None or image is None or expert is None or len(self.reid.signatures(fiche.id_piste))
                or fiche.largeur_px < self.reid.reglages.largeur_min_px):
            return
        resultat = expert.lancer(fiche, image)
        signature = resultat.valeurs.get("signature") if resultat.reussi else None
        if signature is not None:
            self._reidentifier(t, fiche, signature, resultat.valeurs.get("largeur_recadrage") or fiche.largeur_px,
                               resultat.valeurs.get("couleur"), self._mesure(t, fiche, image, contexte))

    def _reidentifier(self, t: float, fiche: FicheNavire, signature: Any, largeur_px: float,
                      couleur: Any = None, mesure: Mesure | None = None) -> None:
        """Nouvelle signature de la piste : cherche si elle ressemble à un navire déjà signalé."""
        if self.reid is None:
            return
        if mesure is not None:
            self.reid.noter_piste(fiche.id_piste, mesure=mesure)
        if not self.reid.ajouter_vue(fiche.id_piste, signature, largeur_px, couleur):
            return
        self._rechercher_reid(t, fiche)

    def _rechercher_reid(self, t: float, fiche: FicheNavire) -> None:
        """Cherche si la piste, avec tout ce que l'on sait d'elle, ressemble à un navire déjà signalé."""
        avant = fiche.interne.deja_vu
        apres = self.reid.rechercher(fiche.id_piste, fiche.experts.types, self._pistes_visibles(fiche.id_piste))
        fiche.interne.deja_vu = apres
        if apres is not None and (avant is None or avant.navire.numero != apres.navire.numero
                                  or avant.niveau != apres.niveau):
            self._noter(t, fiche, "reidentification",
                        f"ressemble au navire {apres.navire.immatriculation or 'sans immatriculation'} "
                        f"({apres.niveau}, {apres.similarite:.2f})", details=apres.journal())
        elif apres is None and avant is not None:
            self._noter(t, fiche, "reidentification", "ne ressemble plus assez à un navire déjà signalé")

    def _lecture_confirmee_par_reid(self, fiche: FicheNavire, resultat: Resultat,
                                    valeurs: dict[str, Any]) -> Resultat:
        """Une lecture seule ne suffit pas au vote ; elle suffit si elle donne exactement l'immatriculation
        du navire que l'apparence reconnaît : deux indices indépendants concordent."""
        deja_vu, lue = fiche.interne.deja_vu, valeurs.get("lue")
        if (self.reid is None or not self.reglages.reid_valider_une_lecture or deja_vu is None
                or deja_vu.navire.immatriculation is None or lue is None
                or lue != deja_vu.navire.immatriculation or valeurs.get("candidate") != lue):
            return resultat
        valeurs["immatriculation"] = lue
        valeurs["raison"] = "lecture confirmée par la ré-identification"
        return Resultat(True, valeurs)

    def _memoriser(self, t: float, fiche: FicheNavire, immatriculation: str | None) -> Any:
        """À l'alerte : ce que la mémoire sait déjà de ce navire, puis le navire entre en mémoire.

        Immatriculation validée : on vérifie que le navire qui la portait déjà lui ressemble. Sinon, on
        cherche par l'apparence seule (le résultat ne sert qu'à informer, jamais à fusionner).
        """
        if self.reid is None:
            return None
        if immatriculation is not None:
            deja_vu = self.reid.verifier(fiche.id_piste, immatriculation)
            if deja_vu is not None and deja_vu.apparence_coherente is False:
                self._noter(t, fiche, "reidentification",
                            f"{immatriculation} déjà signalé sur un navire d'apparence différente",
                            reussi=False, details=deja_vu.journal())
        else:
            deja_vu = self.reid.rechercher(fiche.id_piste, fiche.experts.types,
                                           self._pistes_visibles(fiche.id_piste))
        self.reid.enregistrer(fiche.id_piste, t, immatriculation, list(fiche.experts.types), deja_vu)
        return deja_vu

    def _textes_hors_format(self, fiche: FicheNavire) -> list[str]:
        """Textes lus plusieurs fois sur la coque sans être l'immatriculation : nom, immatriculation étrangère."""
        r = self.reglages
        lus = [(n, texte) for texte, n in fiche.interne.textes_lus.items() if n >= r.lectures_texte_hors_format]
        return [texte for _, texte in sorted(lus, key=lambda x: -x[0])[:r.max_textes_alerte]]

    def _envoyer_etat(self, t: float, contexte: Contexte) -> None:
        if self._dernier_etat is not None and t - self._dernier_etat < self.reglages.periode_etat_s:
            return
        self._dernier_etat = t
        self.emetteur.envoyer(contrats.message_etat(t, contexte.mode, contexte.batterie, self.navires_suivis(t),
                                                    contexte.temperature_pi))

    def _noter(self, t: float, fiche: FicheNavire, action: str, raison: str, **suite: Any) -> None:
        self.journal.noter(t=round(t, 2), piste=fiche.id_piste, action=action, raison=raison, **suite,
                           fiche=fiche.contrat(), nettete=fiche.interne.nettete)
