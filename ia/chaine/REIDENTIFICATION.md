# Ré-identification des navires

Rédigé par Adam-Sabri, le 09/11/2026. Tâche confiée à la répartition IA du 05/11/2026 : savoir si un navire a déjà été vu.

## Le besoin

D'après le cadrage du 05/11, le client veut :

- reconnaître un navire dont l'immatriculation n'est pas lisible, ou vérifier l'immatriculation lue ;
- ne pas refaire tout le travail (OCR, approche) pour un navire déjà connu.

Le numéro de piste ne suffit pas. Il vient du suivi et ne dure que tant que le navire reste en vue. Si le navire est masqué, sort du champ ou revient plus tard, il reçoit un nouveau numéro et la chaîne le traite comme un navire inconnu : nouveau type, nouvelle lecture, nouvelle approche, nouvelle alerte.

## Le principe : informer, ne jamais fusionner

La mesure de `ARCHITECTURE.md` fixe la règle. Sur 25 photos de navires de pêche, comparées une vue contre une vue :

- au seuil 0,85, la signature DINOv2 reconnaît 82 % des paires du même navire et confond 1 % des paires de navires différents ;
- au seuil 0,9, aucune confusion, mais seulement 55 % des paires reconnues.

Deux fileyeurs bleus se ressemblent trop. Si l'on fusionnait les fiches de deux navires différents, l'un des deux disparaîtrait. **La ré-identification ne fusionne donc jamais de fiches et ne remplace jamais l'OCR.** Seule une immatriculation lue et validée prouve l'identité d'un navire.

## Ce qu'elle fait

La mémoire des navires (`reidentification.py`, `MemoireNavires`) garde chaque navire déjà alerté avec :

- son immatriculation, si elle a été lue ;
- ses types ;
- jusqu'à 12 signatures, choisies pour couvrir des points de vue variés.

Une signature est le vecteur de 768 nombres que l'expert type calcule déjà avec DINOv2. **Elle ne coûte aucun calcul en plus.**

| Situation | Effet | Où |
|---|---|---|
| Un nouveau navire ressemble à un navire déjà signalé | L'alerte porte `deja_vu` (immatriculation probable, niveau, ressemblance). L'opérateur lit « Très probablement GV 642410 ». | `Chaine._memoriser` |
| L'OCR lit **une** fois exactement l'immatriculation que la ressemblance propose | La lecture est validée tout de suite, au lieu d'attendre une deuxième lecture identique. Deux indices indépendants concordent. | `Chaine._lecture_confirmee_par_reid` |
| Navire trop petit pour être lu, reconnu avec certitude comme un navire déjà identifié | Alerte partielle avec `deja_vu`, **sans nouvelle approche** (économie de batterie et de temps). Option `--reid-reapprocher` pour approcher quand même. | `decideur.py`, question 4 |
| Immatriculation lue, déjà portée par un navire d'apparence très différente | L'alerte porte `deja_vu.apparence_coherente: false`, la page l'affiche en orange, et le journal le note. Cela peut être une erreur d'OCR, ou deux navires qui portent le même numéro. | `MemoireNavires.verifier` |

Dans tous les cas, l'immatriculation de l'alerte reste celle que l'OCR a lue (ou `null`). Une ressemblance ne la remplit jamais.

## Indices complémentaires (`indices.py`)

La signature DINOv2 ne suffit pas à séparer deux navires de même modèle. La mémoire garde aussi, pour chaque navire :

| Indice | Rôle | Source |
|---|---|---|
| **Nom** lu sur la coque (« KOFRIGAN ») | score : +0,06 si le même nom est retrouvé (moitié si lu une fois), −0,03 si deux noms bien lus diffèrent | textes hors format de l'OCR |
| **Fragment d'immatriculation** (« BR5387 ») | score : +0,04 s'il est compatible avec l'immatriculation du navire en mémoire (même quartier, au moins 4 chiffres, une faute tolérée). Jamais de malus : un fragment mal lu ne doit pas écarter le bon navire | textes hors format de l'OCR |
| **Couleur par bandes** (superstructure, flanc, coque) | score : de −0,04 à +0,02 autour d'une similarité de 0,85 | `couleur.signature_couleur_bandes`, calculée avec la signature |
| **Longueur réelle** | veto si les longueurs minimales diffèrent de plus de 1,8 fois | distance mesurée par le drone |
| **Trajet** | veto si le navire aurait dû dépasser 20 m/s pour passer de sa dernière position à la nouvelle | position, cap et distance mesurée du drone |

Règles : la somme des bonus est plafonnée à 0,08 ; sous 0,75 de ressemblance visuelle rien ne rattrape un candidat ; les indices corrigent la ressemblance (qui sert aux seuils `probable` et `sur`) et ne la remplacent pas. Le détail de chaque indice est dans le champ `indices` du journal.

**Taille et trajet demandent des mesures que le drone doit fournir** : `Contexte.distance_navire_m` (distance mesurée à la cible), `position_m` et `cap_deg`. La distance de l'approche simulée est déduite d'une longueur supposée par type : s'en servir pour mesurer le navire serait circulaire. Sans ces mesures, ces deux indices sont inactifs.

Tous les poids sont des valeurs de départ **non recalées** (`ReglagesReid`). Les recaler demande des images de plusieurs navires : `outils/mesurer_reid.py`. La mémoire sauvée passe en version 2 ; la version 1 se relit.

Quand l'OCR lit un navire assez gros, la chaîne prend aussi sa signature et sa couleur de près si la mémoire n'en a aucune (le type est souvent passé quand le navire est trop petit pour une signature).

## Les garde-fous

