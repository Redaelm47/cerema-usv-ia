"""Télécharge les modèles ONNX des experts dans chaine/modeles/ (non versionnés).

    python3 -m chaine.outils.telecharger_modeles

À faire une fois sur chaque machine (Mac, Raspberry Pi) ; ensuite la chaîne tourne hors ligne.
"""
from pathlib import Path

from .reseau import lire

DOSSIER = Path(__file__).resolve().parent.parent / "modeles"
HF = "https://huggingface.co/{depot}/resolve/main/{fichier}"

MODELES = {
    # Expert type : DINOv2 ViT-S/14 figé (Apache 2.0), exporté en ONNX par Xenova
    "dinov2_vits14.onnx": HF.format(depot="Xenova/dinov2-small", fichier="onnx/model.onnx"),
    # Variante de l'expert type : DINOv3 ViT-S/16 (licence DINOv3 de Meta), exporté par onnx-community.
    # Les poids sont dans un second fichier, qui doit garder son nom à côté du premier.
    "dinov3_vits16/model.onnx": HF.format(depot="onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX",
                                          fichier="onnx/model.onnx"),
    "dinov3_vits16/model.onnx_data": HF.format(depot="onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX",
                                               fichier="onnx/model.onnx_data"),
    # Expert OCR : PaddleOCR mobile (Apache 2.0), exporté en ONNX par RapidOCR
    "ocr_detection.onnx": HF.format(depot="SWHL/RapidOCR", fichier="PP-OCRv4/ch_PP-OCRv4_det_infer.onnx"),
    "ocr_lecture.onnx": HF.format(depot="SWHL/RapidOCR", fichier="PP-OCRv3/en_PP-OCRv3_rec_infer.onnx"),
}


def main() -> None:
    DOSSIER.mkdir(exist_ok=True)
    for nom, url in MODELES.items():
        chemin = DOSSIER / nom
        chemin.parent.mkdir(exist_ok=True)
        if chemin.exists():
            print(f"{nom} : déjà là")
            continue
        print(f"{nom} : téléchargement...", flush=True)
        chemin.write_bytes(lire(url, delai_s=600))
        print(f"{nom} : {chemin.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    main()
