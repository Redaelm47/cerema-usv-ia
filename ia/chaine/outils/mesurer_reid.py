"""Mesure la ré-identification sur des photos de navires, et propose des seuils.

    python3 -m chaine.outils.mesurer_reid ../data/reid --rapport runs/mesure_reid.json
    python3 -m chaine.outils.mesurer_reid ../data/reid --signatures runs/signatures_reid.npz   (recalcul évité)

Le dossier contient UN SOUS-DOSSIER PAR NAVIRE, nommé par son identité (immatriculation ou autre), avec
plusieurs images de ce navire, déjà recadrées sur lui (une boîte de détection, pas la photo entière) :

    ../data/reid/GV_642410/vue1.jpg, vue2.jpg ...
    ../data/reid/navire_0042/...

Deux mesures :

1. **Paires** : similarité d'une vue contre une vue, pour toutes les paires du même navire et de navires
   différents. Donne, pour chaque seuil, la part de paires du même navire reconnues et la part de paires
   de navires différents confondues (la mesure de ARCHITECTURE.md, refaite).
2. **Mémoire**, exactement comme dans la chaîne (`MemoireNavires`, mêmes règles de marge) : la moitié des
   navires est mise en mémoire avec quelques vues, comme s'ils avaient été alertés ; puis chaque autre vue
   est présentée comme une nouvelle piste. Les navires jamais mis en mémoire servent d'intrus : les
   reconnaître est une fausse reconnaissance, l'erreur qui compte. Répété sur plusieurs tirages.

Les seuils proposés : le plus bas `seuil_sur` sans aucune fausse reconnaissance, et le plus bas
`seuil_probable` sous 2 % de fausses reconnaissances. Avec peu de navires, ce sont des ordres de grandeur.
"""
import argparse
import json
import random
from pathlib import Path

import numpy as np

from ..reidentification import PROBABLE, SUR, MemoireNavires, ReglagesReid

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SEUILS = [round(s, 2) for s in np.arange(0.70, 0.971, 0.01)]


def lister(dossier: Path) -> dict[str, list[Path]]:
    navires = {}
    for sous_dossier in sorted(p for p in dossier.iterdir() if p.is_dir()):
        images = sorted(p for p in sous_dossier.iterdir() if p.suffix.lower() in EXTENSIONS)
        if images:
            navires[sous_dossier.name] = images
    return navires


def calculer_signatures(navires: dict[str, list[Path]], reseau: str, fils: int | None,
                        cache: Path | None) -> dict[str, np.ndarray]:
    if cache is not None and cache.exists():
        with np.load(cache) as donnees:
            signatures = {nom: donnees[nom] for nom in donnees.files}
        if set(signatures) == set(navires):
            print(f"signatures relues dans {cache}")
            return signatures
    import cv2  # importés ici : l'évaluation seule se teste sans eux

    from ..experts.type import Signature
    calcul = Signature(fils=fils, reseau=reseau)
    signatures = {}
    for nom, images in navires.items():
        vecteurs = []
        for chemin in images:
            image = cv2.imdecode(np.fromfile(str(chemin), np.uint8), cv2.IMREAD_COLOR)  # chemins accentués
            if image is None:
                print(f"illisible, ignorée : {chemin}")
                continue
            vecteurs.append(calcul.calculer(image))
        if vecteurs:
            signatures[nom] = np.stack(vecteurs).astype(np.float32)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, **signatures)
    return signatures


def paires(signatures: dict[str, np.ndarray]) -> dict:
    noms = list(signatures)
    toutes = np.vstack([signatures[n] for n in noms])
    etiquettes = np.concatenate([[i] * len(signatures[n]) for i, n in enumerate(noms)])
    similarites = toutes @ toutes.T
    haut = np.triu_indices(len(toutes), k=1)
    s, meme = similarites[haut], (etiquettes[:, None] == etiquettes[None, :])[haut]
    memes, differents = s[meme], s[~meme]
    lignes = [{"seuil": seuil,
               "meme_navire_reconnu": round(float((memes >= seuil).mean()), 4) if len(memes) else None,
               "navires_differents_confondus": round(float((differents >= seuil).mean()), 4) if len(differents) else None}
              for seuil in SEUILS]
    centiles = lambda x: {f"p{p}": round(float(np.percentile(x, p)), 3) for p in (1, 5, 25, 50, 75, 95, 99)} if len(x) else {}
    return {"paires_meme_navire": int(len(memes)), "paires_differentes": int(len(differents)),
            "similarite_meme_navire": centiles(memes), "similarite_differents": centiles(differents),
            "par_seuil": lignes}


