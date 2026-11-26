# Architecture de la partie « décision et experts »

Ce document explique comment la chaîne est construite et pourquoi. Le mode d'emploi, les chiffres mesurés et ce qui reste à faire sont dans `README.md`. La proposition d'origine est dans `docs/architecture_vision_embarquee.pdf` ; la section « Écarts » dit en quoi le code s'en éloigne.

## Vue d'ensemble

```
caméra + suivi (Guillaume)                      station sol (Adam-Sabri)
        │ contrat 1 : observations + image                ▲ contrat 3 : alerte, decision, etat
        ▼                                                 │
   ┌─────────────────────────────── Chaine.pas ───────────┴──────────┐
   │ 1. fiches : une par navire (contrat 2)                          │
   │ 2. image la plus nette retenue pour chaque navire à lire        │
   │ 3. décideur : une action par fiche (les quatre questions)       │
   │ 4. au plus UN expert lancé : filtre qualité → type ou OCR,      │
   │    ou approche (garde-fous)                                     │
   │ 5. alerte, messages, journal                                    │
   └─────────────────────────────────────────────────────────────────┘
```

Une image entre, la chaîne la traite jusqu'au bout, et rend la main. Il n'y a ni fil d'exécution caché ni attente : c'est ce qui la rend testable image par image et prévisible sur le Pi. La seule exception est l'envoi réseau des messages, qui passe par un fil à part pour qu'une station sol lente ne ralentisse rien.

## Le trajet d'une image (`chaine.py`)

1. **Lecture du contrat 1** (`contrats.lire_observations`). Un message mal formé est refusé tout de suite.
2. **État du drone** (`Contexte`) : batterie, zone, mode, distance au navire approché. Il vient du drone simulé aujourd'hui, de l'autopilote plus tard.
3. **Mise à jour des fiches**. Bloc `suivi` : boîte, confiance, nombre d'images d'affilée. Bloc `decision` : la piste devient confirmée, ou perdue.
4. **Image la plus nette**. Pour chaque navire en attente de lecture, on garde le recadrage le plus net vu depuis le dernier essai.
5. **Décision**, fiche par fiche, de la plus ancienne à la plus récente. Dès qu'un expert a été lancé, les autres fiches attendent l'image suivante.
6. **Message d'état**, une fois par seconde.

## La fiche navire (`fiche.py`)

Trois blocs, comme dans le contrat 2, et chacun n'écrit que dans le sien :

| Bloc | Qui écrit | Contenu |
|---|---|---|
| `suivi` | le suivi | première et dernière vue, images d'affilée, boîte, confiance, vitesse apparente |
| `experts` | les experts | types possibles, confiance du type, immatriculation, sa confiance |
| `decision` | le décideur | état, nombre de tentatives par expert, début de l'approche |

Un quatrième bloc, `interne`, est la mémoire de travail de la chaîne : date du dernier essai de chaque expert, rejets du filtre qualité, netteté, lecture en cours de vote, textes lus sur la coque, repères de l'approche. Il va dans le journal mais ne sort jamais dans un message.

États d'une piste : `nouvelle` → `confirmee` → (`en_approche`) → `alertee`, ou `perdue` si elle disparaît plus de cinq secondes.

## Le décideur (`decideur.py`)

Une fonction pure : une fiche et l'état du drone en entrée, une action et sa raison en sortie. Elle ne regarde aucune image et ne modifie rien, ce qui permet de tester chaque règle en une ligne.

| Ordre | Question | Action |
|---|---|---|
| 0 | Piste confirmée et visible sur cette image ? | sinon attendre |
| 1 | Type encore inconnu, et navire d'au moins 64 px ? | expert type |
| 2 | Immatriculation validée ? | alerte complète |
| 3 | Navire d'au moins `seuil_ocr_px` ? | expert OCR |
| 4 | Approche permise ? | approche, sinon alerte partielle |

Règles ajoutées autour de l'arbre :

