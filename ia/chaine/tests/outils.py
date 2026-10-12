"""Petites fabriques partagées par les tests."""
from chaine.fiche import Etat, FicheNavire, Observation


def observations(t, *pistes):
    """Message du contrat 1. Chaque piste : (id_piste, largeur) ou Observation."""
    liste = []
    for piste in pistes:
        if not isinstance(piste, Observation):
            id_piste, largeur = piste
            piste = Observation(id_piste, (100.0, 100.0, largeur, largeur / 3), 0.8)
        liste.append({"id_piste": piste.id_piste, "boite": list(piste.boite), "confiance": piste.confiance})
    return {"t": t, "pistes": liste}


def fiche_confirmee(largeur=40.0, t=1.0, id_piste=1) -> FicheNavire:
    fiche = FicheNavire.creer(id_piste, 0.0)
    fiche.observer(t, Observation(id_piste, (100.0, 100.0, largeur, largeur / 3), 0.8))
    fiche.decision.etat = Etat.CONFIRMEE
    return fiche
