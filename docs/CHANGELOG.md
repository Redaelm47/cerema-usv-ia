# Changements

Ce fichier répertorie les principales évolutions du projet.

## 2026-11-26

- Réglages de Guillaume dans la chaîne : `best4_2` détecteur par défaut sur ordinateur, vidéo et simulateur (`--detecteur`), détection sûre à 55 % (son seuil optimal), experts lancés après 5 détections sûres d'affilée (`images_confirmation`, au lieu de 3 images à 30 %). Sur le Pi, le modèle COCO de l'IMX500 garde 30 %. BoT-SORT n'est pas repris : le suivi de `ia/suivi` fait déjà mieux sur la scène Blender. Le simulateur passe par `Suivi.pas`, le même suivi que le Pi.
- Simulateur, mode mission : route du drone tracée sur la carte et suivie en boucle à 3 nœuds, prise en main par la chaîne IA pendant l'approche puis reprise de la route ; scénarios rejouables (`?scenario=`, `ia/simulateur/public/scenarios/`) dont la démo pour le tuteur (`demo-tuteur`) ; distance réelle au navire transmise à la chaîne pendant l'approche ; détecteur par défaut de la passerelle : `yolo11n`, comme sur l'IMX500 (`best4_2` voit des navires dans les nuages et sur la mer vide du simulateur).
- Boîte d'envoi SQLite (`ia/chaine/boite.py`, option `--boite`) : les messages vers la station sont gardés dans un fichier jusqu'à l'accusé de réception, même si la liaison coupe ou si le programme est relancé ; alertes d'abord, seul le dernier état compte pendant une coupure. Sans `--boite`, rien ne change.
- Rangement des branches : la chaîne de vision embarquée (`ia/suivi`, `ia/chaine`, `ia/embarque`, scène Blender, contrats), la ré-identification et la boîte d'envoi sont dans `main` (pull request #2). Branches `ia/chaine-squelette`, `ia/reidentification` et `claude/loving-edison-apkb5o` supprimées, leur contenu étant entièrement dans `main`.
- Ajout du simulateur 3D Iroise (`ia/simulateur/`) : Goulet et rade de Brest réels (relief LiDAR et orthophotos IGN, bathymétrie EMODnet), mer, ciel, trafic et modèles 3D de navires, caméra du drone à 45 cm de l'eau avec pluie, gouttes et buée sur l'objectif, carte pour téléporter le drone et poser des navires, passerelle vers la chaîne IA (`bridge/chaine_cerema.py`). Relief, images et modèles 3D (83 Mo) versionnés en exception à la règle des fichiers lourds, pour lancer le simulateur sans téléchargement.
- Consignes pour les agents de code : `ia/simulateur/AGENTS.md`, skill Claude Code `simulateur-iroise` et aperçu `simulateur` dans `.claude/launch.json`.

## 2026-11-23

- Ré-identification (`ia/chaine`) : indices complémentaires (nom, fragment d'immatriculation, couleur par bandes, taille, trajet) en plus de la signature DINOv2, mémoire des navires en version 2, détail dans `ia/chaine/REIDENTIFICATION.md`.
- Compte rendu du point de séance du 23/11 (`docs/comptes_rendus/2026-11-23_point-de-seance.pdf`) : GPS à une dizaine de mètres près, gouverne pas à pas et propulsion fonctionnelles, missions limitées à une zone, test de suivi de zone le 26/11, réunion du 26/11 avec le Cerema reportée. Sommaire des comptes rendus mis à jour.

## 2026-11-20

- Compte rendu du point de fin de séance du 20/11 (`docs/comptes_rendus/2026-11-20_point-de-seance.pdf`) : nouveau GPS fonctionnel, tests de missions par manettes virtuelles, recherche d'immatriculation de 50 à 10 s en simulation, caméra nocturne seule retenue, simulation 3D, réunion du 26/11 avec le Cerema. Sommaire des comptes rendus mis à jour.

## 2026-11-09

- Compte rendu du point de fin de séance du 09/11 (`docs/comptes_rendus/2026-11-09_point-de-seance.pdf`) : premier moteur testé, GPS bloqué faute d'adaptateur 10 broches, nouveau modèle de détection sur images dégradées, mémoire des bateaux déjà vus pour la ré-identification. Sommaire des comptes rendus mis à jour.

## 2026-11-05

- Rangement du dépôt : page d'accueil d'une page ; comptes rendus, guides (Raspberry Pi, ex-`sandbox/`, et Git, ex-README) et historique regroupés dans `docs/` ; `detections.json` déplacé en exemple dans `ia/raspberry_pi/` et ignoré à la racine ; branches déjà fusionnées supprimées.
- Ajout du plan d'actions de l'atelier 6 de co-développement (`docs/plan_actions_USV-IA.pdf`) : tableau des tâches sur GitHub, un responsable du suivi par sous-groupe, points de début et de fin de séance, horaires fixes.
- Comptes rendus en PDF : point de fin de séance, répartition des tâches IA et plateforme, et point d'étape du 21/10 (jusque-là en Markdown seulement).
- Rangement de `comptes_rendus/` : seuls les PDF et le sommaire restent à la racine du dossier ; textes, sources LaTeX, style commun et modèles sont dans `comptes_rendus/sources/`.
- Ajout de deux skills Claude Code dans `.claude/skills/` : `compte-rendu-reunion` (d'une transcription de réunion au compte rendu PDF rangé et poussé) et `projet-cerema` (conventions du projet).

## 2026-10-19

- Ajout de la revue de projet (`docs/revue_de_projet/`) : présentation (PPTX et PDF) et tableau de suivi (planning v1/v2, risques, actions, données client, responsabilités, réunions).

## 2026-10-12

- Ajout de la station sol (`station_sol/`) : serveur, page opérateur en direct, vérification du contrat n°3 et rejeu de faux messages.
- Réorganisation des README : tableau « Par où commencer », lots et répartition du lot L2, arborescence, méthode Git pas à pas ; README pour `sandbox/` ; liens entre `ia/`, `sandbox/` et `docs/`.
- Document de synthèse version 1 déplacé de la racine vers `docs/`.

## 2026-10-08

- Ajout du document de synthèse version 2 (PDF et sources LaTeX) dans `docs/`.
- Ajout de la proposition d'architecture de la vision embarquée et de la répartition du travail (PDF) dans `docs/`.

## 2026-10-01

- Ajout des documents du projet 2025 (comptes rendus, définition, livrables, poster).
- Ajout des scripts YOLO 2025 (PC et Raspberry Pi).
- Ajout du sujet et de la présentation du projet 20.

## 2026-09-28

- Création du dépôt et de son organisation.
- Récupération du travail du projet 2025 (clé USB fournie par le Cerema).
