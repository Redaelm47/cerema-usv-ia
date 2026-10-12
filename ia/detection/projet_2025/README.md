# Scripts YOLO du projet 2025

Scripts de détection de navires de l'équipe 2025, récupérés sur la clé USB du Cerema (dossier `yolo/`).

- `yolo_detect.py` : détection sur image, dossier, vidéo, caméra USB ou Pi Camera, avec affichage.
- `yolo_detect_rasp.py` : variante pour Raspberry Pi, avec l'option `--no-display` (sans écran) et une capture Pi Camera en `XRGB8888`.
- `test.jpg`, `bateau_test.jpg`, `personne_test.jpg` : images de test.
- `detections.json` : exemple de sortie JSON obtenu sur le Raspberry Pi (une ligne par image : horodatage et liste des détections avec classe, confiance et boîte).

Exemple :

```
python yolo_detect.py --model best.pt --source test.jpg --thresh 0.5
python yolo_detect_rasp.py --model best.pt --source picamera0 --resolution 640x480 --no-display
```

Dépendances : `ultralytics`, `opencv-python`, `numpy`, et `picamera2` sur Raspberry Pi.

## Non versionné

- **Poids du modèle (`best.pt`)** : non retrouvés dans la partie copiée de la clé (dossier `Travail technique/YOLO/Dataset Augmenté/Modèles/`, copie incomplète). À récupérer sur la clé.
- **Jeu de données augmenté** (`augmented_maritime/`, train/valid, environ 7 Go) : sur la clé, dans `Travail technique/YOLO/Dataset Augmenté/`.
- Environnements virtuels Python (`venv/`) : à recréer.
