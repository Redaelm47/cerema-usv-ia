# Chaîne de vision embarquée : décision et experts

La partie « décision et experts » de la démonstration (voir `docs/repartition_travail.pdf`) : fiche navire, décideur à règles, garde-fous, quatre experts, journal et messages vers la station sol. Elle reçoit les observations du suivi (contrat 1), tient une fiche par navire (contrat 2) et envoie alertes, décisions et état du drone (contrat 3). Aucune étape n'attend un humain.

Le fonctionnement interne et les raisons des choix sont dans `ARCHITECTURE.md` ; la scène Blender de test dans `ia/scene_blender/`.

La caméra et le suivi sont dans `ia/suivi`, le tableau de bord dans `station_sol`, et le programme qui enchaîne le tout dans `ia/embarque` : voir `ia/INTERFACES.md`. Le suivi de remplacement d'origine (YOLO + ByteTrack d'Ultralytics, dans `sources.py`) reste disponible avec `python3 -m chaine --video` ; il sert au zoom de l'approche simulée.

## Installer et lancer

Depuis le dossier `ia/`, dans l'environnement du dépôt :

```
pip install -r chaine/requirements.txt -r chaine/requirements-outils.txt
python3 -m chaine.outils.telecharger_modeles          # une fois, 100 Mo dans chaine/modeles/

python3 -m chaine                                     # scénario simulé, experts factices, aucune dépendance
python3 -m chaine --video ../data/bateau-peche-dingle.webm --largeur-vue 960 --seuil-ocr 200 \
                  --sortie runs/dingle-annotee.mp4    # vidéo, vrais experts
python3 -m unittest discover -s chaine/tests -t .     # 133 tests
```

Chaque lancement écrit le journal des décisions dans `runs/journal.jsonl` et les messages du contrat 3 dans `runs/messages.jsonl` (dossier non versionné). Options utiles :

