# Ressources externes de la scène Blender

Les fichiers téléchargés sont rangés dans `data/blender/ressources/` (dossier non versionné).

## Navire de pêche « Sjark » (utilisé par `bateau.py`)

| | |
|---|---|
| Fichier | `data/blender/ressources/sjark_ntnu/sjark.blend` (37 Mo, textures incluses dans le fichier) |
| Contenu | Petit navire de pêche côtier norvégien (sjark), environ 60 000 triangles, textures PBR 2048 px |
| Auteur | Ocean Autonomy Cluster (jeu de données Gemini / milliAmpere, NTNU) |
| Licence | Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/ |
| Page source | https://www.itk.ntnu.no/milliampere-data/gemini/3d_models/Sjark%201/ |
| Projet | https://oceanautonomy.no/ |
| Téléchargé le | 8 octobre 2026, sans compte ni clé |

Mention à reprendre dans tout rendu ou document qui utilise le modèle :

> This work uses data from Ocean Autonomy Cluster. Data available at
> https://www.itk.ntnu.no/milliampere-data/gemini/, licensed under CC BY 4.0.

Modifications apportées par `bateau.py` (à signaler, la licence le demande) : mise à
l'échelle, repeinte de la coque et de la superstructure, mâts raccourcis de moitié,
ajout de l'immatriculation française, du nom, du radar, des antennes, des feux, du
vire-filet, des caisses et des bouées.

Pour retélécharger le modèle :

```sh
d=data/blender/ressources/sjark_ntnu
mkdir -p "$d"
for f in sjark.blend LICENSE.txt README.html; do
  curl -o "$d/$f" "https://www.itk.ntnu.no/milliampere-data/gemini/3d_models/Sjark%201/$f"
done
```

Le chemin du modèle peut aussi être donné par la variable d'environnement `BATEAU_MODELE`.
Les fichiers `sjark.fbx` et `sjark.png` du même dossier sont une copie FBX et une image
d'aperçu ; `bateau.py` ne s'en sert pas.

## Ciels HDRI (utilisés par `mer.py`, fonction `creer_ciel`)

Fichiers rangés dans `data/blender/ressources/` (non versionné, 54 Mo au total). S'ils manquent,
`mer.py` retombe sur son ciel procédural. Pour les retélécharger : les URL ci-dessous.

| Fichier | Usage (couverture) | Auteurs | Licence | Page | Lien direct |
|---|---|---|---|---|---|
| `kloofendal_38d_partly_cloudy_puresky_4k.hdr` (20 Mo) | < 0,45 : éclaircies, soleil à 38° | Greg Zaal (original), Jarod Guest (retouche du ciel) | CC0 | https://polyhaven.com/a/kloofendal_38d_partly_cloudy_puresky | https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/kloofendal_38d_partly_cloudy_puresky_4k.hdr |
| `kloofendal_28d_misty_puresky_4k.hdr` (16 Mo) | 0,45 à 0,75 : ciel voilé, soleil diffus à 28° | Jenelle van Heerden (photo), Greg Zaal (traitement) | CC0 | https://polyhaven.com/a/kloofendal_28d_misty_puresky | https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/kloofendal_28d_misty_puresky_4k.hdr |
| `overcast_soil_puresky_4k.hdr` (17 Mo) | ≥ 0,75 : couvert gris | Sergej Majboroda (original), Jarod Guest (retouche du ciel) | CC0 | https://polyhaven.com/a/overcast_soil_puresky | https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/overcast_soil_puresky_4k.hdr |

Source : Poly Haven (https://polyhaven.com), liens obtenus par l'API https://api.polyhaven.com/files/<identifiant>,
téléchargés le 8 octobre 2026. Ce sont des « pure skies » (sans sol ni horizon terrestre).
