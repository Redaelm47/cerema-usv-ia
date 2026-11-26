# Campagnes sans écran sur le cluster

Le mode campagne du simulateur (`?campagne=1`, voir le README du simulateur) tourne ici sans écran, sur les GPU du cluster Slurm : Chromium sans écran rend la scène sur le GPU NVIDIA (WebGL 2), la passerelle `bridge/chaine_cerema.py --campagne` fait tourner la chaîne IA, et les résultats partent sur le Drive.

| Fichier | Rôle |
|---|---|
| `lancer.py` | une instance : site statique (`dist/`), passerelle, Chromium 2028 x 1520, suivi de `window.campagne`, arrêt propre, copie sur le Drive |
| `campagne.sbatch` | tableau de tâches Slurm, 1 RTX 3080 par tâche, graine = 1000 x numéro de tâche |

## Préparer (une fois, sur le nœud de connexion)

```bash
cd ia/simulateur && npm ci && npm run build      # Node 22
```

Il faut aussi un Python avec Playwright et Chromium (`lancer.py`), un Python pour la chaîne (`ia/chaine/requirements.txt`, `ultralytics`, `websockets`), les modèles de `ia/chaine/modeles/` et rclone configuré avec le Drive. Les chemins sont en tête de `campagne.sbatch`.

## Lancer

```bash
# essai court : 1 tâche, 2 épisodes de 60 s
EPISODES=2 DUREE=60 sbatch --array=1 --time=00:30:00 ia/simulateur/campagne/campagne.sbatch

# 4 tâches de 20 épisodes de 180 s, deux instances par GPU
EPISODES=20 DUREE=180 PAR_GPU=2 sbatch --array=1-4 --time=04:00:00 ia/simulateur/campagne/campagne.sbatch
```

- Variables : `EPISODES` (10), `DUREE` (180 s simulées par épisode), `IMG_S` (5), `DETECTEUR` (`best4_2`), `PAR_GPU` (1 ou 2), `CAMPAGNE` (nom du dossier, par défaut l'heure de soumission), `DELAI` (s).
- La tâche k part de la graine 1000 k ; avec `PAR_GPU=2`, la deuxième instance (`tache_<k>b`) part de 1000 k + 500.
- Ports choisis libres à chaque lancement : plusieurs instances partagent un GPU sans se gêner.
- Points de sauvegarde : le dossier de la tâche est copié sur le Drive toutes les 10 min (`--copie-min`) ; `ARRET_A=06:35` (ou `--arret-a`) arrête proprement à cette heure, et un SIGTERM de Slurm aussi, avec une dernière copie.
- Arrêt : fin de campagne (`CAMPAGNE FINIE`), erreur dans la page, passerelle arrêtée, rien qui avance pendant 10 min, ou délai dépassé (par défaut 10 s réelles par seconde simulée + 10 min). Code de sortie 0, 1 (erreur) ou 2 (délai).
- Si le rendu WebGL est SwiftShader (pas de GPU dans le navigateur), la tâche s'arrête tout de suite.

Une seule instance, à la main sur un nœud GPU :

```bash
python ia/simulateur/campagne/lancer.py --graine 1000 --episodes 2 --duree 60 --tache essai \
    --python-chaine <python de la chaîne> --drive non --travail resultats/
```

`--mode-normal 120` ouvre à la place le simulateur en temps réel (`?scenario=demo-tuteur&bridge=1`) pendant 120 s et relève les images par seconde reçues par la passerelle.

## Résultats

Sur le Drive, `gdrive:Minos/cerema-usv-ia/campagnes/<AAAA-MM-JJ_HHMM>/tache_<k>/` :

- `episodes.jsonl` (une ligne par épisode), `bilan.json` (débit), `journaux/` : écrits par la passerelle ;
- `lancement.json` : paramètres, URL, commit, nœud, carte qui fait le rendu WebGL, raison de l'arrêt ;
- `passerelle.log`, `navigateur.log` (console de la page), `derniere_image.jpg`.

La copie locale est effacée une fois sur le Drive ; si rclone échoue, elle reste dans le dossier `--travail`.

## Bilan

```bash
rclone copy gdrive:Minos/cerema-usv-ia/campagnes/<AAAA-MM-JJ_HHMM> resultats/ --include "*.jsonl" --include "*.json"
python ia/simulateur/bridge/bilan.py resultats/tache_* --sortie resultats/bilan
```

`bilan.md`, `episodes.csv` et les graphes arrivent dans `resultats/bilan/`. Le débit de chaque tâche (heures simulées par heure réelle) est dans son `bilan.json`.