def evaluer_memoire(signatures: dict[str, np.ndarray], reglages: ReglagesReid, tirages: int = 20,
                    vues_en_memoire: int = 2, graine: int = 0) -> dict:
    """Simule la chaîne : navires connus en mémoire, puis vues présentées comme de nouvelles pistes."""
    rng = random.Random(graine)
    compte = {"connu_reconnu_sur": 0, "connu_reconnu_probable": 0, "connu_pris_pour_un_autre": 0,
              "connu_non_reconnu": 0, "intrus_reconnu_a_tort": 0, "intrus_rejete": 0}
    noms = [n for n in signatures if len(signatures[n]) >= 1]
    for _ in range(tirages):
        rng.shuffle(noms)
        en_memoire = noms[:len(noms) // 2]
        memoire, requetes, piste = MemoireNavires(reglages), [], 1
        for nom in en_memoire:
            vues = list(signatures[nom])
            rng.shuffle(vues)
            gardees, restantes = vues[:vues_en_memoire], vues[vues_en_memoire:]
            for v in gardees:
                memoire.ajouter_vue(piste, v, 10 ** 6)
            memoire.enregistrer(piste, float(piste), nom, [])
            piste += 1
            requetes += [(nom, v, True) for v in restantes]
        for nom in noms[len(noms) // 2:]:
            requetes += [(nom, v, False) for v in signatures[nom]]
        for nom, v, connu in requetes:
            memoire.ajouter_vue(piste, v, 10 ** 6)
            trouve = memoire.rechercher(piste)
            memoire.oublier(piste)
            piste += 1
            if not connu:
                compte["intrus_reconnu_a_tort" if trouve else "intrus_rejete"] += 1
            elif trouve is None:
                compte["connu_non_reconnu"] += 1
            elif trouve.navire.immatriculation != nom:
                compte["connu_pris_pour_un_autre"] += 1
            else:
                compte["connu_reconnu_sur" if trouve.niveau == SUR else "connu_reconnu_probable"] += 1
    connus = sum(v for k, v in compte.items() if k.startswith("connu"))
    intrus = compte["intrus_reconnu_a_tort"] + compte["intrus_rejete"]
    faux = compte["connu_pris_pour_un_autre"] + compte["intrus_reconnu_a_tort"]
    reconnus = compte["connu_reconnu_sur"] + compte["connu_reconnu_probable"]
    return {**compte, "requetes": connus + intrus,
            "taux_reconnaissance": round(reconnus / connus, 4) if connus else None,
            "taux_fausse_reconnaissance": round(faux / (connus + intrus), 4) if connus + intrus else None}


def proposer_seuils(signatures: dict[str, np.ndarray], tirages: int, vues_en_memoire: int) -> dict:
    """Balaye les seuils : chaque réponse est comptée comme « sûre » au seuil étudié."""
    balayage = []
    for seuil in SEUILS:
        r = evaluer_memoire(signatures, ReglagesReid(seuil_probable=seuil, seuil_sur=seuil), tirages,
                            vues_en_memoire)
        balayage.append({"seuil": seuil, "reconnaissance": r["taux_reconnaissance"],
                         "fausse_reconnaissance": r["taux_fausse_reconnaissance"]})
    sans_erreur = [b["seuil"] for b in balayage if b["fausse_reconnaissance"] == 0]
    peu_d_erreurs = [b["seuil"] for b in balayage if b["fausse_reconnaissance"] is not None
                     and b["fausse_reconnaissance"] <= 0.02]
    return {"balayage": balayage, "seuil_sur_propose": min(sans_erreur) if sans_erreur else None,
            "seuil_probable_propose": min(peu_d_erreurs) if peu_d_erreurs else None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesure de la ré-identification sur des photos de navires")
    parser.add_argument("dossier", type=Path, help="un sous-dossier par navire, images recadrées dedans")
    parser.add_argument("--reseau", choices=("dinov2", "dinov3"), default="dinov2")
    parser.add_argument("--fils", type=int)
    parser.add_argument("--signatures", type=Path, help="cache .npz des signatures (écrit, puis relu)")
    parser.add_argument("--tirages", type=int, default=20)
    parser.add_argument("--vues-en-memoire", type=int, default=2,
                        help="vues d'un navire connues de la mémoire (l'expert type en voit 2 ou 3 par piste)")
    parser.add_argument("--rapport", type=Path, help="fichier JSON du rapport complet")
    args = parser.parse_args()

    navires = lister(args.dossier)
    if len(navires) < 4:
        parser.error(f"{len(navires)} navire(s) trouvé(s) dans {args.dossier} : il en faut au moins 4")
    signatures = calculer_signatures(navires, args.reseau, args.fils, args.signatures)
    vues = sum(len(v) for v in signatures.values())
    print(f"{len(signatures)} navires, {vues} vues, réseau {args.reseau}\n")

    p = paires(signatures)
    print(f"Paires : {p['paires_meme_navire']} du même navire, {p['paires_differentes']} de navires différents")
    print(f"  similarité, même navire     : {p['similarite_meme_navire']}")
    print(f"  similarité, navires différents : {p['similarite_differents']}")
    print("  seuil   même navire reconnu   navires différents confondus")
    for ligne in p["par_seuil"][::2]:
        print(f"  {ligne['seuil']:.2f}   {ligne['meme_navire_reconnu']!s:>18}   {ligne['navires_differents_confondus']!s:>18}")

    defaut = evaluer_memoire(signatures, ReglagesReid(), args.tirages, args.vues_en_memoire)
    print(f"\nMémoire, réglages actuels (probable {ReglagesReid.seuil_probable}, sûr {ReglagesReid.seuil_sur}, "
          f"marge {ReglagesReid.marge}), {args.tirages} tirages :")
    for cle, valeur in defaut.items():
        print(f"  {cle:<28} {valeur}")

    propositions = proposer_seuils(signatures, args.tirages, args.vues_en_memoire)
    print(f"\nSeuil « sûr » proposé (aucune fausse reconnaissance) : {propositions['seuil_sur_propose']}")
    print(f"Seuil « probable » proposé (2 % au plus)             : {propositions['seuil_probable_propose']}")
    incoherence = p["similarite_meme_navire"].get("p1")
    print(f"Seuil d'incohérence suggéré (1 % des paires du même navire en dessous) : {incoherence}")
    if len(signatures) < 30:
        print(f"\nAttention : {len(signatures)} navires seulement, ces seuils sont des ordres de grandeur.")

    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        rapport = {"navires": len(signatures), "vues": vues, "reseau": args.reseau, "paires": p,
                   "memoire_reglages_actuels": defaut, "propositions": propositions,
                   "seuil_incoherence_suggere": incoherence}
        args.rapport.write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"rapport écrit dans {args.rapport}")


if __name__ == "__main__":
    main()