1. **Deux seuils.** Le niveau `probable` s'applique à partir d'une ressemblance de 0,85, le niveau `sur` à partir de 0,90. Seul `sur` peut éviter une approche.
2. **Une marge.** Si deux navires d'identités différentes ressemblent presque autant (écart inférieur à 0,03), la mémoire ne choisit pas. Les entrées d'un même navire (même immatriculation, ou reliées par la ressemblance) ne comptent pas dans ce calcul.
3. **Navires vus en même temps.** Deux pistes dont les périodes de visibilité se chevauchent sont deux navires différents, quelle que soit leur ressemblance.
4. **Types incompatibles.** Si l'expert type est sûr des deux côtés (`peche` contre `voilier`), le navire est écarté. Un type hésitant n'écarte rien.
5. **Signatures trop pauvres.** Un recadrage de moins de 80 px n'est pas gardé.
6. **Ressemblance d'un ensemble de vues à un autre.** Pour chaque vue de la piste, on prend la vue la plus proche du navire en mémoire, puis on fait la moyenne. Prendre le maximum sur toutes les paires gonflerait les fausses ressemblances.
7. **Pas de fusion.** Un navire sans immatriculation reconnu avec certitude reçoit sa propre entrée, reliée au premier navire (`ressemble_a`) mais distincte.
8. **Mémoire bornée.** Elle garde 500 navires au plus ; au-delà, le navire vu le moins récemment est oublié.

Sans `--reid`, la chaîne se comporte exactement comme avant. Un test le vérifie.

## Contrat 3 : le champ `deja_vu`

C'est un ajout facultatif à l'alerte, présent seulement quand il y a quelque chose à dire. La station sol accepte déjà les champs en plus, et un test le vérifie avec `station_sol/contrat.py`.

```json
{"genre": "alerte", "t": 105.2, "id_piste": 12, "complete": false, "types": ["peche"],
 "immatriculation": null, "confiance_immatriculation": 0.0,
 "raison": "navire reconnu (GV 642410), pas de nouvelle approche",
 "deja_vu": {"immatriculation": "GV 642410", "niveau": "sur", "similarite": 0.934, "premiere_alerte_t": 20.6}}
```

| Champ | Sens |
|---|---|
| `immatriculation` | celle du navire reconnu (`null` s'il n'avait pas été lu) |
| `niveau` | `probable`, `sur` (ressemblance seule) ou `immatriculation` (même immatriculation lue) |
| `similarite` | entre 0 et 1, `null` si le navire n'a aucune signature |
| `premiere_alerte_t` | date de la première alerte du navire reconnu |
| `apparence_coherente` | seulement au niveau `immatriculation` : `false` si les deux apparences ne vont pas ensemble |

## Lancer

Depuis `ia/` :

```
python -m chaine --video V --reid                                   # mémoire le temps de la mission
python -m chaine --video V --memoire-navires runs/memoire/navires   # mémoire relue et sauvée d'une mission à l'autre
python -m embarque --pi --station http://<mac>:8000 --reid
```

La mémoire sauvée tient en deux fichiers : `navires.json` (lisible) et `navires.npz` (signatures). Les dates qu'elle contient sont relatives à la mission où le navire a été vu.

Avec les experts factices (scénario simulé), aucune signature n'est calculée : seule la vérification par l'immatriculation agit.

## Recaler les seuils : `outils/mesurer_reid.py`

Les seuils actuels viennent de 25 photos seulement. Pour les recaler :

1. Préparer un dossier avec **un sous-dossier par navire** et plusieurs images recadrées sur le navire dans chacun. Les sources possibles sont dans `ia/JEUX_DE_DONNEES.md` (Warships-ReID, VesselReID), ou nos propres images de la caméra.
2. Lancer : `python -m chaine.outils.mesurer_reid ../data/reid --signatures runs/signatures_reid.npz --rapport runs/mesure_reid.json`

L'outil rend deux mesures :

- **Paires** : la mesure de `ARCHITECTURE.md`, refaite, pour chaque seuil.
- **Mémoire** : la vraie procédure de la chaîne. La moitié des navires est mise en mémoire ; l'autre moitié sert d'intrus. On compte les navires reconnus, ceux pris pour un autre et les intrus reconnus à tort.

Il propose ensuite les seuils `sur` (aucune fausse reconnaissance), `probable` (2 % au plus) et le seuil d'incohérence. Il suffit de les reporter dans `ReglagesReid`.

## Tests

`python -m unittest chaine.tests.test_reidentification` : 33 tests sur des signatures synthétiques, sans modèle. Ils couvrent :

- la mémoire : seuils, marge, jumeaux, types, navires vus en même temps, sauvegarde ;
- la chaîne : pas de nouvelle approche, lecture unique confirmée, incohérence, comportement inchangé sans `--reid`, reprise de piste ;
- le contrat de la station sol ;
- l'outil de mesure.

## Limites et suite

- **Pas encore mesuré sur de vraies images.** C'est la prochaine étape, avec `mesurer_reid.py`.
- Les signatures viennent de l'expert type, qui tourne 2 à 3 fois par navire, souvent quand le navire est encore petit. Une signature prise plus près serait meilleure, mais coûterait un passage du réseau (0,3 à 0,6 s estimées sur le Pi).
- DINOv2 n'a pas été entraîné à distinguer deux navires de même modèle. Une tête apprise pour la ré-identification (perte triplet sur VesselReID) améliorerait les choses, mais il faudrait des données et un accord d'accès.
- La règle « vus en même temps » ne connaît que les fiches encore en mémoire de la chaîne : 60 s après la dernière vue, une fiche alertée est oubliée.
- La signature dépend de l'angle de vue : un navire vu de face puis de côté peut ne pas être reconnu. Cette erreur est sans danger : il est alors traité comme un nouveau navire, comme avant.
