# Point de séance du 05/11/2026

Point de fin de séance avec toute l'équipe, comme prévu par le [plan d'actions](../../docs/plan_actions_USV-IA.pdf) (action A8) : chaque sous-groupe dit où il en est et ce que chacun prend pour la séance suivante.

| | |
|---|---|
| **Date** | jeudi 5 novembre 2026 |
| **Participants** | les deux sous-groupes : plateforme (lot L1) et IA (lot L2) |
| **Rédacteur** | Reda El Mekkaoui, d'après la transcription automatique |
| **Prochain point** | début de la prochaine séance, à 8h30 |

## En bref

- **Plateforme** : on garde le GPS. Une dernière tentative avec le module actuel, branché sur le port GPS1 ; s'il ne marche pas, on change de module. En parallèle : télémétrie, branchement des moteurs et des ESC, prise en main d'ArduPilot et de QGroundControl.
- **IA** : la chaîne marche à peu près de bout en bout depuis la démonstration du lundi 02/11. Restent les tests de dégradation, les tests d'hallucination et la ré-identification.
- **Ensuite** : la plateforme fera un point commun pour que tous comprennent le contrôleur de vol et le pilotage des moteurs. L'IA passera à la vision nocturne, puis au mode d'emploi.

## Qui fait quoi pour la prochaine séance

### Plateforme (lot L1)

| Qui | Tâche | Détail |
|---|---|---|
| **Ewen** | GPS : dernière tentative | Trouver un câble JST-GH 10 broches, modifier certaines broches et brancher le GPS sur le port GPS1. S'il ne marche toujours pas, on change de module. Peu de temps à y passer. |
| **Ewen** | Télémétrie | La liaison marche, mais pour l'instant comme un simple câble. Analyser ce qui passe entre les modules et ce qu'on peut réellement en tirer. |
| **Rana** | Branchement des moteurs et des ESC | Se documenter sur la façon de relier tous les composants, en tenant compte maintenant du moteur. |
| **Selma** | ArduPilot et QGroundControl | Étudier les paramètres depuis QGroundControl et la programmation d'une mission. Pas encore essayé, car il faut d'abord les branchements : à avancer dès la prochaine séance. |

### IA (lot L2)

Détail et priorités dans la [répartition des tâches IA du même jour](../2026-11-05_repartition-taches-vision.pdf).

| Qui | Tâche | Détail |
|---|---|---|
| **Guillaume** | Tests de dégradation d'image | Gouttes d'eau, pixels noirs aléatoires. Une séance maximum. |
| **Guillaume** | Tests caméra | À continuer. |
| **Reda** | Tests d'hallucination | Vérifier que le système n'envoie pas d'alerte quand il n'y a aucun bateau. |
| **Reda** | Améliorer l'existant | En particulier les experts. |
| **Reda** | Petite boîte compacte | La fabriquer. |
| **Adam-Sabri** | Ré-identification | Savoir si un bateau a déjà été vu. Rechercher comment faire. |
| *à confirmer* | Retester le modèle | « Base 4 » dans la transcription. Si besoin, ajouter à la base des images avec d'autres caractéristiques. |

## Fait depuis la dernière séance

- **IA** : démonstration du lundi 02/11 avec la vraie caméra. La chaîne (détection, experts, alerte) marche à peu près de bout en bout.
- **IA** : nouvelle [répartition des tâches](../2026-11-05_repartition-taches-vision.pdf).
- **Plateforme** : un module GPS prêté par un autre groupe a fonctionné. On ne peut pas le garder, mais on a vu comment le GPS doit se comporter.
- **Plateforme** : la liaison de télémétrie fonctionne.
- **Équipe** : [plan d'actions](../../docs/plan_actions_USV-IA.pdf) de l'atelier 6 adopté (horaires, points de séance, tableau des tâches).

## Décisions

- **GPS** : on continue avec un GPS, comme le souhaite Antoine Douchin (Cerema). Une seule tentative de plus avec le module actuel, puis on en change plutôt que d'y passer plus de temps. Point encore à voir avec les tuteurs.
- **IA** : priorité à une vision et des alertes fiables. La vision nocturne et le mode d'emploi viendront après.

## Pour la suite

- **Plateforme** : quand chacun aura fini sa tâche, faire un point commun. Tout le monde doit comprendre comment fonctionne le contrôleur de vol, comment piloter les moteurs et quels retours on reçoit sur l'ordinateur.
- **IA** : la caméra de vision nocturne n'a pas encore été utilisée. On s'y mettra une fois le reste fini, puis on rédigera le mode d'emploi.

## Suivi du plan d'actions

| Indicateur | Ce jour |
|---|---|
| Tableau des tâches GitHub (A1) | Pas encore créé. Prévu avant la prochaine séance (Reda, Ewen). En attendant, les tâches sont listées ici. |
| Point de fin de séance (A7) | Fait : c'est ce compte rendu. |
| Retards à l'arrivée ou après la pause (A10) | Non relevés. |

---

*Rédigé à partir d'une transcription automatique. Corrections : « Eoen » → Ewen, « Ranel » → Rana, « l'Artois pilote » → ArduPilot, « GST, GH » → JST-GH. La transcription disait « sans GPS » : il faut lire « avec GPS ». Une erreur ? Dites-le, on corrige.*
