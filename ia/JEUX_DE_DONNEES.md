# Jeux de données publics utiles à la vision embarquée

État vérifié le 8 octobre 2026 (pages officielles et existence des fichiers ; rien n'a été téléchargé sauf mention). Aucun jeu public ne couvre à la fois le point de vue d'un drone de surface, le type de navire et l'immatriculation. Le Cerema n'a pas de jeu de données à fournir.

## Détection et suivi depuis l'eau

| Nom | Contenu | Accès | Licence | Intérêt |
|---|---|---|---|---|
| MODD2 (ViCoS, Ljubljana) | 28 vidéos continues depuis un drone de surface, 11 675 images 1278x958, obstacles en boîtes (grand, petit) | direct, 1,7 Go : `https://data.vicos.si/borja/modd2_dataset/MODD2_video_data_rectified.zip` et `MODD2_annotations_v2_rectified.zip` | non indiquée | vraies vidéos au ras de l'eau ; pas de type, pas de numéro de piste |
| Singapore Maritime Dataset | 81 vidéos 1080p (rivage, embarqué, infrarouge), vérité de détection et de suivi | Google Drive depuis `https://sites.google.com/site/dilipprasad/home/singapore-maritime-dataset` ; annotations corrigées : `https://github.com/kjunhwa/SMD-Plus` | non indiquée | vidéos continues avec suivi ; partie embarquée prise d'un navire, plus haut qu'un drone |
| MODS (ViCoS) | environ 81 000 images depuis un drone de surface, boîtes bateau / nageur / autre | lien SharePoint dans `https://github.com/bborja/mods_evaluation`, à ouvrir dans un navigateur | non indiquée | banc d'essai de détection ; pas de type |
| LaRS (ViCoS) | plus de 4 000 scènes de 10 images, segmentation (bateau, barque, bouée, nageur...) | formulaire : `https://lojzezust.github.io/lars-dataset/` | CC BY-NC 4.0 | diversité des scènes ; trop court pour un suivi |
| WaterScenes | 54 120 images depuis un drone de surface, 7 classes (ship, boat, vessel, kayak...) | `https://github.com/WaterScenes/WaterScenes` | CC BY-NC-SA 4.0 | bon point de vue ; eaux intérieures, classes éloignées des nôtres |
| FVessel | 26 vidéos du Yangtsé, pistes au format MOT, AIS | `https://huggingface.co/datasets/gy65896/FVessel` (2,6 à 41 Go) | MIT | vérité de suivi ; caméra fixe en hauteur |
| MaSTr1325 (ViCoS) | 1 325 images isolées, segmentation eau / ciel / obstacle | `https://www.vicos.si/resources/mastr1325/` | CC BY 4.0 | peu utile ici |

## Type de navire

| Nom | Contenu | Accès | Licence | Intérêt |
|---|---|---|---|---|
| ABOships | 9 880 images 720p prises d'un bateau en mouvement, 41 967 boîtes, 11 catégories (cargo, ferry, voilier, bateau à moteur, navire à passagers...) | direct, 8,2 Go : `https://zenodo.org/records/4736931` | CC BY 4.0 | le meilleur pour l'expert type : vu depuis l'eau ; ni pêche ni pneumatique |
| SeaShips | environ 7 000 images de caméras côtières, 6 types dont bateau de pêche | miroir non officiel : `https://huggingface.co/datasets/dronefreak/SeaShips` | inconnue | cargo, pêche, passagers ; vue en hauteur, navires fluviaux chinois |
| Warships-ReID | 183 navires, 4 780 images, 8 types dont pêche et voilier | Google Drive depuis `https://github.com/scott0o0/Warships-Reid` | non indiquée | type et ré-identification à la fois |

## Texte et immatriculation

| Nom | Contenu | Accès | Licence | Intérêt |
|---|---|---|---|---|
| Hull inscriptions (Wawrzyniak et al., 2022) | 100 images de 56 navires avec inscriptions de coque, 100 sans | direct, 92 Mo : `https://ndownloader.figshare.com/files/36107570` | CC BY 4.0 | seul jeu public trouvé ; test de l'OCR, trop petit pour entraîner |

Aucun jeu public d'immatriculations françaises de navires. Nos 86 photos de Wikimedia Commons (`outils/telecharger_photos_immatriculees.py`) restent la seule mesure sur le format français.

## Ré-identification

| Nom | Contenu | Accès | Intérêt |
|---|---|---|---|
| Warships-ReID | voir plus haut | Google Drive | petit, direct |
| VesselReID (vsislab) | 1 248 navires, 30 587 images | accord à signer : `https://github.com/vsislab/VesselReID` | le plus sérieux, mais démarche et délai |

## Par où commencer

1. ABOships pour réentraîner et mesurer l'expert type sur des vues prises depuis l'eau.
2. MODD2 pour essayer détection et suivi sur de vraies vidéos de drone de surface.
3. Hull inscriptions pour un second test de l'OCR, et Warships-ReID pour mesurer la signature.

Non vérifié : taille et accès réels de MODS, contenu de USVTrack (`https://usvtrack.github.io`), liens Google Drive non ouverts.
