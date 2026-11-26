# Caméra et suivi

Partie 1 de la chaîne (voir [INTERFACES.md](../INTERFACES.md)) : prend les images, détecte les navires, donne à chacun un numéro stable, et rend les observations du contrat 1. Écrit par Reda le 12/10/2026 pour tester l'ensemble ; c'est la place de la partie de Guillaume.

```
python3 -m suivi --video ../data/scene-blender-01.mp4 --sortie runs/suivi.mp4    # sur le Mac
python3 -m suivi --camera 0 --toutes-classes --duree 20                          # webcam, essai sans navire
python3 -m suivi --pi --duree 20                                                 # caméra IMX500, sur le Pi
python3 -m unittest discover -s suivi/tests -t .                                 # 23 tests
```

| Fichier | Rôle |
|---|---|
| `associateur.py` | donne les numéros : principe de ByteTrack réécrit en NumPy, sans PyTorch |
| `detecteur.py` | YOLO par Ultralytics, pour le Mac, les vidéos et le simulateur : `best4_2` de Guillaume par défaut (détection sûre à 55 %), `yolo11n` (COCO) avec `--detecteur yolo11n`. Tourne sur la carte graphique quand il y en a une (NVIDIA ou Apple), sinon sur le processeur : mêmes boîtes, 12 ms par image au lieu de 34 sur un Mac |
| `camera_pi.py` | caméra IMX500 : la détection tourne dans le capteur. **Non essayé** |
| `images.py` | fichier vidéo (image par image, ou en temps réel) et webcam |
| `suivi.py` | assemble le tout et écrit le message du contrat 1 ; `Suivi.pas` traite une image à la fois (simulateur) |

## Comment un numéro est donné

1. Chaque piste prédit où sa boîte devrait être sur la nouvelle image (position et vitesse).
2. Les détections sûres (au moins 55 % avec `best4_2`, le seuil optimal de Guillaume sur son jeu de test ; 25 % sans profil) sont associées aux pistes : d'abord celles dont la boîte recouvre la prédiction, ensuite celles qui en sont seulement proches.
3. Les détections douteuses (entre 5 % et le seuil des détections sûres) ne peuvent que prolonger une piste existante. C'est ce qui garde le numéro d'un navire lointain, que le détecteur voit mal.
4. Une détection sûre que rien n'explique ouvre une nouvelle piste, sauf si elle est posée sur un navire déjà suivi (le détecteur rend parfois une seconde boîte sur la cabine).
5. Une piste qui n'est plus vue reste en mémoire 4 secondes et reprend son numéro si le navire réapparaît au même endroit, avec à peu près la même taille.
6. La caméra est à ras de l'eau : son tangage déplace les navires surtout verticalement, de plus que leur hauteur d'une image à l'autre (simulateur : 62 px en médiane contre 6 px horizontalement). L'écart vertical compte donc trois fois moins que l'écart horizontal (`poids_vertical = 0.3`), le recouvrement est mesuré à la même hauteur, et la vitesse verticale d'une boîte n'est pas prolongée (`vitesse_verticale = False`). Sur la démo du simulateur, les changements de numéro sur le chalutier passent de 104 à 16 ; rien ne change sur la vidéo de Dingle ni sur la scène Blender 01. `poids_vertical=1.0, vitesse_verticale=True` redonne l'ancien comportement.

L'associateur ne regarde que la position et la taille, jamais l'apparence. Dans le doute (deux pistes possibles pour une boîte, ou l'inverse), il n'associe pas : un numéro de plus vaut mieux que deux navires sous le même numéro.

## Mesuré sur la scène Blender

450 images, mer formée, caméra qui roule, un navire qui passe à 40 m et un autre à 250 m (60 px de large).

| | Ultralytics (YOLO + ByteTrack) | Ce suivi |
|---|---|---|
| Numéros donnés aux 2 navires | 16 | 2 |
| Alertes envoyées par la chaîne | 8 | 2 |
| Navires confondus sous un même numéro | 0 | 0 |

Le détecteur est le même dans les deux cas. Le gain vient des détections douteuses et de l'association par distance quand les boîtes ne se recouvrent pas. Compenser le mouvement de la caméra a été essayé et n'apportait rien de plus : ce n'est pas dans le code. C'est pourquoi BoT-SORT, meilleur que le ByteTrack d'Ultralytics dans les essais de Guillaume grâce à cette compensation, n'a pas été repris : ce suivi fait déjà mieux que les deux sur cette scène.

La chaîne (`ia/chaine`) ne lance les experts qu'après 5 détections sûres d'affilée (règle de Guillaume, `ia/detection/programs/test_expert_trigger.py`) : une vague ou un reflet ne tient pas aussi longtemps. Le seuil de la détection sûre suit le détecteur : 55 % avec `best4_2`, 30 % avec le modèle COCO de l'IMX500, pas encore calibré.

Sur la vidéo Dingle (un navire, 960 images) : un seul numéro.

## Limites

- Réglé sur deux vidéos seulement. Les seuils sont dans `ReglagesSuivi`.
- Deux navires l'un devant l'autre : celui de derrière perd son numéro s'il reste masqué plus de 4 secondes, et en reçoit un nouveau.
- Un navire qui réapparaît au même endroit et à la même taille qu'un autre, moins de 4 secondes après, hériterait de son numéro. Rien de tel dans les essais, mais le cas existe.
- La caméra IMX500 n'a pas été essayée dans ce code : repère des boîtes, sens de l'image et cadence sont à vérifier sur le Pi.
