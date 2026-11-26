# Simulateur Iroise : consignes pour les agents de code

Ce fichier s'adresse aux agents (Claude Code, Codex, Cursor…) qui travaillent sur `ia/simulateur/`. Le [README](README.md) décrit le simulateur pour l'équipe ; ici, ce qu'un agent doit savoir pour le lancer, s'en servir pour tester la chaîne IA et le modifier sans rien casser.

## En bref

- Simulateur temps réel dans le navigateur : Three.js 0.187 (WebGL 2) et Vite 8, sans moteur de jeu ni autre dépendance.
- Il sert à tester de bout en bout la chaîne de vision du drone (détection, suivi, décision, alerte, approche) sur la vraie géographie du Goulet et de la rade de Brest, vue depuis une caméra à 45 cm au-dessus de l'eau.
- `src/` le code, `public/` les données et les modèles 3D, `tools/` les scripts qui génèrent les données, `bridge/` les passerelles Python vers une chaîne IA.
- Interface, commentaires et messages de commit en français.

## Lancer

```bash
cd ia/simulateur
npm install      # une fois : three et vite
npm run dev      # http://127.0.0.1:5173
```

- Node.js 20.19 ou plus récent. Ne rien installer d'autre sur la machine sans l'accord de la personne.
- Le port 5173 est fixe (`strictPort`) : s'il est pris, un serveur du simulateur tourne sans doute déjà, le réutiliser.
- Dans l'application Claude (onglet Code), `.claude/launch.json` à la racine du dépôt déclare ce serveur sous le nom `simulateur`, pour l'aperçu intégré.
- Vérifier la compilation avec `npm run build` (sortie dans `dist/`, ignorée par git).
- Arrêter le serveur quand la personne n'en a plus besoin.

## Monter un scénario de test

Le plus simple pour un test reproductible : un fichier de scénario dans `public/scenarios/` (voir `demo-tuteur.json`), chargé par `?scenario=nom` : météo, heure, position et route du drone, navires, trafic automatique. Sinon, par l'URL : `?weather=Brume`, `?hour=20.5&month=6`, `?x=..&z=..` (position en mètres locaux), `?hdg=90&speed=1.5`, `?ships=0` (pas de trafic), `?bridge=1` (se connecte à la chaîne), `?gt=1` (boîtes de vérité terrain), `?ui=0` (image caméra seule), `?map=1`, `?dpr=1` (résolution fixe), `?drops=0`, `?models=0`. La liste complète est dans le README.

À la main :

- `C` ouvre la carte satellite : chercher un lieu, téléporter le drone (glisser pour le cap), tracer la route du drone (il la suit en boucle et la reprend après chaque approche), poser des navires (type, vitesse, cap, route en boucle), couper le trafic automatique. Les navires posés restent jusqu'à ce qu'on les supprime et figurent dans l'AIS envoyé à la chaîne.
- Le panneau Réglages donne l'heure, le mois, la météo (Clair, Nuageux, Couvert, Brume, Coup de vent, Couchant, Pluie, Grain), le vent, la houle, la marée, la pluie, la buée sur l'objectif, le trafic et la caméra.
- `M` prend ou rend la main, `1` `2` `3` changent de vue, `B` affiche la vérité terrain, `H` masque l'interface, `P` fait une capture PNG.

Pour un test de robustesse (gouttes, buée, contre-jour, brume, houle), changer un seul réglage à la fois et noter les valeurs dans le compte rendu du test.

## Brancher une chaîne IA

Le simulateur est client WebSocket de `ws://127.0.0.1:8765` (`?ws=` pour une autre adresse).

