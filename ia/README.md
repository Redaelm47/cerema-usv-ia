# Volet IA

Objectif : créer une chaîne fonctionnelle de détection des navires passant dans le champ de vision du drone, et déterminer leur catégorie, leur immatriculation (OCR) et leur activité (tracking).

Point de départ (projet 2025) : une caméra basse résolution en fonctionnement permanent passe la main à la caméra IA lorsqu'une détection plus gourmande en énergie et en ressources est nécessaire. Les tests YOLO ont porté sur la dégradation des images en résolution et en masquage (gouttes de pluie).

- [detection](detection) : détection et classification des navires
- [ocr](ocr) : lecture des immatriculations
- [tracking](tracking) : suivi de l'activité des navires
- [raspberry_pi](raspberry_pi) : montage des caméras et portage sur Raspberry Pi 4