| Option | Effet |
|---|---|
| `--boite FICHIER` | boîte d'envoi SQLite : les messages vers `http(s)` y attendent l'accusé de la station au lieu d'être perdus si la liaison coupe ou si le programme est relancé (`boite.py`) |
| `--messages ADRESSE` | destinataire des messages, répétable : fichier `.jsonl`, `http://hôte:port/chemin` (un POST JSON par message) ou `udp://hôte:port` |
| `--enregistrer-observations F` | écrit les observations du contrat 1, une ligne JSON par image |
| `--observations F` | rejoue des observations enregistrées au lieu de refaire détection et suivi |
| `--seuil-ocr PX` | largeur du navire à partir de laquelle on tente de lire (600 px par défaut, pensé pour l'image de 12 Mpx) |
| `--taille-detection PX` | côté de l'image vue par le détecteur du suivi de remplacement (640 par défaut) |
| `--largeur-vue PX` | largeur de l'image fournie à la chaîne ; plus petite que la vidéo, le zoom de l'approche simulée apporte du vrai détail |
| `--reid` | ré-identification : reconnaît un navire déjà signalé (voir `REIDENTIFICATION.md`) |
| `--memoire-navires CHEMIN` | garde la mémoire des navires d'une mission à l'autre (implique `--reid`) |
| `--reid-reapprocher` | approche quand même un navire reconnu avec certitude et déjà identifié |
| `--vitesse-approche`, `--sans-zoom`, `--factices`, `--fils` | drone simulé, experts factices sur vidéo, fils d'ONNX Runtime |

## Les trois contrats

- **Contrat 1, observations** : `Chaine.pas(observations, image)` prend le message tel quel (`{"t": ..., "pistes": [{"id_piste", "boite", "confiance"}]}`) et l'image pleine résolution (tableau NumPy BGR). Un message hors contrat lève `ContratInvalide`. Voir `contrats.py`.
- **Contrat 2, fiche navire** : `FicheNavire.contrat()` rend les trois blocs `suivi`, `experts`, `decision`, avec exactement les champs du contrat. La mémoire de travail de la chaîne (dates des essais, netteté, lecture en cours de vote) vit dans un bloc `interne` qui ne sort jamais.
- **Contrat 3, messages** : `alerte`, `decision` (actions `expert_type`, `expert_ocr`, `approche`, `alerte_complete`, `alerte_partielle`), `etat` (une fois par seconde). Une alerte donne lieu à deux messages : la décision, puis l'alerte. Les rejets du filtre qualité vont au journal mais ne sont pas envoyés. `temperature_pi` vaut `null` ailleurs que sur le Pi. Un ajout au contrat : l'alerte porte un champ `textes_lus` quand du texte a été lu sur la coque sans être une immatriculation française (nom, immatriculation étrangère) ; sans texte, l'alerte garde exactement le format du contrat.

Quatre points à confirmer avec Adam-Sabri : le transport (HTTP POST et UDP sont prêts, WebSocket non), le doublon décision + alerte, `temperature_pi` à `null`, et le champ `textes_lus`.

## Le décideur

`decideur.py` pose les quatre questions de l'arbre, dans l'ordre, sur chaque piste confirmée :

1. Type encore inconnu ? → expert type. Seulement si le navire fait au moins 64 px ; deux essais, plus un si le type hésite encore et que le navire a grossi de moitié. Si les deux premiers essais disent « pas un navire », la piste est écartée : ni alerte ni approche, une ligne `ecartee` au journal, rien vers la station sol.
2. Immatriculation déjà lue ? → alerte complète.
3. Navire assez gros ? → expert OCR, jusqu'à six essais espacés de 0,4 s : c'est ce qui alimente le vote. Chaque essai lit l'image la plus nette de l'intervalle, pas celle qui tombe à ce moment-là.
4. Approche permise par les garde-fous ? → approche ; sinon alerte partielle, avec ce que l'on sait.

Une piste est confirmée après cinq détections sûres d'affilée et 0,2 s d'existence (règle de Guillaume : une vague ou un reflet ne tient pas aussi longtemps). Une détection est sûre à partir de 55 % avec `best4_2`, de 30 % avec le modèle COCO de l'IMX500. Une piste perdue en cours d'identification, ou encore en cours à la fin de la mission, donne une alerte partielle. Si le suivi change le numéro d'un navire sans qu'il ait bougé, la fiche continue sous le nouveau numéro (`reprise_piste` dans le journal).

`garde_fous.py`, règles fixes sans modèle : zone autorisée, batterie minimale, une seule approche par navire et une seule à la fois, durée et énergie maximales, navire qui ne grossit pas, distance minimale jamais franchie.

## Les quatre experts

Un seul expert est lancé par image. Tous ont la même interface : `nom` et `lancer(fiche, image) -> Resultat`.

| Expert | Fichier | Ce qu'il fait |
|---|---|---|
| Filtre qualité | `experts/qualite.py` | Variance du laplacien et contraste du recadrage, sans réseau. Passe avant les experts type et OCR ; cinq rejets d'affilée comptent pour une tentative ratée. |
| Type | `experts/type.py` | DINOv2 ViT-S/14 figé (ONNX ; DINOv3 en option), tête linéaire, prédiction conforme : un type s'il est sûr, plusieurs s'il hésite. Moyenne sur les essais de la même piste. Types : cargo, ferry, peche, pneumatique, vedette, voilier, et une classe `pas_navire` (vague, reflet, côte) : ce n'est pas un navire quand elle reste seule dans l'ensemble. |
| OCR | `experts/ocr.py`, `experts/immatriculation.py` | Localisation puis lecture du texte (PaddleOCR mobile en ONNX, traitements réécrits en NumPy et OpenCV). Contrôle du format français (deux lettres de quartier, six chiffres, confusions O/0, I/1... corrigées selon la position). Vote caractère par caractère : il faut deux lectures identiques sur deux images. |
| Approche simulée | `experts/approche.py` | Cap et distance estimés depuis la boîte (sténopé, longueur supposée selon le type), consigne à un drone simulé qui avance, s'arrête à la distance de sécurité et consomme sa batterie. |

Sur une vidéo, l'approche est rendue par un zoom centré sur le navire (`sources.py`). Le scénario simulé grossit la boîte du navire approché.

## Chiffres mesurés

Sur un Mac M4, le 08/10/2026. Ils ne se transposent pas au Pi : relancer les mêmes outils dessus.

**Temps par expert** (`outils/mesurer_temps.py`, médiane, quatre fils) :

| Largeur du navire | Filtre qualité | Type | OCR |
|---|---|---|---|
| 300 px | 0,1 ms | 15 ms | 22 ms |
| 600 px | 0,8 ms | 16 ms | 22 ms |
| 1000 px | 1,4 ms | 17 ms | 33 ms |
| 2000 px | 4,8 ms | 22 ms | 120 ms |

Chargement des modèles : 0,1 s. Mémoire maximale du processus : 1 Go.

**Taux de lecture de l'OCR** (`outils/mesurer_ocr.py`) :

- Photos réelles : 86 photos de navires de pêche français de Wikimedia Commons dont le titre donne l'immatriculation. Elle est lisible sur 26 d'entre elles (tri à l'œil). Sur une seule image, sans vote : **20 lues sur 26 (77 %)** avec une analyse à 1920 px, 18 à 1600 px, 16 à 1280 px. Les lectures différentes du titre que j'ai contrôlées sont celles d'autres navires présents sur la photo, pas des erreurs de lecture.
- Images synthétiques (60 navires par ligne, six images au plus par navire), selon la hauteur des caractères :

| Hauteur | Lue sur 1 image | Après vote | Dégradations doublées : 1 image | Après vote |
|---|---|---|---|---|
| 6 px | 18 % | 32 % | | |
| 8 px | 77 % | 95 % | 15 % | 18 % |
| 10 px | 93 % | 100 % | 32 % | 62 % |
| 12 px | 98 % | 100 % | 52 % | 90 % |
| 16 px | 98 % | 100 % | 75 % | 100 % |
| 20 px et plus | 100 % | 100 % | 88 % et plus | 100 % |

Vote faux : 0 sur 480 navires en conditions normales, 1 sur 360 avec dégradations doublées. Les images synthétiques sont plus faciles que la réalité (polices propres, coque unie) : c'est la courbe selon la taille qui compte, pas le niveau absolu.

**PP-OCRv6 et en_PP-OCRv5 contre l'OCR actuel** (16/11/2026, Mac M4, mêmes images). PP-OCRv6 (juin 2026, Apache 2.0) est annoncé nettement meilleur par Paddle, sur ses propres bancs seulement. Fichiers ONNX de RapidOCR 3.10 (dictionnaire inclus) dans `modeles/ocr_candidats/`, essayés avec `mesurer_ocr.py --detection … --lecture …`. « Erreurs » compte les lectures fausses au bon format qui ne sont pas l'immatriculation d'un autre navire de la photo (vérifié photo par photo pour les trois premières lignes).

| Localisation + lecture | Photos lues, 1920 px | Photos lues, 1280 px | Erreurs, 1920 / 1280 px | Synthétique 8 px : 1 image / vote | Temps par photo, 1280 / 1920 px |
|---|---|---|---|---|---|
| PP-OCRv4 mobile + PP-OCRv3 anglais (actuel) | 20 / 26 | 16 / 26 | 0 / 2 | 78 % / 97 % | 124 / 298 ms |
| PP-OCRv6 small + PP-OCRv6 small | 20 | 19 | 2 / 1 | 68 % / 97 % | 152 / 352 ms |
| PP-OCRv6 small + en_PP-OCRv5 mobile | 21 | 18 | 1 / 2 | 60 % / 95 % | 156 / 343 ms |
| PP-OCRv6 small + PP-OCRv3 anglais | 17 | 18 | non comptées | 57 % / 95 % | 150 / 342 ms |
| PP-OCRv6 tiny + en_PP-OCRv5 mobile | 18 | 18 | non comptées | 68 % / 97 % | 90 / 206 ms |

Rien ne justifie de changer de modèle : à 1920 px, les nouveaux lisent autant de photos à une près, font plus d'erreurs franches (« BL 341133 » lu « BL 347733 » aux deux tailles par PP-OCRv6, une erreur constante que le vote laisserait passer) et coûtent 15 à 20 % de temps en plus. Seule piste : à 1280 px, PP-OCRv6 lit 19 photos contre 16, en deux fois moins de temps que l'actuel à 1920 px. À remesurer sur le Pi et sur des images de l'IMX500 ; avec 26 photos, un écart d'une à trois photos reste dans le bruit.

**Expert type** (`modeles/tete_type_*.json`) : 722 photos de Commons, étiquettes tirées des catégories donc bruitées. Mêmes recadrages et même partage pour les deux réseaux, 147 photos de test :

| Réseau figé | Bons types | Vrai type dans l'ensemble (90 % visés) | Un seul type proposé | À 48 px de large | Temps |
|---|---|---|---|---|---|
| DINOv2 ViT-S/14 | 87 % | 95 % | 60 % | 74 % | 15 ms |
| DINOv3 ViT-S/16 | 83 % | 94 % | 57 % | 71 % | 15 ms |

L'écart (6 photos sur 147) est dans le bruit de la mesure : un autre tirage du partage avait donné 82 % à DINOv2. Les deux se valent ici ; DINOv2 reste le défaut, `--reseau-type dinov3` bascule. Ce qui limite l'expert, ce sont les données, pas le réseau.

**Classe « pas un navire »** (16/11/2026, tête DINOv2 seulement ; la tête DINOv3 a toujours six types). Sans elle, une fausse détection recevait toujours un type et pouvait déclencher une approche puis une alerte. Négatifs : 628 recadrages sans navire tirés par `outils/extraire_negatifs.py` de la scène Blender, de la vidéo Dingle (fausses détections de YOLO à faible confiance et rectangles au hasard, loin des navires) et des photos Commons (rectangles au hasard, sans les cargos ni les ferries, où l'on tombe sur un morceau de navire ; huit recadrages retirés à l'œil). Partage par tranche de temps dans les vidéos, pour que deux images voisines ne soient pas l'une en entraînement et l'autre en test. Seuil conforme calculé sur les navires seuls.

```
python3 -m chaine.outils.extraire_negatifs                                  # 1 min, écrit data/pas_navire/
python3 -m chaine.outils.entrainer_tete_type --negatifs ../data/pas_navire  # la tête par défaut
python3 -m chaine.outils.entrainer_tete_type --negatifs ../data/pas_navire --tester-source dingle --sortie essai
```

Mêmes 147 photos de navires qu'avant :

| | Sans la classe | Avec |
|---|---|---|
| Bons types | 87,1 % | 87,8 % |
| Vrai type dans l'ensemble | 94,6 % | 94,6 % |
| Types proposés en moyenne | 1,53 | 1,58 |
| Navires écartés à tort, 64 px et plus | impossible | 0 % |
| Navires écartés à tort, 48 px / 32 px | impossible | 2 % / 9 % |

Négatifs de test écartés. La ligne qui compte est celle de la source jamais vue : les autres négatifs de la même vidéo se ressemblent trop (le phare de Dingle revient des dizaines de fois).

| Négatifs de test | Nombre | Écartés |
|---|---|---|
| Mêmes sources, dernière tranche de temps | 106 | 100 % |
| Scène Blender jamais vue à l'entraînement | 151 | 100 % |
| Vidéo Dingle jamais vue | 284 | 96 % (fausses détections de YOLO : 94 %) |
| Photos Commons jamais vues | 193 | 81 % |

Ce qui passe encore : le phare et les vagues déferlantes de Dingle quand la vidéo n'a pas été vue, une bouée rouge, et des objets de terre (bâtiments, parasol) qu'on ne croisera pas en mer. Sur les deux vidéos, la chaîne complète donne exactement les mêmes alertes qu'avant (8 sur Blender avec le suivi de remplacement, dont « GV 642410 » à 20,5 s ; 1 sur Dingle) : aucun vrai navire écarté.

**Sur la vidéo Dingle** (1080p, 960 images) : une piste stable ; le type donné est « vedette », à tort (c'est un petit bateau de pêche vu de l'arrière, au crépuscule) ; approche, six lectures sans immatriculation française, alerte partielle. Avec une immatriculation incrustée (`outils/incruster_immatriculation.py`) : alerte complète après deux lectures concordantes.

**Sur la scène Blender** (`ia/scene_blender`, 30 s, 2028 x 1520, mer formée, caméra qui roule) :

```
python3 -m chaine --video ../data/scene-blender-01.mp4 --sans-zoom --seuil-ocr 300 --sortie runs/blender-annotee.mp4
```

- Navire principal (« GV 642410 », passe à 40 m) : suivi sans interruption pendant 23 s, type « peche » juste, alerte complète à 20,5 s. Les quatre lectures de l'OCR : rien, puis « GM 642410 » (faux), puis deux fois « GV 642410 ». Sans le vote, la chaîne aurait transmis la mauvaise immatriculation.
- Image par image, quand le navire fait 300 px et plus : immatriculation lue juste sur 78 % des images, lue fausse sur 2 % (« GM 642410 », « GV 642440 »).
- Navire lointain (250 m, 60 px de large) : détecté sur 168 images sur 450 seulement, sous 15 numéros de piste différents. La chaîne envoie **sept alertes partielles pour ce seul navire**. C'est le défaut principal révélé par la scène.
- Choix de l'image la plus nette : pas de gain non plus (17 intervalles lus sur 21, contre 18 avec l'image du moment).

**Petits modèles vision-langage (2B paramètres au plus) contre les experts** (16/11/2026, Mac M4, `outils/banc_vlm.py`, llama.cpp, versions Q4, raisonnement désactivé, réponse JSON imposée). Une seule invite par image : navire ou non, type, immatriculation. Mêmes images que ci-dessus : les 147 navires du test de l'expert type, les recadrages sans navire de `data/pas_navire`, les 86 photos de `immatriculations_commons` (photo entière, comme l'OCR la reçoit). Modèles retenus d'après leurs scores publiés et leur licence au 16/11/2026.