- Détecteur par défaut : `yolo11n`, celui de la caméra IMX500. `best4_2` voit des navires dans les nuages et sur la mer vide du simulateur : à mesurer avant de s'en servir.
- `bridge/chaine_cerema.py` fait tourner la chaîne du projet (`ia/suivi`, `ia/chaine`) de cette copie du dépôt sur les images du simulateur. `--depot` sert seulement à tester une autre copie (un worktree d'une autre branche, par exemple). Ne jamais faire de checkout ni de stash dans la copie de travail de quelqu'un d'autre.
- `bridge/pipeline_example.py` est un exemple minimal en boucle fermée, à copier pour brancher un autre pipeline.
- Simulateur vers chaîne, environ 10 images/s : `[uint32 LE taille du JSON][JSON UTF-8][JPEG]`. Le JSON donne les intrinsèques de la caméra, sa pose, l'état du drone, la vérité terrain (boîtes en pixels, distance, relèvement, navire caché par la courbure ou le relief), l'AIS de tous les navires et l'environnement (soleil, vent, houle, nuages, brume, buée).
- Chaîne vers simulateur, messages JSON : `heading`, `cmd`, `goto`, `approach`, `stop`, `route` (nouvelle route du drone), `mission` (reprise de la route), `alert`, `detections`. Les formats exacts sont dans le README.
- Une fois branchée, la caméra passe en 2028×1520, le mode par défaut de l'IMX500, et les boîtes de la chaîne s'affichent en bleu (la vérité terrain reste en doré).
- Les journaux vont dans `bridge/runs/` (ignoré par git) ; `bridge/runs/apercu.jpg` montre la dernière image vue par la chaîne.

Toute évolution du protocole se fait des deux côtés à la fois : `src/bridge/Bridge.js` et `frameMeta` dans `src/main.js`, les deux scripts de `bridge/`, et le README.

## Plan du code

| Fichier | Rôle |
|---|---|
| `src/main.js` | application : boucle de rendu, réglages et préréglages météo, clavier, paramètres d'URL, téléportation, métadonnées envoyées à la chaîne |
| `src/ocean/` | mer spectrale de Tessendorf calculée sur GPU (`OceanFFT`, `spectrum`), rendu de la surface (`OceanSurface`), lecture des vagues côté CPU pour faire flotter les coques (`OceanSampler`) |
| `src/sky/` | atmosphère physique, nuages volumétriques, position du soleil à Brest |
| `src/terrain/Terrain.js` | relief et orthophotos de l'IGN, profondeurs, rendu de la côte |
| `src/ships/` | trafic et chenaux (`Traffic`), tenue à la mer (`Vessel`), coques procédurales et modèles 3D (`ShipFactory`, `hull`, `shipMaterial`) |
| `src/usv/USV.js` | le drone : catamaran de 0,92 m, modèle de manœuvre, mât de la caméra |
| `src/post/CameraFX.js` | modèle de caméra : exposition, halo, distorsion, aberration chromatique, bruit, gouttes et buée sur l'objectif |
| `src/fx/` | pluie qui tombe et impacts sur la mer (`Rain`), gouttes projetées sur le dôme (`LensDrops`), sillages (`Wake`) |
| `src/sim/GroundTruth.js` | boîtes de vérité terrain, avec masquage par le relief et la courbure de la Terre |
| `src/bridge/Bridge.js` | client WebSocket, envoi des images, réception des commandes |
| `src/ui/` | interface (`HUD`), carte plein écran et mini-carte (`MapView`), styles |
| `public/data/` | relief (`dem_*.bin`, Int16 en décimètres), orthophotos, noms de lieux, métadonnées (`terrain.json`) : produits par `tools/` |
| `public/models/` | modèles 3D des navires, `models.json` (échelle, ligne de flottaison), `ATTRIBUTION.md` (licences) |
| `tools/` | chaîne de données : `fetch.py` (téléchargements), `build.py` (relief et images), `places.py`, `labels.py` (noms), `preview.py` (contrôle visuel) ; `geo.py` fixe le repère et les emprises |

Repère : origine à 48,345° N, 4,56° O. Repère local en mètres, x vers l'est et n vers le nord ; dans la scène three.js, x est, y haut, z = -n (sud). Les caps sont en degrés depuis le nord, sens horaire.

## Modifier le simulateur

- Après chaque changement visible, ouvrir le simulateur, regarder le résultat (capture) et la console du navigateur (aucune erreur), puis `npm run build`.
- Budget : rester au-dessus d'environ 42 images/s sur un portable récent. Pas d'allocation dans la boucle de rendu ; une fonction coûteuse doit pouvoir se couper dans les réglages.
- Ne pas retoucher `public/data/` à la main : modifier `tools/` puis régénérer (commande dans le README). Le dépôt ne versionne pas les fichiers lourds ; `public/data/` et `public/models/` sont une exception voulue, pour que le simulateur se lance sans téléchargement. Ne pas ajouter d'autre fichier lourd sans l'accord de l'équipe.
- Un nouveau modèle 3D doit avoir une licence libre (CC BY ou CC0) : ajouter son entrée dans `models.json` et son crédit dans `ATTRIBUTION.md`.
- Tenir à jour la section « Limites connues » du README : ce qui n'est pas réaliste doit y être écrit.
- Les textes de l'interface sont en français et courts.

Pièges déjà rencontrés :

- Les traînées de pluie sont des quads tournés vers l'axe de chute : sans `side: THREE.DoubleSide`, la moitié est éliminée par le back-face culling et la pluie disparaît.
- Une capture prise pendant que l'onglet est caché peut montrer une image ancienne : afficher l'onglet avant de juger un rendu.
- La ligne 0 des orthophotos est le bord nord.
- En vue libre, `C` ouvre la carte : la descente est sur `X`.

## Dépôt et équipe

- Le travail sur le simulateur se fait sur une branche `ia/…`, puis une pull request vers `main` relue par un autre membre (voir `docs/guides/git.md`). Messages de commit en français ; les évolutions importantes vont dans `docs/CHANGELOG.md`.
- Le client (Cerema) et le tuteur école lisent le dépôt : tout ce qui est poussé doit pouvoir être lu par eux. Ne jamais les assigner ni les mentionner.
- Ne pas versionner `node_modules/`, `dist/`, `tools/cache/`, `bridge/.venv/` ni `bridge/runs/` (déjà dans `.gitignore`).
