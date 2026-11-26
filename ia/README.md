# Volet IA

Objectif : créer une chaîne fonctionnelle de détection des navires passant dans le champ de vision du drone, et déterminer leur catégorie, leur immatriculation (OCR) et leur activité (tracking).

Point de départ (projet 2025) : une caméra basse résolution en fonctionnement permanent passe la main à la caméra IA lorsqu'une détection plus gourmande en énergie et en ressources est nécessaire. Les tests YOLO ont porté sur la dégradation des images en résolution et en masquage (gouttes de pluie).

Architecture retenue pour 2026 : [docs/architecture_vision_embarquee.pdf](../docs/architecture_vision_embarquee.pdf). La caméra IMX500 veille, le suivi donne un numéro à chaque navire, un décideur lance un expert à la fois (type, OCR, approche), et une alerte courte part vers la [station sol](../station_sol). La répartition du travail et les formats JSON échangés sont dans [docs/repartition_travail.pdf](../docs/repartition_travail.pdf).

- [INTERFACES.md](INTERFACES.md) : les trois parties (suivi, décision, station sol), ce que chacune reçoit et rend
- [suivi](suivi) : caméra, détection et numéros de piste (partie 1)
- [chaine](chaine) : décision et experts qualité, type, immatriculation (OCR), approche, ré-identification (partie 2)
- [embarque](embarque) : le programme complet qui tourne sur le Pi
- [simulateur](simulateur) : simulateur 3D du Goulet et de la rade de Brest, vus depuis la caméra du drone, pour tester la chaîne de bout en bout (détection, alerte, approche) par tous les temps
- [scene_blender](scene_blender) : vidéos de test rendues avec Blender
- [detection](detection) : entraînement du détecteur (modèles best4, tests de dégradation)
- [raspberry_pi](raspberry_pi) : montage des caméras et déploiement sur le Raspberry Pi