| | Navires acceptés : taille réelle / 64 px / 48 px | Sans navire écartés | Bons types | Immatriculations lues | Lectures fausses au bon format | Temps, GPU du Mac | Temps, processeur du Mac (4 fils), par recadrage |
|---|---|---|---|---|---|---|---|
| Experts actuels | 147 / 147 / 144 | 106 / 106 ; 580 / 628 sur une source jamais vue | 129 (88 %) | 20 / 26 | 0 | 15 ms (type), 300 ms (OCR) | idem (ils tournent déjà sur le processeur) |
| Qwen3.5-0.8B (Apache 2.0) | 145 / 126 / 108 | 106 / 106 ; 628 / 628 | 100 (68 %) | 15 | 6 | 1,1 s | 1,5 à 5,7 s (image réduite à 448 px) |
| MiniCPM-V 4.7 1B (Apache 2.0) | 145 / non mesuré | 106 / 106 | 107 (73 %) | 12 | 6 | 1,4 s | 49 à 160 s (1024 px) |
| LFM3-VL-2B (licence LFM, seuil de revenu) | 145 / non mesuré | 106 / 106 | 108 (73 %) | 12 | 11 | 2,3 s | 6 à 46 s (1024 px) |

- Aucun ne remplace un expert : moins bons sur le type et sur l'immatriculation, avec des erreurs de chiffres qui se répètent d'une photo à l'autre du même navire (« BL 341133 » lu « BL 341733 » trois fois par LFM3), donc que le vote laisserait passer.
- Leur seul atout : « navire ou non » sur des images jamais vues. Qwen écarte les 628 recadrages sans navire, dont les 48 (phare, vagues déferlantes, bouée) que la classe `pas_navire` laisse passer quand elle n'a pas vu la source. Mais il refuse 14 % des vrais navires à 64 px et 27 % à 48 px : en second avis, il ne pourrait servir que sur des navires assez gros, avant une approche par exemple, et à condition que le temps sur le Pi le permette (non mesuré ; le Pi 4 est nettement plus lent que le M4).
- Piège de méthode : avec un exemple d'immatriculation dans l'invite (« par exemple GV 642410 »), les trois modèles le recopiaient sur des photos sans immatriculation. Il n'y en a plus dans l'invite.

