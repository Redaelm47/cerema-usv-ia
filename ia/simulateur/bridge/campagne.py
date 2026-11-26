"""Mode campagne de la passerelle : un épisode après l'autre, et ce que la chaîne a bien ou mal fait dans chacun.

Le simulateur (?campagne=1, src/sim/Campagne.js) annonce chaque épisode, envoie ses images une à une et attend la
réponse de la chaîne. Ici, chaque image est comparée à la vérité terrain du simulateur :

- une boîte de la chaîne qui recouvre un navire réel (intersection sur union >= 0,3) est une vraie détection,
  une boîte qui ne recouvre rien est une fausse détection ;
- une piste dont la boîte tombe sur le même navire au moins une image sur deux est rattachée à ce navire,
  les autres sont des hallucinations (vagues, reflets, côte) ;
- une alerte est rattachée au navire de sa piste ; une plaque est juste si elle est égale au nom du navire
  (les chalutiers du simulateur portent leur immatriculation comme nom).

Résultats : une ligne par épisode dans <dossier>/episodes.jsonl, le débit dans <dossier>/bilan.json.
Graphes et tableaux de plusieurs campagnes : bridge/bilan.py.
"""
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

VISIBLE_PX = 20          # un navire de moins de 20 px de large n'est pas compté comme visible
RECOUVREMENT_MIN = 0.3   # boîte de la chaîne sur un navire réel
IMMAT = re.compile(r"^[A-Z]{2} ?\d{6}$")


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def normaliser(texte) -> str:
    return re.sub(r"[^A-Z0-9]", "", (texte or "").upper())


class Mesures:
    """Ce que fait la chaîne pendant un épisode, comparé à la vérité terrain."""

    def __init__(self, numero: int, graine: int, scenario: dict):
        self.numero, self.graine, self.scenario = numero, graine, scenario
        self.images = 0
        self.vraies = self.fausses = self.manquees = 0          # boîtes, image par image
        self.piste_images = Counter()                           # piste -> images où elle est vue
        self.piste_navire = defaultdict(Counter)                # piste -> navire réel -> images en commun
        self.confirmees = set()                                 # pistes passées au moins une fois en « confirmée »
        self.navires = {}                                       # navire réel -> ce qu'on sait de lui

    def observer(self, meta: dict, t: float, chaine) -> None:
        self.images += 1
        verites = meta.get("ground_truth", [])
        boites = []
        for f in chaine.fiches.values():
            if f.suivi.derniere_vue != t:
                continue
            x, y, w, h = f.suivi.boite
            confirmee = getattr(f.decision.etat, "value", f.decision.etat) != "nouvelle"
            boites.append((f.id_piste, (x, y, x + w, y + h), confirmee))
            if confirmee:
                self.confirmees.add(f.id_piste)
        for v in verites:
            largeur = v["bbox"][2] - v["bbox"][0]
            n = self.navires.setdefault(v["id"], {"nom": v.get("name"), "type": v.get("label"), "largeur_max": 0.0,
                                                  "distance_min": 1e9, "vu_t": None, "detecte_t": None,
                                                  "distance_detection": None})
            n["largeur_max"] = max(n["largeur_max"], largeur)
            n["distance_min"] = min(n["distance_min"], v.get("distance", 1e9))
            if largeur >= VISIBLE_PX and n["vu_t"] is None:
                n["vu_t"] = t
        paires = sorted(((iou(b, v["bbox"]), i, j) for i, (_, b, _) in enumerate(boites)
                         for j, v in enumerate(verites)), reverse=True)
        prises_b, prises_v = set(), set()
        for r, i, j in paires:
            if r < RECOUVREMENT_MIN:
                break
            if i in prises_b or j in prises_v:
                continue
            prises_b.add(i)
            prises_v.add(j)
            id_piste, _, confirmee = boites[i]
            v = verites[j]
            self.piste_navire[id_piste][v["id"]] += 1
            n = self.navires[v["id"]]
            if confirmee and n["detecte_t"] is None:
                n["detecte_t"], n["distance_detection"] = t, v.get("distance")
        for id_piste, _, _ in boites:
            self.piste_images[id_piste] += 1
        self.vraies += len(prises_b)
        self.fausses += len(boites) - len(prises_b)
        self.manquees += sum(1 for j, v in enumerate(verites)
                             if j not in prises_v and v["bbox"][2] - v["bbox"][0] >= VISIBLE_PX)

    def navire_de(self, id_piste):
        """Navire réel d'une piste, ou None si c'est une hallucination."""
        communs = self.piste_navire.get(id_piste)
        if not communs:
            return None
        navire, images = communs.most_common(1)[0]
        return navire if images >= 0.5 * self.piste_images[id_piste] else None

    def resumer(self, messages: list, journal: list, duree_simulee_s: float) -> dict:
        vus = {k: n for k, n in self.navires.items() if n["largeur_max"] >= VISIBLE_PX}
        hallucinees = [p for p in self.piste_images if self.navire_de(p) is None]
        alertes = [m for m in messages if m.get("genre") == "alerte"]
        par_navire, alerte_t = Counter(), {}
        sur_hallucination = justes = fausses = 0
        for a in alertes:
            navire = self.navire_de(a["id_piste"])
            if navire is None:
                sur_hallucination += 1
                continue
            par_navire[navire] += 1
            alerte_t.setdefault(navire, a.get("t"))
            if a.get("immatriculation"):
                if normaliser(a["immatriculation"]) == normaliser(self.navires[navire]["nom"]):
                    justes += 1
                else:
                    fausses += 1
        approches = [l for l in journal if l.get("action") == "approche"]
        a_lire = [k for k, n in vus.items() if IMMAT.match(n["nom"] or "")]
        lues = {k for k in a_lire if any(normaliser(a.get("immatriculation")) == normaliser(vus[k]["nom"])
                                         for a in alertes if self.navire_de(a["id_piste"]) == k)}
        sc = self.scenario
        return {
            "numero": self.numero, "graine": self.graine, "zone": sc.get("zone"), "meteo": sc.get("weather"),
            "heure": round(sc.get("hour", 0), 2), "mois": sc.get("month"), "vent_mps": round(sc.get("wind", 0), 1),
            "houle": round(sc.get("swell", 0), 2), "navires_scenario": len(sc.get("ships", [])),
            "types_scenario": [s["kind"] for s in sc.get("ships", [])],
            "duree_simulee_s": round(duree_simulee_s, 1), "images": self.images,
            "navires_vus": len(vus),
            "navires_detectes": sum(1 for n in vus.values() if n["detecte_t"] is not None),
            "navires_alertes": sum(1 for k in vus if par_navire[k] > 0),
            "plaques_a_lire": len(a_lire), "plaques_lues": len(lues),
            "lectures_justes": justes, "lectures_fausses": fausses,
            "alertes": len(alertes), "alertes_completes": sum(1 for a in alertes if a.get("complete")),
            "alertes_sur_hallucination": sur_hallucination,
            "alertes_en_double": sum(max(0, c - 1) for c in par_navire.values()),
            "pistes": len(self.piste_images), "pistes_hallucinees": len(hallucinees),
            "hallucinations_confirmees": sum(1 for p in hallucinees if p in self.confirmees),
            "approches": len(approches),
            "approches_sur_hallucination": sum(1 for l in approches if self.navire_de(l.get("piste")) is None),
            "boites_vraies": self.vraies, "boites_fausses": self.fausses, "boites_manquees": self.manquees,
            "delais_detection_s": [round(n["detecte_t"] - n["vu_t"], 1) for n in vus.values()
                                   if n["detecte_t"] is not None and n["vu_t"] is not None],
            "distances_detection_m": [round(n["distance_detection"]) for n in vus.values()
                                      if n["distance_detection"] is not None],
            "delais_alerte_s": [round(alerte_t[k] - vus[k]["vu_t"], 1) for k in vus
                                if k in alerte_t and alerte_t[k] is not None and vus[k]["vu_t"] is not None],
            "navires": [{"nom": n["nom"], "type": n["type"], "largeur_max_px": round(n["largeur_max"]),
                         "distance_min_m": round(n["distance_min"]), "detecte": n["detecte_t"] is not None,
                         "alerte": par_navire[k] > 0} for k, n in vus.items()],
        }


