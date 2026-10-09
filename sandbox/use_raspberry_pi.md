# Guide d'utilisation - Raspberry Pi & YOLO (Cerema)

Ce guide rassemble toutes les commandes essentielles pour vous connecter au Raspberry Pi, lancer la détection YOLO avec votre modèle, streamer le flux en direct ou récupérer vos fichiers.

## ⚠️ Consigne de sécurité primordiale
- Toujours éteindre le Raspberry Pi (`sudo shutdown now`) avant de brancher ou débrancher la nappe de la caméra. Ne jamais brancher à chaud sous peine de griller le matériel.

## 1. Connexion SSH au Raspberry Pi
Depuis votre PC portable :

```
ssh pi@cerema-pi.local
```

(Mot de passe : cerema)

## 2. Lancer la détection YOLO avec enregistrement
Une fois connecté au Pi, exécutez ces commandes :
```
cd Desktop/Yolo_test
```
```
source yolo_env/bin/activate
```

```
python yolo_detect_rasp.py --model best.pt --source picamera0 --resolution 640x480 --record --no-display
```

*(Pour arrêter l'enregistrement : appuyez sur Ctrl + C. La vidéo demo1.avi sera générée dans le dossier).*

## 3. Diffuser le flux vidéo en direct (Streaming distant)
Pour lancer un affichage en direct du flux de la caméra depuis le Pi directement sur votre PC :

```
ssh pi@cerema-pi.local "rpicam-vid -t 0 -n --inline --rotation 180 --width 1280 --height 720 --framerate 15 --post-process-file /usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json -o -" | ffplay -fflags nobuffer -flags low_delay -framedrop -
```

## 4. Récupérer la vidéo demo1.avi sur votre PC
Depuis un terminal sur votre PC portable :
```
scp pi@cerema-pi.local:Desktop/Yolo_test/demo1.avi .
```

*(Astuce lecture : Si la vidéo enregistrée paraît accélérée, ouvrez-la avec VLC et appuyez sur la touche `[` pour baisser la vitesse en dessous de 0.67x).*