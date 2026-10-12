# Changements

Ce fichier répertorie les principales évolutions du projet.

## 2026-10-12

- Suivi (`ia/suivi`) : caméra, détection et numéros de piste, sans PyTorch sur le Pi ; 2 numéros au lieu de 16 pour les 2 navires de la scène Blender.
- Programme embarqué (`ia/embarque`) : suivi, décision et experts en une commande, messages vers la station sol ; script de déploiement sur le Pi (`ia/raspberry_pi/deployer.sh`, non essayé).
- `ia/INTERFACES.md` : les trois parties, leurs entrées et leurs sorties, avec des exemples réels.
- Station sol : `temperature_pi` peut valoir `null` hors du Pi, textes lus sur la coque affichés dans l'alerte, page adaptée au téléphone, adresse du Mac sur le réseau affichée au démarrage.
- Ajout de la station sol (`station_sol/`) : serveur, page opérateur en direct, vérification du contrat n°3 et rejeu de faux messages.
- Réorganisation des README : tableau « Par où commencer », lots et répartition du lot L2, arborescence, méthode Git pas à pas ; README pour `sandbox/` ; liens entre `ia/`, `sandbox/` et `docs/`.
- Document de synthèse version 1 déplacé de la racine vers `docs/`.

## 2026-10-08

- Chaîne de vision embarquée (`ia/chaine`) : fiche navire en trois blocs, décideur et garde-fous, vrais experts sur ONNX Runtime (filtre qualité, type, OCR avec vote, approche simulée), messages vers la station sol, suivi de remplacement sur vidéo, tests et mesures.
- Ajout du document de synthèse version 2 (PDF et sources LaTeX) dans `docs/`.
- Ajout de la proposition d'architecture de la vision embarquée et de la répartition du travail (PDF) dans `docs/`.

## 2026-10-01

- Ajout des documents du projet 2025 (comptes rendus, définition, livrables, poster).
- Ajout des scripts YOLO 2025 (PC et Raspberry Pi).
- Ajout du sujet et de la présentation du projet 20.

## 2026-09-28

- Création du dépôt et de son organisation.
- Récupération du travail du projet 2025 (clé USB fournie par le Cerema).