class Campagne:
    """Reçoit les messages texte du simulateur (épisodes) et écrit les résultats."""

    def __init__(self, pont, dossier: Path):
        self.pont = pont
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = open(self.dossier / "episodes.jsonl", "a", encoding="utf-8")
        self.debut = time.perf_counter()
        self.episodes = 0
        self.secondes = 0.0
        self.images = 0
        self._t0 = None

    def message(self, m: dict) -> bool:
        """Traite un message du simulateur ; True quand la campagne est finie."""
        genre = m.get("type")
        if genre == "episode_debut":
            self.pont.nouvel_episode(m["numero"])
            self.pont.mesures = Mesures(m["numero"], m["graine"], m.get("scenario", {}))
            self._t0 = time.perf_counter()
        elif genre == "episode_fin" and self.pont.mesures is not None:
            resultat = self.pont.fin_episode()
            resultat["duree_reelle_s"] = round(time.perf_counter() - (self._t0 or self.debut), 1)
            self.fichier.write(json.dumps(resultat, ensure_ascii=False) + "\n")
            self.fichier.flush()
            self.episodes += 1
            self.secondes += resultat["duree_simulee_s"]
            self.images += resultat["images"]
            print(f"épisode {resultat['numero']} ({resultat['meteo']}, {resultat['zone']}) : "
                  f"{resultat['navires_detectes']}/{resultat['navires_vus']} navires détectés, "
                  f"{resultat['plaques_lues']}/{resultat['plaques_a_lire']} plaques lues, "
                  f"{resultat['alertes_sur_hallucination']} alerte(s) sur hallucination, "
                  f"{resultat['duree_simulee_s']:.0f} s simulées en {resultat['duree_reelle_s']:.0f} s", flush=True)
        elif genre == "campagne_fin":
            duree = time.perf_counter() - self.debut
            bilan = {"episodes": self.episodes, "heures_simulees": round(self.secondes / 3600, 3),
                     "images": self.images, "duree_reelle_s": round(duree, 1),
                     "heures_simulees_par_heure": round(self.secondes / max(duree, 1e-9), 2),
                     "detecteur": self.pont.nom_detecteur, "appareil": getattr(self.pont, "appareil", None)}
            (self.dossier / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=1))
            self.fichier.close()
            print(f"{self.episodes} épisodes, {bilan['heures_simulees']} h simulées en {duree / 60:.1f} min "
                  f"({bilan['heures_simulees_par_heure']} h simulées par heure)", flush=True)
            print("CAMPAGNE FINIE", flush=True)
            return True
        return False
