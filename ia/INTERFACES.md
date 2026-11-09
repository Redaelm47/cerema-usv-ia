# Les trois parties et ce qui passe de l'une à l'autre

Trois programmes, trois personnes, deux échanges. Tant que les échanges ne changent pas, chaque partie peut être modifiée ou remplacée sans toucher aux autres.

```
  SUR LE RASPBERRY PI                                                       SUR LE MAC
┌────────────────────┐  contrat 1   ┌──────────────────────┐  contrat 3   ┌──────────────────────┐
│ 1. Caméra et suivi │ ───────────▶ │ 2. Décision, experts │ ───────────▶ │ 3. Station sol       │
│    ia/suivi        │ observations │    ia/chaine         │   messages   │    station_sol       │
│    Guillaume       │  + image     │    Reda              │  (réseau)    │    Adam-Sabri        │
└────────────────────┘ (en mémoire) └──────────────────────┘              └──────────────────────┘
```

Le contrat 2 (la fiche navire) n'est pas un échange : c'est la mémoire interne de la partie 2.

| | 1. Caméra et suivi | 2. Décision et experts | 3. Station sol |
|---|---|---|---|
| Responsable | Guillaume | Reda | Adam-Sabri |
| Dossier | `ia/suivi/` | `ia/chaine/` | `station_sol/` |
| Tourne sur | le Pi | le Pi | le Mac |
| Reçoit | les images de la caméra | les observations et l'image (contrat 1) | les messages (contrat 3) |
| Rend | les observations et l'image (contrat 1) | les messages (contrat 3) | la page de l'opérateur |
| Sa sortie, dans un fichier | `runs/observations.jsonl` | `runs/messages.jsonl` (et `runs/journal.jsonl`, qui reste à bord) | `station_sol/journaux/messages_<date>.jsonl` |
| Lancer seule | `python3 -m suivi --video V` | `python3 -m chaine --video V --observations runs/observations.jsonl` | `python3 serveur.py` puis `python3 rejouer.py F` |
| Tests | `python3 -m unittest discover -s suivi/tests -t .` (16) | `python3 -m unittest discover -s chaine/tests -t .` (127) | aucun |

Le code de `ia/suivi/` a été écrit par Reda le 12/10/2026 pour pouvoir tester l'ensemble : c'est la place de la partie de Guillaume, qui peut le reprendre ou le remplacer.

## Sortie de la partie 1 : les observations (contrat 1)

Une fois par image, **même quand il n'y a aucun navire** (liste vide). Deux choses ensemble :

1. un message JSON ;
2. l'image en pleine résolution, en mémoire (tableau NumPy, couleurs dans l'ordre bleu, vert, rouge).

```json
{"t": 20.0, "pistes": [
  {"id_piste": 2, "boite": [562.6, 583.5, 299.9, 233.5], "confiance": 0.745},
  {"id_piste": 1, "boite": [1432.4, 771.5, 58.7, 32.2], "confiance": 0.405}]}
```

| Champ | Sens |
|---|---|
| `t` | secondes depuis le démarrage |
| `id_piste` | numéro du navire. Il ne change pas tant que c'est le même navire, et il n'est jamais donné à un autre |
| `boite` | x, y du coin haut gauche, largeur, hauteur, en pixels **de l'image fournie avec le message** |
| `confiance` | confiance du détecteur, entre 0 et 1 |

Ce que la partie 1 ne fait pas : elle ne dit ni le type ni l'immatriculation, elle ne filtre pas les petits navires, elle ne décide rien.

Dans le programme embarqué, l'échange est un appel de fonction : `Chaine.pas(observations, image)`.

## Sortie de la partie 2 : les messages (contrat 3)

Un objet JSON par message, envoyé par `POST http://<mac>:8000/message`. Aucune image. Trois genres :

```json
{"genre": "etat", "t": 20.0, "mode": "approche", "batterie": 0.99, "navires_suivis": 2, "temperature_pi": 61.5}
{"genre": "decision", "t": 20.07, "id_piste": 2, "action": "expert_ocr", "raison": "navire assez gros pour lire"}
{"genre": "alerte", "t": 20.6, "id_piste": 2, "complete": true, "types": ["peche"],
 "immatriculation": "GV 642410", "confiance_immatriculation": 0.97, "raison": "immatriculation lue"}
```

| Genre | Quand | Champs |
|---|---|---|
| `etat` | une fois par seconde | `mode` (`patrouille` ou `approche`), `batterie` (0 à 1, simulée), `navires_suivis`, `temperature_pi` (`null` ailleurs que sur le Pi) |
| `decision` | à chaque décision | `id_piste`, `action` (`expert_type`, `expert_ocr`, `approche`, `alerte_complete`, `alerte_partielle`), `raison` |
| `alerte` | quand un navire est traité | `id_piste`, `complete`, `types` (liste, vide si inconnu), `immatriculation` (ou `null`), `confiance_immatriculation`, `raison`, et `textes_lus` quand du texte a été lu sur la coque sans être une immatriculation française, et `deja_vu` quand la ré-identification (option `--reid`) reconnaît un navire déjà signalé |

Une alerte donne deux messages : la décision (`alerte_complete` ou `alerte_partielle`), puis l'alerte.

La partie 2 écrit aussi un journal (`runs/journal.jsonl`) : chaque décision avec la fiche complète du navire à ce moment. Il reste à bord.

## Sortie de la partie 3 : la page de l'opérateur

La station sol vérifie chaque message (`station_sol/contrat.py`), refuse ceux qui sont hors contrat (réponse 400), garde les autres dans un fichier et les pousse en direct vers la page : état du drone, alertes, tableau des navires, journal. Elle n'envoie rien au drone.

## Tout ensemble

Le programme embarqué (`ia/embarque/`) enchaîne les parties 1 et 2 dans un seul processus.

Sur le Mac, pour répéter :

```
cd station_sol && python3 serveur.py                    # terminal 1 ; ouvrir http://localhost:8000
cd ia && python3 -m embarque --video ../data/scene-blender-01.mp4 --temps-reel --seuil-ocr 300 \
                             --station http://localhost:8000          # terminal 2
```

Sur le Pi, pour la démonstration (la station sol tourne sur le Mac, tout le calcul sur le Pi) :

```
sh ia/raspberry_pi/deployer.sh                          # depuis le Mac, une fois : copie et installe
ssh pi@cerema-pi.local
cd cerema/ia && ../env/bin/python -m embarque --pi --station http://<adresse-du-mac>:8000
```

## Vérifier une partie sans les autres

- **Partie 1 seule** : `python3 -m suivi --video V --sortie runs/suivi.mp4` écrit les observations et une vidéo avec les boîtes et les numéros. Un navire doit garder le même numéro du début à la fin.
- **Partie 2 seule** : `python3 -m chaine --video V --observations F` rejoue des observations enregistrées. Le résultat ne dépend plus du suivi.
- **Partie 3 seule** : `python3 rejouer.py F` rejoue n'importe quel fichier de messages, par exemple `ia/runs/messages.jsonl`.

## État au 12/10/2026

Essayé sur le Mac, de bout en bout, sur la scène Blender : 2 navires, 2 numéros de piste, 2 alertes (une complète « GV 642410 », une partielle), 40 messages reçus et affichés par la station sol, aucun refusé.

Pas essayé : la caméra IMX500 (`suivi/camera_pi.py`) et le script de déploiement, le Pi n'étant pas joignable.