- **Confirmation** : cinq détections sûres d'affilée (règle de Guillaume ; sûre = 55 % avec `best4_2`, 30 % avec le modèle COCO de l'IMX500) et 0,2 s d'existence. Une vague, un caillou ou un reflet ne tient pas aussi longtemps.
- **Essais comptés et espacés** : deux pour le type, six pour l'OCR, 0,4 s entre deux essais du même expert. Sans limite, un navire illisible bloquerait la chaîne ; sans espacement, on relirait la même image.
- **Type hésitant** : nouvel essai seulement si le navire a grossi de moitié depuis le dernier.
- **Piste perdue ou fin de mission** : alerte partielle avec ce que l'on sait. Aucune piste confirmée ne reste sans réponse.
- **Une seule approche à la fois** : les autres navires attendent, mais peuvent être lus s'ils sont assez gros.

## Les garde-fous (`garde_fous.py`)

Des règles fixes, sans modèle appris, parce que personne ne valide l'approche.

- Avant : drone dans la zone, batterie au-dessus de 30 %, navire jamais approché.
- Pendant : abandon après 120 s, après 10 % de batterie consommée, si le navire n'a pas grossi au bout de 20 s (il s'éloigne plus vite que le drone), si la zone est quittée, ou si la distance minimale de 30 m est atteinte sans pouvoir lire.

## Les experts (`experts/`)

Tous ont la même forme : un attribut `nom` et une méthode `lancer(fiche, image)` qui rend un `Resultat` (réussi ou non, et des valeurs). Un expert se remplace sans toucher au reste.

### Filtre qualité (`qualite.py`)

Variance du laplacien (netteté) et écart-type (contraste) du recadrage en niveaux de gris, ramené à 512 px. Pas de réseau, moins d'une milliseconde. Il passe avant les experts type et OCR. Cinq rejets d'affilée comptent pour une tentative ratée, sinon un navire toujours flou tournerait sans fin.

### Type (`type.py`)

1. Le recadrage est placé entier dans un carré de 224 px.
2. Un réseau figé, DINOv2 ViT-S/14, en tire une **signature** : 768 nombres qui résument l'apparence du navire (384 pour le jeton de classe, 384 pour la moyenne des jetons de l'image), ramenés à la norme 1.
3. Une tête linéaire donne une probabilité par type. Elle s'entraîne en une minute (`outils/entrainer_tete_type.py`).
4. Prédiction conforme : on garde tous les types dont la probabilité dépasse un seuil calibré pour que le vrai type soit dans l'ensemble neuf fois sur dix. Un type : l'expert est sûr. Plusieurs : il hésite, et l'alerte le dit.
5. Les probabilités sont moyennées sur les essais de la même piste.

Pourquoi un réseau figé et une petite tête : on a très peu d'images étiquetées, et réentraîner la tête ne demande ni carte graphique ni PyTorch. DINOv3 est disponible en option ; mesuré sur les mêmes photos, il fait jeu égal.

### OCR (`ocr.py`, `immatriculation.py`)

1. **Localisation** : DBNet (PP-OCRv4 mobile) rend une carte de probabilité de texte. Le recadrage est mis entre 736 et 1920 px de grand côté : agrandir un petit navire aide la localisation, plafonner borne le temps de calcul.
2. **Découpe** : chaque zone est redressée (perspective) et ramenée à 48 px de haut.
3. **Lecture** : CRNN (PP-OCRv3 mobile, alphabet latin), décodage CTC restreint aux lettres, chiffres, espace, point et tiret.
4. **Assemblage** : le quartier et le numéro forment parfois deux zones ; on essaie aussi les paires de zones voisines sur une même ligne.
5. **Format** : deux lettres de quartier, six chiffres, isolés du reste. Les confusions habituelles sont corrigées selon la position (O/0, I/1, S/5, B/8...), au plus deux par lecture. Un quartier absent de la liste n'est accepté que sans correction.
6. **Vote** : caractère par caractère, pondéré par la confiance, sur les lectures de la même piste. Il faut deux lectures identiques, sur deux images, pour valider.

