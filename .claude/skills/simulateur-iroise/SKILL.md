---
name: simulateur-iroise
description: Lancer, utiliser et modifier le simulateur 3D Iroise du projet USV-IA (ia/simulateur, Three.js, Goulet et rade de Brest vus depuis la caméra du drone). À utiliser quand on demande d'ouvrir ou lancer le simulateur, de tester la chaîne IA (détection, suivi, décision, alerte, approche) sur des images simulées, de monter un scénario de test (navires, météo, pluie, buée, brume, heure, position du drone), de brancher un pipeline sur le simulateur, ou de corriger ou améliorer le simulateur.
---

# Simulateur Iroise

Le simulateur est dans `ia/simulateur/`. Avant tout travail dessus, lire `ia/simulateur/AGENTS.md` : lancement, scénarios, branchement de la chaîne, plan du code, règles de modification. Le `README.md` du même dossier décrit le protocole et ce qui est simulé.

## Lancer

```bash
cd ia/simulateur && npm install && npm run dev
```

Puis ouvrir http://127.0.0.1:5173 (dans l'application Claude : aperçu `simulateur` de `.claude/launch.json`). Node.js 20.19 ou plus récent ; ne rien installer d'autre sans l'accord de la personne. Arrêter le serveur à la fin si elle n'en a plus besoin.

## Tester la chaîne IA

1. Station sol : `cd station_sol && python3 serveur.py` (page sur http://localhost:8000).
2. Chaîne, depuis la racine du dépôt : `.venv/bin/python ia/simulateur/bridge/chaine_cerema.py --station http://localhost:8000`. Après une modification de la chaîne, l'arrêter et la relancer : le simulateur se reconnecte seul. Pour tester une autre branche sans toucher à la copie de travail de la personne : un worktree, et `--depot` vers lui.
3. Ouvrir le simulateur avec `?bridge=1`, ou sur un scénario : `?scenario=demo-tuteur&bridge=1` (patrouille, approche d'un chalutier, plaque lue, alerte, reprise de la route). Les boîtes de la chaîne s'affichent en bleu, la vérité terrain en doré (`B`). Détecteur par défaut : `yolo11n`, comme sur l'IMX500.
4. Monter le scénario (URL pour qu'il soit reproductible, ou carte `C` pour poser des navires), changer une condition à la fois, et relever ce que la chaîne a vu dans `ia/simulateur/bridge/runs/`.

## Rendre compte

Dire ce qui a été vérifié dans le navigateur (capture, console sans erreur, `npm run build`) et ce qui ne l'a pas été. Pousser sur une branche `ia/…` et ouvrir une pull request vers `main` seulement si la personne le demande ; le client et le tuteur lisent le dépôt.