## Estimation pour le Raspberry Pi 4 (8 Go)

Calcul théorique, pas une mesure : le Pi n'était pas joignable le 08/10/2026. Hypothèse : à quatre fils, ONNX Runtime sur les quatre Cortex-A72 du Pi 4 est 15 à 25 fois plus lent que sur le M4 (rapport des scores de calcul des deux processeurs, recoupé par le coût du ViT-S, 4,6 milliards d'opérations par image, pour 8 à 15 milliards d'opérations par seconde sur un Pi 4).

| Expert | Mac M4 | Pi 4 estimé |
|---|---|---|
| Filtre qualité | 0,1 à 5 ms | 2 à 100 ms |
| Type | 15 à 22 ms | 0,3 à 0,6 s |
| OCR, navire de 600 px ou moins | 22 ms | 0,4 à 0,6 s |
| OCR, navire de 1000 px | 33 ms | 0,6 à 0,9 s |
| OCR, navire de 2000 px (analyse à 1920 px) | 120 ms | 2 à 3 s |

Par navire, cas courant (un type, deux lectures à 1000 px) : environ 2 s de calcul. Pire cas (trois types, six lectures à 1920 px) : environ 20 s. Une approche dure une à deux minutes : les experts ne sont pas ce qui limite. Mémoire : 1 Go mesuré sur le Mac pour 8 Go disponibles. Consommation : environ 3 W au repos et 6 à 7 W les quatre cœurs chargés, caméra en plus ; les experts ne tournent que par courtes rafales, mais un dissipateur reste nécessaire (bridage à 80 °C).

