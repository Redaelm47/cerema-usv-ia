# Scène Blender de test

Ce que voit le drone quand un navire de pêche passe : la vidéo de test de la chaîne de vision (`ia/chaine`).

- `scene.py` : la séquence. Caméra du drone à 1,2 m de l'eau, 66° de champ, 2028 x 1520 (la moitié de la résolution de l'IMX500), 15 images/s pendant 30 s. Le navire principal (« GV 642410 », 14 m) vient de loin sur la gauche, coupe le champ en biais et en sort par la droite, au plus près à 40 m. Un second navire (« CC 911290 ») passe à 250 m, trop loin pour être lu.
- `mer.py` : mer animée (trois champs de vagues superposés, écume, sillages), ciel, brume, côte lointaine, et la caméra qui roule, tangue et pilonne avec la mer.
- `bateau.py` : le navire, à partir d'un modèle libre repeint, avec son immatriculation sur les deux bords de l'étrave.
- `RESSOURCES.md` : les fichiers téléchargés (modèle du navire, ciels), leurs auteurs et leurs licences. Le modèle du navire est sous CC BY 4.0 : la mention d'attribution qui s'y trouve doit accompagner toute diffusion de la vidéo.

## Lancer

Blender 5.2, depuis ce dossier. Les ressources vont dans `data/blender/ressources/` (voir `RESSOURCES.md`).

```
blender -b -P scene.py -- --apercu 400 /tmp/apercu.jpg      # une image, pour vérifier
blender -b -P scene.py -- --rendu                            # la séquence, dans data/blender/rendu/scene_01/
ffmpeg -framerate 15 -i ../../data/blender/rendu/scene_01/image_%04d.jpg -c:v libx264 -crf 14 -pix_fmt yuv420p ../../data/scene-blender-01.mp4
```

Compter 13 s par image sur un Mac M4 (Cycles sur le GPU), soit environ 1 h 40 pour les 451 images, et jusqu'à 8 Go de mémoire. Un rendu interrompu reprend où il s'était arrêté. `verite.json`, écrit à côté des images, donne pour chaque image la position et la distance de chaque navire.

Pour varier les conditions : `--couverture` (0 ciel clair, 1 couvert), `--graine`, et en tête de `scene.py` l'état de la mer et les routes des navires.

## Limites

- Les navires bougent avec la mer mais ne sont pas couplés à la vague exacte sous leur coque, et l'eau n'est pas repoussée par la coque.
- Peu de moutons visibles, même par mer formée.
- Le navire est un côtier norvégien, pas un chalutier breton.
