# Iroise, simulateur maritime du Goulet de Brest

Simulateur temps réel dans le navigateur (Three.js, WebGL 2) pour tester de bout en bout la chaîne de perception et de décision du micro drone de surface du projet Cerema x IMT Atlantique (USV-IA) : la caméra du drone filme la mer au ras de l'eau, les navires passent, le pipeline détecte, lance l'alerte et s'approche.

La scène est la vraie géographie du Goulet et de la rade de Brest, de la pointe Saint-Mathieu au Moulin Blanc : relief LiDAR HD de l'IGN (bâtiments et arbres compris), orthophotos, bathymétrie EMODnet et chenaux d'accès vérifiés en profondeur.

## Lancer

Il faut Node.js 20.19 ou plus récent (`node --version`). Depuis la racine du dépôt :

```bash
cd ia/simulateur
npm install
npm run dev
```

Puis ouvrir http://127.0.0.1:5173 dans Chrome, Edge ou Safari (WebGL 2). Le chargement prend quelques secondes (35 Mo de relief et d’images). Le simulateur tourne sur un portable récent ; sur une machine plus faible, la résolution baisse toute seule.

Pour les agents de code (Claude Code, Codex, Cursor…) : [AGENTS.md](AGENTS.md) explique comment lancer, tester et modifier le simulateur.

## Commandes

| Touche | Action |
|---|---|
| `M` ou bouton « Prendre la main » | l'opérateur prend la main / la rend au pilote automatique |
| `Z` `S` (ou `W` `S`, flèches) | gaz avant / arrière (prend la main automatiquement) |
| `Q` `D` (ou `A` `D`, flèches) | cap à bâbord / tribord (poussée différentielle) |
| `Espace` | stopper (maintien du cap, vitesse nulle) |
| `C`, bouton carte ou clic sur la mini-carte | carte satellite : chercher un lieu, téléporter le drone, ajouter des navires |
| `1` `2` `3` | caméra embarquée, vue poursuite, vue libre |
| glisser la souris | orienter la caméra (tourelle, orbite ou vue libre) |
| double-clic | recentrer la tourelle |
| `B` | boîtes de vérité terrain |
| `H` | masquer l'interface (image caméra seule) |
| `P` | capture PNG |
| `F` | plein écran |

En vue libre : `Z` `Q` `S` `D` pour se déplacer, `E` / `X` pour monter et descendre, `Maj` pour accélérer.

Manette (Xbox, PlayStation, 8BitDo...) : stick gauche vertical pour les gaz, stick droit (ou gauche) horizontal pour le cap, gâchettes pour avancer et reculer, `A` / croix pour prendre ou rendre la main, `B` / rond pour stopper, `Y` / triangle pour changer de vue. Toucher un stick prend la main.

Dans la liste « Cibles AIS », un clic sur un navire lance l'approche automatique (maintien à 60 m). Le panneau Réglages règle l'heure, le mois, la météo (Clair, Nuageux, Couvert, Brume, Coup de vent, Couchant), le vent, la houle, les nuages, la brume, la marée, la densité du trafic, le champ de vision, l'exposition, la stabilisation de la caméra, et une démo autonome qui détecte puis approche toute seule.

### La carte

