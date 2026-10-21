# Compte rendu : point d'étape GPS Neo M8P et vision embarquée

- **Date :** 2026-10-21
- **Lieu / format :**
- **Présents :** intervenants 1, 2 et 3 (noms à compléter)
- **Rédacteur :** Reda El Mekkaoui (d'après la transcription automatique)

## Ordre du jour

1. Diagnostic du GPS Neo M8P, non reconnu par le Pixhawk
2. Méthode de travail et sécurité du matériel
3. Démo de la chaîne vision embarquée (détection, décideur, experts, dashboard) et ses limites
4. Base de données, API et évolutivité

## En bref

- Le GPS fixe sa position mais **ne parle pas au Pixhawk** : on reprend d'abord le câblage et les protocoles, la config ArduPilot ensuite.
- Plan B si le M8P n'est pas compatible : **module F9P**.
- La chaîne vision marche **en simulation**. Sur la vraie caméra, l'image est **floue**.
- Le JSON ne suffira pas : il faut une **base de données extensible et une API**, et un **SSD** à la place de la carte SD.

## Points abordés

### Volet USV : GPS Neo M8P et Pixhawk

**Constat**
- Le Neo M8P est alimenté et fixe sa position, mais la liaison avec le Pixhawk (port GPS2, `SERIAL4`) ne marche pas.
- On a déjà essayé d'inverser les broches, sans succès.

**Causes possibles** (selon l'intervenant 1)
- configuration de la puce u-blox ;
- RX/TX inversés ;
- baudrate ou port du Pixhawk mal configuré. Le port a peut-être été fermé ou reconfiguré l'an dernier (Mathieu Arzel l'a utilisé).

**À vérifier sur le brochage**
- Broches essentielles : masse, 5 V, TX/RX (UART), SCL/SDA (I2C).
- Voir si ArduPilot exige un GPS branché sur GPS1.

**À écarter :** faire passer le GPS par la Raspberry Pi. C'est le Pixhawk qui fait la fusion des capteurs, et la latence serait trop forte.

### Volet USV : méthode et sécurité du matériel

- **Comprendre et documenter tout le câblage** autour du Pixhawk, sur le schéma Holybro annoté, **avant** de configurer ArduPilot.
- Sources de référence : le site Holybro et la doc ArduPilot.
- **Batterie 4S (14,8 V)** : vérifier la polarité et les tensions au multimètre avant tout branchement. Ne pas alimenter le Pixhawk sur les sorties directes.
- On peut tester le GPS seul avec un **adaptateur USB-série et un script Python**, plus simplement qu'avec la Raspberry Pi.
- L'intervenant 1 n'est pas sur place la semaine prochaine. En cas de blocage, lui écrire par mail pour caler une visio ou un appel de 30 minutes.

### Volet IA : démo de la vision embarquée

**Architecture présentée**

```
caméra IMX500 (modèle léger, une image toutes les 2 s)
   → décideur
   → experts : OCR de l'immatriculation, mouvement, catégorie
   → alertes sur le dashboard
```

- Seuil de détection à 50 %, réglable.
- Filtre qualité : l'expert OCR n'est appelé que si l'image est assez nette.

**Démo en simulation**
- Bateau de pêche détecté, immatriculation lue, alerte sur le dashboard.
- Bateau lointain détecté, mais sans plaque lisible.

**Problèmes**
- Le modèle `base.pt` de l'an dernier ne détecte rien, alors que **YOLO11n détecte le bateau à 88 %**. Il a été fait par Kalid ; tout serait sur le Drive copié sur la clé USB.
- Caméra filmant un écran : **image totalement floue**.
- La Raspberry Pi 4 chauffe (52 °C relevés).

### Volet IA : base de données, API et évolutivité

- Le JSON ne suffira pas pour un bateau qui navigue 365 jours par an. Il faut une **base de données extensible** (SQL, NoSQL ou SQLite 3).
- Champs à prévoir : vitesse, image dégradée de chaque bateau, futurs capteurs (lidar, AIS).
- Prévoir des **experts en greffon**, dont la ré-identification d'un bateau revu plus tard. Mathieu Arzel pourrait aider.
- Le dashboard HTML (fait avec Claude) est jugé utile, mais il ne faut pas trop développer l'interface : **priorité à une API** entre la base et l'affichage.
- Une carte SD grillera avec des écritures répétées : **prévoir un SSD**.

## Décisions

- Priorité au matériel (câblage, protocoles) avant la configuration du firmware ArduPilot.
- Si le M8P ne peut pas fonctionner avec le Pixhawk, on passe sur un module **F9P**.
- Le GPS est branché **directement au Pixhawk**, pas via la Raspberry Pi.
- Le dashboard HTML actuel est conservé pour les tests.

## Actions

| Action | Responsable | Échéance |
|---|---|---|
| Vérifier la compatibilité du M8P Drotek avec le Pixhawk et son brochage, puis envoyer un mail | Intervenant 1 | 2026-10-21 (ce soir) |
| Chercher un adaptateur USB-série à l'atelier | Intervenant 1 | |
| Étudier le brochage et les protocoles GPS du Pixhawk 6C mini (Holybro, ArduPilot) | Intervenant 2 | |
| Interroger Mathieu Arzel sur la configuration du Pixhawk | Intervenant 2 | |
| Tester le système sur la vraie caméra en réglant le problème de flou | Intervenant 2 | |
| Trouver un boîtier Pi 4 avec ventilateur et un SSD | Intervenant 3 | |
| Concevoir une base de données extensible et une API reliant la base au dashboard | Équipe vision embarquée | |

## Prochaine réunion

- **Date :** à fixer. L'intervenant 1 étant absent la semaine prochaine, prévoir une visio de 30 minutes par mail en cas de blocage.

---

*Rédigé à partir d'une transcription automatique : orthographes corrigées (« Olibro » → Holybro, « drawtech » → Drotek, « S9P / ZF9P » → F9P, « Ardel » → Arzel). Les intervenants n'étaient pas nommés dans la transcription.*
