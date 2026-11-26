"""Bilan d'une ou plusieurs campagnes du simulateur : tableaux, graphes et résumé.

    python3 ia/simulateur/bridge/bilan.py campagnes/tache_0 campagnes/tache_1 ... --sortie bilan/

Lit les episodes.jsonl écrits par la passerelle (--campagne) et produit dans --sortie :
- episodes.csv : une ligne par épisode ;
- bilan.md : chiffres globaux, puis par météo et par nombre de navires ;
- des graphes PNG (si matplotlib est installé) : taux par météo, hallucinations par heure, distance de détection,
  délai avant l'alerte.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

COLONNES = ["numero", "graine", "zone", "meteo", "heure", "mois", "vent_mps", "houle", "navires_scenario",
            "duree_simulee_s", "images", "navires_vus", "navires_detectes", "navires_alertes", "plaques_a_lire",
            "plaques_lues", "lectures_justes", "lectures_fausses", "alertes", "alertes_completes",
            "alertes_sur_hallucination", "alertes_en_double", "pistes", "pistes_hallucinees",
            "hallucinations_confirmees", "approches", "approches_sur_hallucination", "boites_vraies",
            "boites_fausses", "boites_manquees", "duree_reelle_s"]


def lire(dossiers):
    episodes = []
    for d in dossiers:
        for f in sorted(Path(d).rglob("episodes.jsonl")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                if ligne.strip():
                    e = json.loads(ligne)
                    e["source"] = str(f.parent)
                    episodes.append(e)
    return episodes


def taux(n, d):
    return f"{100 * n / d:.0f} %" if d else "–"


def resume(groupe):
    """Chiffres d'un groupe d'épisodes."""
    s = lambda cle: sum(e.get(cle, 0) for e in groupe)
    heures = s("duree_simulee_s") / 3600
    return {
        "épisodes": len(groupe),
        "heures simulées": f"{heures:.2f}",
        "navires détectés": taux(s("navires_detectes"), s("navires_vus")),
        "navires alertés": taux(s("navires_alertes"), s("navires_vus")),
        "plaques lues": taux(s("plaques_lues"), s("plaques_a_lire")),
        "lectures fausses": s("lectures_fausses"),
        "alertes sur hallucination / h": f"{s('alertes_sur_hallucination') / heures:.1f}" if heures else "–",
        "approches sur hallucination / h": f"{s('approches_sur_hallucination') / heures:.1f}" if heures else "–",
        "alertes en double": s("alertes_en_double"),
        "précision des boîtes": taux(s("boites_vraies"), s("boites_vraies") + s("boites_fausses")),
        "rappel des boîtes": taux(s("boites_vraies"), s("boites_vraies") + s("boites_manquees")),
    }


def tableau(lignes, titre_colonne):
    if not lignes:
        return ""
    cles = list(next(iter(lignes.values())).keys())
    out = [f"| {titre_colonne} | " + " | ".join(cles) + " |", "|" + "---|" * (len(cles) + 1)]
    for nom, r in lignes.items():
        out.append(f"| {nom} | " + " | ".join(str(r[c]) for c in cles) + " |")
    return "\n".join(out)


def graphes(episodes, sortie: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib absent : pas de graphes")
        return []
    fichiers = []
    par_meteo = defaultdict(list)
    for e in episodes:
        par_meteo[e["meteo"]].append(e)
    meteos = sorted(par_meteo)
    s = lambda g, cle: sum(e.get(cle, 0) for e in g)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    largeur = 0.27
    for k, (cle_n, cle_d, nom) in enumerate([("navires_detectes", "navires_vus", "navires détectés"),
                                              ("navires_alertes", "navires_vus", "navires alertés"),
                                              ("plaques_lues", "plaques_a_lire", "plaques lues")]):
        valeurs = [100 * s(par_meteo[m], cle_n) / max(s(par_meteo[m], cle_d), 1) for m in meteos]
        ax.bar([i + (k - 1) * largeur for i in range(len(meteos))], valeurs, largeur, label=nom)
    ax.set_xticks(range(len(meteos)), meteos, rotation=20)
    ax.set_ylabel("%")
    ax.set_ylim(0, 100)
    ax.set_title("Ce que la chaîne réussit, par météo")
    ax.legend(frameon=False)
    fig.tight_layout()
    fichiers.append(sortie / "taux_par_meteo.png")
    fig.savefig(fichiers[-1], dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    heures = [s(par_meteo[m], "duree_simulee_s") / 3600 for m in meteos]
    ax.bar(meteos, [s(par_meteo[m], "alertes_sur_hallucination") / max(h, 1e-9) for m, h in zip(meteos, heures)],
           label="alertes sur hallucination")
    ax.plot(meteos, [s(par_meteo[m], "hallucinations_confirmees") / max(h, 1e-9) for m, h in zip(meteos, heures)],
            "o-", color="black", label="hallucinations confirmées (experts lancés)")
    ax.set_ylabel("par heure de patrouille")
    ax.set_title("Hallucinations, par météo")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False)
    fig.tight_layout()
    fichiers.append(sortie / "hallucinations_par_meteo.png")
    fig.savefig(fichiers[-1], dpi=130)
    plt.close(fig)

    distances = [d for e in episodes for d in e.get("distances_detection_m", [])]
    delais = [d for e in episodes for d in e.get("delais_alerte_s", [])]
    for valeurs, nom, unite, fichier in ((distances, "Distance du navire à la confirmation", "m", "distance_detection.png"),
                                         (delais, "Délai entre le navire visible et l'alerte", "s", "delai_alerte.png")):
        if not valeurs:
            continue
        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.hist(valeurs, bins=20)
        ax.set_xlabel(unite)
        ax.set_ylabel("navires")
        ax.set_title(nom)
        fig.tight_layout()
        fichiers.append(sortie / fichier)
        fig.savefig(fichiers[-1], dpi=130)
        plt.close(fig)
    return fichiers


def main():
    ap = argparse.ArgumentParser(description="Bilan des campagnes du simulateur")
    ap.add_argument("dossiers", nargs="+", type=Path, help="dossiers de campagne (episodes.jsonl, cherché dedans)")
    ap.add_argument("--sortie", type=Path, default=Path("bilan"))
    args = ap.parse_args()
    episodes = lire(args.dossiers)
    if not episodes:
        raise SystemExit("aucun episodes.jsonl trouvé")
    args.sortie.mkdir(parents=True, exist_ok=True)
    with open(args.sortie / "episodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES + ["source"], extrasaction="ignore")
        w.writeheader()
        w.writerows(episodes)
    par_meteo, par_navires = defaultdict(list), defaultdict(list)
    for e in episodes:
        par_meteo[e["meteo"]].append(e)
        par_navires[e["navires_scenario"]].append(e)
    debits = [json.loads(p.read_text()) for d in args.dossiers for p in Path(d).rglob("bilan.json")]
    lignes = ["# Bilan des campagnes du simulateur", "",
              f"{len(episodes)} épisodes, {sum(e['duree_simulee_s'] for e in episodes) / 3600:.2f} h simulées.", ""]
    if debits:
        lignes += [f"Débit moyen : {sum(d['heures_simulees_par_heure'] for d in debits) / len(debits):.2f} h simulées "
                   f"par heure et par instance ({len(debits)} instance(s), détecteur {debits[0].get('detecteur')}).", ""]
    lignes += ["## Ensemble", "", tableau({"tout": resume(episodes)}, ""), "",
               "## Par météo", "", tableau({m: resume(g) for m, g in sorted(par_meteo.items())}, "météo"), "",
               "## Par nombre de navires", "",
               tableau({f"{n} navire(s)": resume(g) for n, g in sorted(par_navires.items())}, "scénario"), "",
               "Mer vide (0 navire) : toute alerte est une hallucination.", ""]
    for f in graphes(episodes, args.sortie):
        lignes += [f"![{f.stem}]({f.name})", ""]
    (args.sortie / "bilan.md").write_text("\n".join(lignes), encoding="utf-8")
    print(f"bilan écrit dans {args.sortie}/bilan.md")


if __name__ == "__main__":
    main()