Les textes lus qui ne sont pas une immatriculation française (nom du navire, immatriculation étrangère) sont comptés ; ceux lus au moins deux fois partent dans l'alerte, champ `textes_lus`.

Les traitements avant et après les réseaux sont réécrits en NumPy et OpenCV pour ne dépendre que d'ONNX Runtime.

### Approche simulée (`approche.py`)

- **Estimation** : cap par la position de la boîte dans l'image, distance par le modèle du sténopé avec une longueur supposée selon le type.
- **Consigne** : s'arrêter à la distance où le navire dépasserait le seuil de lecture, jamais en dessous de la distance minimale.
- **Drone simulé** : avance à vitesse constante, consomme sa batterie plus vite en approche. Les sources d'images lisent son rapprochement pour grossir le navire (zoom sur vidéo).

## Messages et journal (`messages.py`, `journal.py`, `contrats.py`)

- **Messages** : `decision` à chaque expert lancé et à chaque alerte, `alerte`, `etat` chaque seconde. L'adresse choisit le transport : fichier, HTTP POST ou UDP.
- **Journal** : une ligne JSON par action, avec la fiche, le résultat de l'expert, son temps et la netteté. C'est la preuve de ce qui a été décidé, et la matière pour entraîner plus tard un décideur appris : chaque ligne dit si l'expert a réussi dans cet état de la fiche.

## Reconnaître un navire : ce qui est fait, ce qui ne l'est pas

Le numéro de piste vient du suivi (ByteTrack) : d'une image à la suivante, une boîte qui recouvre celle d'avant garde son numéro. Ce n'est pas une identification du navire, seulement une continuité de position. Quand le navire est masqué ou que la détection saute, le suivi peut lui donner un nouveau numéro.

La chaîne ne rattache deux numéros que dans un cas : un nouveau numéro apparaît là où une fiche a disparu depuis moins de deux secondes, avec des boîtes qui se recouvrent, alors qu'aucune autre piste n'occupe la place (`reprise_piste` dans le journal).

La signature visuelle de l'expert type pourrait servir à reconnaître un navire déjà vu, mais **elle ne suffit pas à fusionner deux fiches**. Mesuré sur 25 photos réelles de navires de pêche : au seuil de similarité 0,85, le même navire est reconnu dans 82 % des paires, et deux navires différents sont confondus dans 1 % des paires ; au seuil 0,9, aucune confusion mais seulement 55 % de reconnaissance. Deux fileyeurs bleus se ressemblent trop. Fusionner à tort ferait disparaître un navire : la chaîne ne le fait donc jamais sur la seule apparence. La seule preuve d'identité est l'immatriculation lue.

La ré-identification (`reidentification.py`, option `--reid`) se sert de la signature sans rien fusionner : elle informe l'alerte (`deja_vu`), permet de valider une immatriculation sur une seule lecture quand elle confirme la ressemblance, et évite de réapprocher un navire reconnu avec certitude. Détail et mesure : `REIDENTIFICATION.md`.

## Écarts avec la proposition d'origine

| Proposition | Code | Raison |
|---|---|---|
| Fiche à plat dans le squelette | Trois blocs | Contrat 2 |
| Type une fois par navire | Deux essais, plus un si le navire grossit | Un recadrage de 60 px classe mal |
| OCR dès que le navire est assez gros | Six essais espacés, image la plus nette, vote | Une lecture seule se trompe |
| Confirmation sur cinq détections sûres | Cinq images, 0,2 s, 55 % avec `best4_2` | Fausses pistes sur les vagues et les reflets |
| DINO sans précision de version | DINOv2 par défaut, DINOv3 en option | Résultats égaux, licence plus simple |
| Alerte sans texte libre | `textes_lus` si quelque chose a été lu | Navires étrangers, nom du navire |
| Approche par MAVLink | Drone simulé | Hors périmètre pour l'instant |
| Ré-identification « ensuite » | Reprise par position ; mémoire des navires qui informe sans fusionner (`--reid`) | La signature seule confond des navires |
| Décideur appris (étape 2) | Non fait | Il faut d'abord des journaux |
