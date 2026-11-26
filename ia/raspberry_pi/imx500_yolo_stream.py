"""
Détection YOLO exécutée sur la puce de la Raspberry Pi AI Camera (IMX500).
Les images annotées sont envoyées en MJPEG sur la sortie standard, pour être
affichées sur un autre ordinateur via SSH :

    ssh pi@cerema-pi.local "python3 imx500_yolo_stream.py" | ffplay -f mjpeg -fflags nobuffer -
"""
import os
import sys
import argparse

import cv2
import numpy as np
from picamera2 import Picamera2
from picamera2.devices import IMX500

COCO_LABELS = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog',
    'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella',
    'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
    'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 'bottle',
    'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant',
    'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
    'teddy bear', 'hair drier', 'toothbrush',
]

parser = argparse.ArgumentParser()
parser.add_argument('--model', default=os.path.expanduser('~/models/imx500_network_yolo11n_pp.rpk'),
                    help='Modèle IMX500 (.rpk) avec post-processing intégré')
parser.add_argument('--thresh', type=float, default=0.5, help='Seuil de confiance minimum')
parser.add_argument('--resolution', default='1280x720', help='Résolution du flux (LxH)')
parser.add_argument('--no-rotate', action='store_true', help='Ne pas retourner l\'image de 180°')
args = parser.parse_args()

# Toute la sortie standard est réservée au flux vidéo : les messages des
# bibliothèques (barre de chargement du firmware, logs) partent sur stderr.
video_out = os.fdopen(os.dup(sys.stdout.fileno()), 'wb')
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

width, height = map(int, args.resolution.split('x'))

# L'IMX500 doit être créé avant Picamera2 pour charger le modèle dans la caméra
imx500 = IMX500(args.model)
_, input_h = imx500.get_input_size()

picam2 = Picamera2(imx500.camera_num)
config = picam2.create_video_configuration(main={'size': (width, height), 'format': 'RGB888'},
                                           controls={'FrameRate': 30}, buffer_count=12)
imx500.show_network_fw_progress_bar()
picam2.start(config)

try:
    while True:
        request = picam2.capture_request()
        try:
            metadata = request.get_metadata()
            frame = request.make_array('main').copy()
        finally:
            request.release()

        detections = []
        outputs = imx500.get_outputs(metadata, add_batch=True)
        if outputs is not None:
            boxes, scores, classes = outputs[0][0], outputs[1][0], outputs[2][0]
            # Les modèles YOLO donnent des boîtes (x0, y0, x1, y1) en pixels de l'entrée
            # du réseau ; convert_inference_coords attend (y0, x0, y1, x1) normalisé.
            boxes = boxes / input_h
            boxes = boxes[:, [1, 0, 3, 2]]
            for box, score, cls in zip(boxes, scores, classes):
                if score < args.thresh:
                    continue
                x, y, w, h = imx500.convert_inference_coords(tuple(box), metadata, picam2)
                detections.append((int(x), int(y), int(w), int(h), int(cls), float(score)))

        if not args.no_rotate:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
            detections = [(width - x - w, height - y - h, w, h, c, s) for x, y, w, h, c, s in detections]

        for x, y, w, h, cls, score in detections:
            label = COCO_LABELS[cls] if 0 <= cls < len(COCO_LABELS) else str(cls)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f'{label} {score:.0%}', (x + 5, y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            video_out.write(jpeg.tobytes())
            video_out.flush()
except (KeyboardInterrupt, BrokenPipeError):
    pass
finally:
    picam2.stop()
