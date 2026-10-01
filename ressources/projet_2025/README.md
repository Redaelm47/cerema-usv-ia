# Projet 2025 : Micro drone de surface (groupe 11)

Travail de l'équipe précédente, transmis par le Cerema sur clé USB (septembre 2026).

## Dans ce dépôt

- [documents](documents) :
  - `Définition du projet/` : présentation du projet par le Cerema, notes de définition
  - `Compte rendus de réunion/` : réunions client et rapports hebdomadaires « quatre quadrants »
  - `Livrables IMT Atlantique/` : synthèse de lancement, plan d'action, revue de projet, forum, recette finale (rapport final, présentation, retour d'expérience)
  - `poster-2025-micro-drone-de-surface.pdf` : poster
- [ia/detection/projet_2025](../../ia/detection/projet_2025) : scripts YOLO (PC et Raspberry Pi)

## Points d'entrée utiles

- **Rapport final** : `documents/Livrables IMT Atlantique/Recette finale/RapportRecetteFinale_PCE_G11_VF.docx`
  - § 2.3.3 : moteurs (Gladius Mini), Pixhawk 6C mini sous ArduPilot, pilotage par joystick via Mission Planner, GPS u-blox relié par I2C au Raspberry Pi puis envoyé au Pixhawk en MAVLink (`GPS_TYPE = 14`), stratégie de maintien de position
  - § 2.4 : entraînement YOLO, consommation, tests de dégradation (résolution, gouttes de pluie)
- **Limite signalée par l'équipe** : sous-systèmes validés en laboratoire, mais aucun essai en conditions réelles ni mission par waypoints.

## Restés sur la clé (trop lourds pour Git)

- `Travail technique/YOLO/Dataset Augmenté/` : jeu de données augmenté (environ 7 Go) et modèles entraînés
- `yolo/` : environnements Python et résultats de prédiction
- `Recording 2026-01-22 142900.mp4` : enregistrement vidéo (213 Mo)
