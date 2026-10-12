# Volet IA

Objectif : créer une chaîne fonctionnelle de détection des navires passant dans le champ de vision du drone, et déterminer leur catégorie, leur immatriculation (OCR) et leur activité (tracking).

Point de départ (projet 2025) : une caméra basse résolution en fonctionnement permanent passe la main à la caméra IA lorsqu'une détection plus gourmande en énergie et en ressources est nécessaire. Les tests YOLO ont porté sur la dégradation des images en résolution et en masquage (gouttes de pluie).

Architecture retenue pour 2026 : [docs/architecture_vision_embarquee.pdf](../docs/architecture_vision_embarquee.pdf). La caméra IMX500 veille, le suivi donne un numéro à chaque navire, un décideur lance un expert à la fois (type, OCR, approche), et une alerte courte part vers la [station sol](../station_sol). La répartition du travail et les formats JSON échangés sont dans [docs/repartition_travail.pdf](../docs/repartition_travail.pdf).

- [INTERFACES.md](INTERFACES.md) : les trois parties (suivi, décision, station sol), ce que chacune reçoit et rend
- [suivi](suivi) : caméra et numéros de piste (partie 1)
- [chaine](chaine) : décision et experts (partie 2)
- [embarque](embarque) : le programme complet qui tourne sur le Pi
- [detection](detection) : détection et classification des navires
- [ocr](ocr) : lecture des immatriculations
- [tracking](tracking) : suivi de l'activité des navires
- [raspberry_pi](raspberry_pi) : montage des caméras et portage sur Raspberry Pi 4
