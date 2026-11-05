# Comptes rendus

Tous les comptes rendus sont ici, **en PDF**. Les fichiers de travail (textes, sources LaTeX, modèles) sont rangés à part dans [sources/](sources).

> **Dernier en date : [point de séance du 05/11/2026](2026-11-05_point-de-seance.pdf)**

## Répartition des tâches en cours

| Sous-groupe | Qui fait quoi | PDF |
|---|---|---|
| **Plateforme** (lot L1) | Ewen : GPS et télémétrie · Rana : moteurs et ESC · Selma : ArduPilot et QGroundControl | [Répartition plateforme](2026-11-05_repartition-taches-plateforme.pdf) |
| **IA** (lot L2) | Guillaume : dégradation et caméra · Reda : hallucination et experts · Adam-Sabri : ré-identification | [Répartition IA](2026-11-05_repartition-taches-vision.pdf) |

## Tous les comptes rendus

Du plus récent au plus ancien.

| Date | Compte rendu | Ce qu'on y trouve |
|---|---|---|
| 05/11/2026 | [Point de fin de séance](2026-11-05_point-de-seance.pdf) | Où en est chaque sous-groupe, qui fait quoi, décision sur le GPS |
| 05/11/2026 | [Répartition des tâches plateforme](2026-11-05_repartition-taches-plateforme.pdf) | Dernière tentative sur le GPS, moteurs et ESC, ArduPilot et QGroundControl |
| 05/11/2026 | [Répartition des tâches IA](2026-11-05_repartition-taches-vision.pdf) | Priorités du lot vision, cadrage avec le client, vision nocturne, mode d'emploi |
| 21/10/2026 | [Point d'étape GPS et vision embarquée](2026-10-21_point-etape-gps-vision.pdf) | Diagnostic du GPS Neo M8P, démo de la vision, base de données et SSD |

## Comment on fonctionne

Depuis l'[atelier 6 de co-développement](../plan_actions_USV-IA.pdf) du 05/11/2026 :

- **8h30**, point de début à six : ce qui a été fait depuis la dernière séance, ce qui bloque ;
- **11h40**, point de fin à six : qui fait quoi pour la séance suivante ;
- après chaque séance, le point de fin est résumé ici, en PDF (action A8) ;
- les tâches vivent sur le tableau GitHub du dépôt (une tâche = une issue).

## Écrire un compte rendu

1. Dans [sources/](sources), copier le `.tex` du compte rendu précédent du même genre (même mise en page, grâce au style commun `style_cr.sty`). Les modèles `.md` servent à préparer le texte.
2. Le nommer `AAAA-MM-JJ_objet.tex`, par exemple `2026-11-12_point-de-seance.tex`.
3. Compiler depuis `sources/` avec `tectonic -o .. AAAA-MM-JJ_objet.tex` : le PDF arrive directement dans ce dossier.
4. Ajouter sa ligne en haut des tableaux ci-dessus et mettre à jour « Dernier en date ».
