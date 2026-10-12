# Modèles

Les fichiers `.onnx` et `.pt` ne sont pas versionnés. Pour les obtenir, depuis `ia/` :

```
python3 -m chaine.outils.telecharger_modeles
```

| Fichier | Rôle | Origine | Licence |
|---|---|---|---|
| `dinov2_vits14.onnx` (88 Mo) | expert type, réseau figé | DINOv2 ViT-S/14, export `Xenova/dinov2-small` | Apache 2.0 |
| `dinov3_vits16/` (86 Mo) | expert type, variante | DINOv3 ViT-S/16, export `onnx-community` | licence DINOv3 de Meta |
| `tete_type_dinov2.npz`, `tete_type_dinov3.npz` (versionnés) | expert type, tête linéaire et seuil conforme | `outils/entrainer_tete_type.py --reseau ...` | la nôtre |
| `tete_type_*.json` (versionnés) | chiffres mesurés à l'entraînement de chaque tête | idem | |
| `ocr_detection.onnx` (4,7 Mo) | expert OCR, localisation du texte | PP-OCRv4 mobile, export `SWHL/RapidOCR` | Apache 2.0 |
| `ocr_lecture.onnx` (9 Mo) | expert OCR, lecture (alphabet latin) | PP-OCRv3 mobile anglais, export `SWHL/RapidOCR` | Apache 2.0 |
| `yolo11n.pt` | suivi de remplacement seulement | Ultralytics, téléchargé au premier lancement | AGPL 3.0 |

Par défaut, les experts n'utilisent que des modèles sous Apache 2.0. DINOv3 (licence propre) n'est qu'une option de test, et seul le suivi de remplacement dépend d'Ultralytics (AGPL).