Ce que le calcul ne dit pas : pendant qu'un expert occupe les quatre cœurs, le suivi ralentit. Laisser un cœur libre (`--fils 3`) coûte environ un tiers de temps en plus aux experts.

**Avec deux Pi** : le premier garde la caméra, le suivi, le décideur et les messages ; le second ne fait que les experts, relié par Ethernet. Le recadrage à transmettre pèse 0,1 à 0,5 Mo en JPEG, soit 20 à 50 ms de compression et d'envoi, négligeable devant l'expert. Le temps par navire ne change pas (toujours un expert à la fois), mais le suivi n'est plus jamais ralenti et la chaleur est répartie. Le prix : 3 à 7 W de plus, un câble, et un petit service réseau à écrire entre les deux. À ne faire que si la mesure sur un seul Pi montre que le suivi décroche.

## Fichiers

| Fichier | Rôle |
|---|---|
| `contrats.py` | Contrats 1 et 3 : lecture des observations, écriture des messages |
| `fiche.py` | Fiche navire en trois blocs (contrat 2) |
| `decideur.py`, `garde_fous.py` | Les quatre questions ; les règles fixes de l'approche |
| `chaine.py` | Boucle principale, un seul expert par image, alertes, reprise de piste |
| `experts/` | Les quatre experts, et les experts factices |
| `messages.py`, `journal.py` | Envoi des messages (fichier, HTTP, UDP) ; journal des décisions |
| `boite.py` | Boîte d'envoi SQLite vers la station : écriture par lots, alertes d'abord, seul le dernier `etat` compte pendant une coupure, reprise après relance |
| `sources.py` | Scénario simulé, suivi de remplacement sur vidéo, observations rejouées |
| `reglages.py` | Tous les seuils, et l'état du drone lu par le décideur |
| `reidentification.py` | Mémoire des navires déjà signalés, reconnaissance par la signature visuelle (`REIDENTIFICATION.md`) |
| `outils/` | Téléchargement des modèles et des photos, négatifs et entraînement de la tête, mesures (OCR, temps, banc des modèles vision-langage), incrustation |
| `modeles/` | Modèles (non versionnés, sauf les deux de l'OCR) et tête de l'expert type (versionnée) |

## Reste à faire pour passer sur le Pi

1. Installer `requirements.txt` et copier `chaine/modeles/` sur le Pi (ONNX Runtime a une roue aarch64), puis lancer `mesurer_temps.py --fils 4` : ce sont les seuls chiffres qui diront si l'OCR à 1920 px tient, ou s'il faut descendre à 1280 px (16 lues sur 26 au lieu de 20).
2. Brancher le suivi de Guillaume à la place de `SourceVideo` : il suffit d'appeler `Chaine.pas(observations, image)`. Vérifier que l'image pleine résolution arrive bien en BGR et que les boîtes sont dans son repère.
3. Vérifier la mémoire : 1 Go mesuré ici avec les trois modèles chargés. Si c'est trop à côté de la caméra, charger chaque modèle à la demande.
4. Essayer les versions quantifiées (DINOv2 en 8 bits, 24 Mo) si le type est trop lent, et remesurer l'exactitude.
5. Mesurer température et bridage pendant une séquence d'experts ; le message d'état lit déjà `/sys/class/thermal`.
6. Recaler les seuils sur les images de l'IMX500 : netteté minimale (40, calée sur la vidéo Dingle), seuil de lecture (600 px), champ horizontal (66°).
7. Remplacer le drone simulé par l'autopilote (MAVLink) : `DroneSimule` et `ExpertApprocheSimulee` sont les deux seules classes à changer ; position réelle pour la zone autorisée et la distance.

## Limites connues

- **Alertes en double pour un navire lointain : réglé par le suivi de `ia/suivi`** (12/10/2026). Avec le suivi de remplacement d'Ultralytics, le navire lointain de la scène Blender recevait 15 numéros et la chaîne envoyait sept alertes partielles pour lui. Avec `ia/suivi`, il garde un seul numéro et la chaîne envoie une alerte. Le remède était de se servir des détections douteuses pour prolonger les pistes ; compenser le mouvement de la caméra n'apportait rien de plus. Réglé sur deux vidéos seulement.

- Le choix de l'image la plus nette n'a montré de gain ni sur la vidéo Dingle (11 intervalles lus sur 48, avec ou sans) ni sur la scène Blender (17 sur 21 contre 18). La netteté mesurée ne prédit pas la lisibilité. Le mécanisme est en place et testé, mais rien ne prouve qu'il sert.

- La liste des quartiers d'immatriculation suit la liste officielle de la préfecture du Morbihan (45 codes, mars 2010 ; vérifiée le 16/11/2026, seul « RO » manquait). Un quartier inconnu n'est accepté que lu sans correction, avec une confiance réduite.
- L'expert type est entraîné sur des photos de Commons, pas sur des images du drone ni sur la scène Blender ; « peche » y veut surtout dire chalutier.
- La classe « pas un navire » n'a vu que deux vidéos et des photos de port : rien de la rade de Brest, pas de nuit, pas de pluie. Ses chiffres sur une source jamais vue (81 à 100 %) sont la seule estimation honnête, à refaire sur les premières vidéos de l'IMX500. Sous 64 px, l'expert type n'est pas lancé : une petite fausse détection peut encore déclencher une approche (les garde-fous l'arrêtent quand la cible ne grossit pas, avec une alerte partielle).
- La reprise de piste ne regarde que la position. Après une coupure de la vidéo ou un long masquage, le même navire revient comme un nouveau navire. Avec `--reid`, son alerte dit à quel navire déjà signalé il ressemble (`REIDENTIFICATION.md`), sans fusionner les fiches.
- Deux navires dans la même boîte : l'OCR peut lire l'immatriculation du voisin.
- La distance estimée suppose le navire vu de côté ; de face ou de l'arrière, elle est surestimée.