`C` ouvre une carte plein écran sur l'orthophoto de l'IGN, avec les noms de lieux (communes, lieux-dits comme Le Dellec ou Le Minou, pointes, plages, ports, phares, forts, IMT Atlantique, plans d'eau). Les noms apparaissent selon le zoom.

- **Chercher un lieu** : le champ en haut à droite centre la carte sur le lieu ; « Y aller » y téléporte le drone (au point d'eau le plus proche).
- **Téléporter le drone** : clic sur l'eau. Garder le clic et glisser choisit son cap. Un clic sur la terre place le drone au point d'eau le plus proche. La carte se referme pour montrer la nouvelle vue.
- **Ajouter un navire** : choisir le type (chalutier, voilier, vedette, remorqueur, passagers, porte-conteneurs, vraquier, frégate) et la vitesse (0 pour un navire à l'arrêt), puis cliquer sur l'eau ; glisser pour le cap. Un navire posé en eau trop peu profonde pour son tirant d'eau est déplacé vers l'eau libre.
- **Fiche d'un navire** (clic dessus) : vitesse et cap modifiables, « Tracer une route » (clics successifs, Entrée ou double-clic pour finir, « Boucle » pour qu'il la répète), « Approcher avec le drone », « Supprimer » (ou touche Suppr). Glisser un navire le déplace.
- Les navires ajoutés gardent leur cap ou suivent leur route et s'arrêtent avant la côte ; le trafic automatique ne les retire jamais. On peut couper le trafic automatique ou le retirer d'un coup pour monter un scénario de test précis. Ils apparaissent dans l'AIS envoyé à la chaîne IA comme les autres.
- Clic droit : téléporter ici, poser un navire ici, centrer ici.

Tant que la carte est ouverte, la simulation continue mais la vue 3D n'est pas dessinée (sauf si la chaîne IA est branchée et attend des images).

### Mission et scénarios

- **Route du drone** : dans la carte, outil « Route du drone », puis un clic par point de passage, Entrée ou double-clic pour la lancer. Le drone la suit en boucle à 3 nœuds (5 nœuds au plus), comme une mission ArduPilot. Quand la chaîne IA décide une approche, elle prend la main ; à la fin de l'approche, le drone reprend sa route. « Prendre la main » puis la rendre fait de même.
- **Scénario rejouable** : `?scenario=nom` charge `public/scenarios/nom.json` (météo, heure, position et route du drone, navires avec type, cap, vitesse et route, trafic automatique coupé ou non). Le même fichier sert pour la démo et pour les essais en série.
- **Démo pour le tuteur** : `?scenario=demo-tuteur&bridge=1`. Le drone patrouille devant Le Dellec, un chalutier croise sa route à 220 m ; la chaîne le détecte, s'approche, lit la plaque, envoie l'alerte complète à la station sol, puis le drone repart.

### Paramètres d'URL

`?scenario=demo-tuteur`, `?weather=Couchant`, `?hour=20.5&month=6`, `?view=chase`, `?ui=0` (image seule), `?gt=1` (boîtes), `?bridge=1` (connexion au pipeline), `?demo=1`, `?fov=60`, `?pan=40` (tourelle en degrés), `?hdg=90&speed=3`, `?x=..&z=..` (position en mètres locaux), `?ships=0`, `?map=1` (ouvrir sur la carte), `?dpr=1` (résolution fixe au lieu de la résolution dynamique).

## Brancher la chaîne IA du projet

`bridge/chaine_cerema.py` fait tourner la chaîne telle qu'elle est dans le dépôt, sur les images du simulateur, sans la modifier :

- détection et suivi : ceux de `ia/suivi`, comme sur le Pi. Par défaut `best4_2`, le modèle de Guillaume, avec ses réglages : détection sûre à 55 %, experts lancés après 5 détections sûres d'affilée. `--detecteur yolo11n` pour le modèle COCO qui tourne aujourd'hui sur l'IMX500. Dans le simulateur, `best4_2` voit encore des navires (60 à 77 %) sur les crêtes de vagues au bord de l'image, assez longtemps pour déclencher des approches : à mesurer sur le banc ;
- suivi : `ia/suivi` (associateur, numéros de pistes), contrat 1 ;
- décision et experts : `ia/chaine` (filtre qualité, type DINOv2, OCR, approche, garde-fous), contrat 3.

Trois terminaux, depuis la racine du dépôt, avec le Python de la chaîne (installation dans `ia/chaine/README.md`, plus `pip install websockets`) :

```bash
cd ia/simulateur && npm run dev                                                  # 1. le simulateur
cd station_sol && python3 serveur.py                                             # 2. la station sol, http://localhost:8000
.venv/bin/python ia/simulateur/bridge/chaine_cerema.py --station http://localhost:8000   # 3. la chaîne
```

Après une modification de la chaîne, il suffit d'arrêter (Ctrl+C) et de relancer la commande 3 : le simulateur se reconnecte tout seul. `--depot` permet de tester la chaîne d'une autre copie du dépôt (un worktree d'une autre branche). Puis ouvrir le simulateur avec `/?bridge=1` (ou l'icône « lien »). Si `websockets` manque dans le Python de la chaîne, le script le prend dans `bridge/.venv` (voir plus bas). Options : `--station http://localhost:8000` pour alimenter aussi la page de la station sol, `--detecteur yolo11n`, `--reseau-type dinov3`.

Quand la chaîne est branchée :

- elle ne reçoit que l'image de la caméra embarquée (vue `1`) : en vue poursuite ou libre, l'envoi est suspendu ;
- la caméra passe en 2028×1520, le mode par défaut de l'IMX500 dans `camera_pi.py` (bandes noires si la fenêtre n'a pas ce format, `?cam=` pour une autre taille) ;
- les seuils de la chaîne sont ramenés à cette taille d'image, comme sur le Pi ;
- les boîtes de la chaîne s'affichent en bleu avec le numéro de piste, le type et l'immatriculation lue ; la vérité terrain du simulateur (touche `B`) reste en doré ;
- les alertes de la chaîne apparaissent dans le HUD, et quand elle décide une approche, elle pilote le drone vers le relèvement de la boîte. L'opérateur qui prend la main passe avant elle ;
- les chalutiers portent une immatriculation française peinte sur l'avant (par exemple « GV 978805 »), lisible par l'expert OCR ;
- pendant une approche, la chaîne reçoit la distance réelle au navire, mesurée dans le simulateur comme le ferait un AIS ou un télémètre ; à la fin de l'approche, le drone reprend sa route ;
- journal des décisions et messages dans `bridge/runs/`, et `bridge/runs/apercu.jpg` montre la dernière image vue avec les boîtes de la chaîne.

## Brancher votre pipeline

Le simulateur est client WebSocket de `ws://127.0.0.1:8765` (modifiable avec `?ws=`). Un exemple complet est fourni (depuis `ia/simulateur`) :

```bash
python3 -m venv bridge/.venv
bridge/.venv/bin/pip install -r bridge/requirements.txt
bridge/.venv/bin/python bridge/pipeline_example.py
```

Ensuite, cliquer sur l'icône « lien » du HUD, ou ouvrir `/?bridge=1`. L'exemple tourne en boucle fermée : détection (vérité terrain bruitée par défaut, ou `--yolo yolov8n.pt` pour un vrai réseau), confirmation sur 3 images, alerte, approche au relèvement, maintien à distance. Ses détections s'affichent en bleu dans le HUD, la vérité terrain en doré.

### Simulateur vers pipeline (binaire, ~10 images/s)

`[uint32 LE taille du JSON][JSON UTF-8][JPEG]`. Le JSON contient :

- `width`, `height`, `intrinsics` (`fx`, `fy`, `cx`, `cy`, `radial_k` : la distorsion en barillet appliquée à l'image) ;
- `camera` : position, quaternion (repère three.js : x est, y haut, z sud), FOV, vue ;
- `own` : lat, lon, cap, vitesse, mode du pilote ;
- `ground_truth` : une entrée par navire visible, avec `bbox` en pixels de l'image envoyée (distorsion comprise), classe, distance, relèvement, lat/lon, cap, vitesse, et les indicateurs `truncated` et `hullDown` (coque cachée par la courbure de la Terre). La visibilité tient compte du relief (un navire derrière une pointe n'est pas listé) ;
- `ais` : tous les navires simulés (MMSI, nom, type, position, cap, vitesse, longueur) ;
- `env` : hauteur du soleil, vent, Hs, nuages, brume.

### Pipeline vers simulateur (texte JSON)

| Message | Effet |
|---|---|
| `{"type":"heading","heading_deg":250,"speed_mps":3}` | pilote : cap et vitesse |
| `{"type":"cmd","throttle":0.6,"rudder":-0.2}` | commande directe (gaz -0.4..1, barre -1..1) |
| `{"type":"goto","lat":48.34,"lon":-4.58,"speed_mps":4}` | ralliement d'un point |
| `{"type":"approach","target_id":12,"standoff_m":60}` | approche d'un navire (id ou `mmsi`) |
| `{"type":"stop"}` | arrêt |
| `{"type":"route","points":[{"lat":48.346,"lon":-4.577}],"loop":true,"speed_mps":1.5}` | nouvelle route du drone, suivie en boucle |
| `{"type":"mission"}` | reprise de la route (fin d'approche) |
| `{"type":"alert","text":"Navire détecté","detail":"..."}` | bandeau d'alerte dans le HUD |
| `{"type":"detections","boxes":[{"bbox":[x0,y0,x1,y1],"label":"bateau","score":0.8}]}` | affichage des détections |

## Ce qui est simulé, et comment

- **Mer** : océan spectral de Tessendorf, 3 cascades FFT 256² calculées sur GPU (spectre JONSWAP de mer du vent selon le vent et le fetch, plus une houle d'ouest), vagues déferlantes par le jacobien, écume persistante, sillages et écume de côte selon la profondeur réelle. Éclairage de Bruneton (reflet du soleil sur une distribution de pentes), Fresnel, diffusion sous la surface sur les crêtes, vaguelettes capillaires près de l'USV.
- **Ciel** : atmosphère physique de Hillaire (diffusion Rayleigh et Mie, ozone, diffusion multiple), cumulus volumétriques avec ombres portées sur la mer et sur la côte, cirrus, brume marine, perspective aérienne cohérente avec le ciel. Position du soleil calculée pour Brest à la date et à l'heure choisies.
- **Côte** : relief LiDAR HD à 4 m du Goulet jusqu'à Brest (Penfeld, port de commerce, Moulin Blanc, côte ouest de Plougastel) et à 15 m au-delà, orthophotos à 2,5 m et 8 m, falaises de granite et estran sombre procéduraux là où l'orthophoto s'étire, courbure de la Terre (les navires lointains passent sous l'horizon).
- **Navires** : 9 modèles 3D réalistes (chalutier côtier, chalutier hauturier, voilier, semi-rigide de sauvetage, vedette, cargo, porte-conteneurs, remorqueur, navette à passagers), sous licence CC BY 4.0 et crédités dans `public/models/ATTRIBUTION.md`. Ils sont mis à l'échelle et posés à leur ligne de flottaison automatiquement (`public/models/models.json`). La frégate et une partie de la flotte restent procédurales : coques profilées, peintures usées, noms sur la coque. Feux de navigation au crépuscule. Chaque coque flotte sur les vagues simulées (pilonnement, tangage, roulis amortis selon sa taille). Les navires de commerce et la Marine suivent les chenaux réels vers le port de commerce et la Penfeld, les autres naviguent dans l'eau libre en évitant la côte.
- **Le drone** : micro catamaran de 0,92 m (deux flotteurs, caisson électronique, deux propulseurs en différentiel), vitesse maximale 5 nœuds (2,6 m/s). Il épouse chaque vague. La caméra (champ vertical 50°, proche d'une IMX500) est sur un petit mât à environ 45 cm au-dessus de l'eau : les crêtes masquent l'horizon par moments, comme en vrai.
- **Pluie** : préréglages « Pluie » et « Grain », ou réglage libre. Gouttes qui tombent en traînées poussées par le vent (floues et larges tout près de l'objectif, fines au loin, vues surtout sur le ciel puisque la caméra est à 45 cm de l'eau), impacts en anneaux sur la mer, visibilité réduite, base des nuages plus sombre, côte mouillée. Sur le dôme de la caméra : des centaines de gouttes floues qui déforment l'image, d'autres qui coulent en laissant une trace, et un film d'eau entre elles.
- **Buée** : réglage « Buée sur l'objectif » (mis automatiquement à 30 % sous la pluie, 50 % dans le grain, 35 % dans la brume). Voile laiteux et flou irrégulier, plus fort vers les bords ; les gouttes qui coulent dégagent leur trace.
- **Caméra** : non stabilisée par défaut, exposition automatique, halo, distorsion en barillet, aberration chromatique, vignettage, réponse film AgX, bruit de capteur. Gouttes sur le dôme quand une vague touche l'avant du drone, film d'eau quand elle le recouvre (désactivable, ou `?drops=0`), utile pour les tests de robustesse aux gouttes.
- **Performances** : le code fait 190 Ko compressé, sans moteur à installer. La résolution s'adapte en continu pour rester au-dessus de ~42 images/s. Mesuré sur MacBook Air M4 avec toute la scène et les modèles 3D : environ 12 ms de calcul par image en 1075×1053 et 12 à 13 ms en 2,2 Mpx (temps GPU synchronisé). Forcer une définition avec `?dpr=`.

## Données et licences

Les fichiers de `public/data/` (34 Mo) et `public/models/` (49 Mo) sont versionnés pour que le simulateur se lance sans téléchargement, en exception à la règle `data/` du `.gitignore` de la racine. Ils sont générés par les scripts de `tools/` (Python avec numpy, scipy, pillow et requests ; environ 860 Mo de téléchargements mis en cache dans `tools/cache/`, ignoré par git) :

```bash
python3 tools/fetch.py && python3 tools/build.py && python3 tools/places.py && python3 tools/labels.py && python3 tools/preview.py
```

- IGN, Géoplateforme : LiDAR HD MNS, RGE ALTI, orthophotos, Plan IGN v2, géocodage (noms de la carte, `public/data/labels.json` ; les plans d'eau et quatre ports sont placés à la main). Licence Ouverte Etalab 2.0.
- EMODnet Bathymetry (DTM 2024) : CC BY 4.0, ne pas utiliser pour la navigation.
- Modèles 3D de navires : CC BY 4.0, auteurs et liens dans `public/models/ATTRIBUTION.md` (modèles Sketchfab récupérés via le miroir public Objaverse). Pour rester sur les modèles procéduraux : `?models=0`.

## Limites connues

- Pas de modèle de frégate libre et propre (les plus beaux sont extraits d'un jeu vidéo) : la frégate reste procédurale. La navette est un ferry de Hong Kong (livrée verte), le voilier a un mât un peu court.
- Les profondeurs des bassins portuaires sont trop faibles (cellules EMODnet de 115 m) et la Roche Mengant n'apparaît pas dans le relief. Les chenaux sont illustratifs, pas validés sur carte SHOM.
- Les sites militaires sont masqués par l'IGN : leurs bâtiments manquent.
- Pas de nuit éclairée (les feux des navires s'allument au crépuscule, mais la côte reste noire), pas de vagues de sillage de Kelvin modélisées (seulement l'écume et la traînée lisse).
- Le modèle de manœuvre du drone est simple (cavalement et lacet du premier ordre), et ses dimensions sont une hypothèse (moins d'un mètre, d'après le sujet 2025) : à ajuster quand la coque sera figée.
- Le trafic et l'AIS sont simulés, pas réels. Un flux AIS réel (par exemple aisstream.io, clé gratuite à créer) pourrait placer les vrais navires du moment dans la scène.
