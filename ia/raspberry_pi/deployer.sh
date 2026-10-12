#!/bin/sh
# Copie le programme embarqué sur le Raspberry Pi et installe ses dépendances.
#
#     sh ia/raspberry_pi/deployer.sh                    # vers pi@cerema-pi.local
#     sh ia/raspberry_pi/deployer.sh pi@192.168.137.200
#
set -e
PI="${1:-pi@cerema-pi.local}"
IA="$(cd "$(dirname "$0")/.." && pwd)"

echo "Copie vers $PI:cerema/ia (110 Mo de modèles la première fois)"
ssh "$PI" "mkdir -p cerema/ia"
# Ni PyTorch ni YOLO sur le Pi : la détection tourne dans la caméra. DINOv3 est l'option non retenue.
rsync -av --delete \
    --exclude "__pycache__" --exclude "tests" \
    --exclude "modeles/yolo11n.pt" --exclude "modeles/dinov3_vits16" \
    "$IA/chaine" "$IA/suivi" "$IA/embarque" "$PI:cerema/ia/"

# Pour l'essai sans caméra : la vidéo Blender et les observations que le suivi en a tirées sur le Mac.
VIDEO="$IA/../data/scene-blender-01.mp4"
OBSERVATIONS="$IA/runs/suivi-blender-observations.jsonl"
if [ -f "$VIDEO" ] && [ -f "$OBSERVATIONS" ]; then
    echo "Copie de la vidéo Blender (134 Mo) et de ses observations vers $PI:cerema/essai"
    ssh "$PI" "mkdir -p cerema/essai"
    rsync -av "$VIDEO" "$OBSERVATIONS" "$PI:cerema/essai/"
fi

echo "Installation des dépendances (environnement cerema/env)"
# --system-site-packages : picamera2 est fourni par le système du Pi, pas par pip.
# NumPy reste celui du système (2.2 sur Raspberry Pi OS Trixie), avec lequel picamera2 est compilé.
ssh "$PI" 'cd cerema && { [ -d env ] || python3 -m venv --system-site-packages env; } &&
    env/bin/pip install --quiet opencv-python-headless onnxruntime &&
    env/bin/python -c "import onnxruntime, cv2, numpy, picamera2; print(\"dépendances prêtes, ONNX Runtime\", onnxruntime.__version__)"'

cat <<FIN

Prêt. Sur le Mac, lancer la station sol :
    cd station_sol && python3 serveur.py          (elle affiche l'adresse à donner au Pi)
Puis sur le Pi (ssh $PI, puis cd cerema/ia) :
    essai sans caméra, vidéo Blender rejouée, experts calculés sur le Pi :
        ../env/bin/python -m chaine --video ../essai/scene-blender-01.mp4 \\
            --observations ../essai/suivi-blender-observations.jsonl --seuil-ocr 300 --fils 4 \\
            --messages http://NOM-DU-MAC.local:8000/message
    avec la caméra, qui filme l'écran du Mac où passe la vidéo :
        ../env/bin/python -m embarque --pi --seuil-ocr 300 --station http://NOM-DU-MAC.local:8000
FIN
