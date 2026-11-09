# Changements

Ce fichier répertorie les principales évolutions du projet.

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
