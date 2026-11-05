---
name: compte-rendu-reunion
description: Transformer une transcription de réunion du projet 20 Cerema (USV-IA) en compte rendu PDF propre, daté, rangé dans comptes_rendus/ et poussé sur GitHub pour l'équipe. À utiliser dès que Reda colle une transcription (« Speaker 1 / Speaker 2 », « You: », résumé automatique), parle de point de séance, de réunion d'équipe, avec le Cerema ou les tuteurs, de répartition des tâches, de compte rendu, de « trace écrite », ou demande de « faire le document et le push ». Contient le format validé, le rangement du dossier, les noms de l'équipe, les pièges des transcriptions et les bonnes pratiques retenues.
---

# Compte rendu de réunion (projet 20 Cerema, USV-IA)

Fixé avec Reda le 05/11/2026. Il colle une transcription ; je produis le compte rendu en **PDF**, je le range, je le date, je mets à jour le sommaire, je pousse sur `main` et je lui donne le lien. Il ne veut pas avoir à me réexpliquer tout ça.

**Les camarades lisent des PDF, pas des `.md`.** Tout ce qui est fait pour les humains est un PDF à la racine de `comptes_rendus/` ; les fichiers de travail vont dans `comptes_rendus/sources/`.

Pour le reste du projet (Git, LaTeX, Pi, équipe en détail), voir le skill `projet-cerema`.

## Où sont les choses

- Dépôt d'équipe : `~/Desktop/imt/cerema/cerema-usv-ia`, GitHub `Redaelm47/cerema-usv-ia` (privé). Y ont accès : les six membres et Matthieu Arzel (`marzelbr`).
- `comptes_rendus/` : **seulement** les PDF, le `README.md` (sommaire, affiché par GitHub sous la liste) et `sources/`.
- `comptes_rendus/sources/` : un `.tex` par compte rendu, `style_cr.sty` (style commun : couleurs, en-tête, cartes `personne`, tableaux), les versions texte `.md` anciennes, les modèles `modele_point_de_seance.md` et `modele_compte_rendu.md`.
- `docs/plan_actions_USV-IA.pdf` : plan d'actions de l'atelier 6 (05/11/2026). Il impose un point à six à 8h30 et à 11h40, et un compte rendu du point de fin après chaque séance (action A8, Reda).

## Étapes

1. **Lire toute la transcription.** Repérer le type de réunion (point de séance à six, réunion d'un sous-groupe, réunion avec le client, réunion avec le tuteur), la date, qui parle de quoi.
2. **Dater.** La date de la réunion, pas celle de l'écriture. Sans indication, prendre la date du jour et le dire à Reda. Vérifier le jour de la semaine par calcul (`date -j -f %Y-%m-%d 2026-11-02 +%A`), ne pas le deviner.
3. **Attribuer chaque tâche à une personne nommée.** Les transcriptions mélangent les voix (voir plus bas). Ce que je ne peux pas déduire de façon sûre : une seule série de questions groupées à Reda (`AskUserQuestion`, 4 questions max). S'il ne sait pas, la tâche va dans le PDF avec « responsable à confirmer », jamais sous un nom deviné.
4. **Reprendre le compte rendu précédent** (via le sommaire) : l'état de ses actions (fait, en cours, en retard, abandonné) ouvre le nouveau.
5. **Écrire le `.tex` dans `sources/`** en copiant le compte rendu précédent du même genre (il utilise `\usepackage{style_cr}`). Formats ci-dessous.
6. **Compiler et regarder** : `cd comptes_rendus/sources && tectonic -o .. <nom>.tex`, puis `pdftoppm -r 70 -png ../<nom>.pdf <scratchpad>/apercu` et lire les images. Corriger : titre seul en bas de page (`\needspace`), note de bas de page seule sur une page, texte qui déborde d'un cadre, étiquettes de schéma qui chevauchent. Répartition d'un sous-groupe : 1 page. Point de séance : 2 pages au plus.
7. **Mettre à jour le sommaire** `comptes_rendus/README.md` : « Dernier en date », le tableau « Répartition des tâches en cours » si elle change, une ligne en haut de « Tous les comptes rendus ». Ajouter une entrée datée dans `CHANGELOG.md`. Vérifier que les liens relatifs existent.
8. **Pousser** depuis un worktree de `main` (voir « Git » plus bas), `git fetch` juste avant.
9. **Répondre à Reda en quelques lignes** : lien GitHub du PDF, puis ce qu'il doit vérifier (attributions incertaines, date supposée, ce qui a été adouci). S'il veut voir : `open "<url GitHub>"`.

## Nommage

`AAAA-MM-JJ_objet.pdf`, la source `sources/AAAA-MM-JJ_objet.tex` porte le même nom. Objets en usage :

| Réunion | Fichier(s) |
|---|---|
| Point de fin de séance à six | `point-de-seance` |
| Répartition des tâches d'un sous-groupe | `repartition-taches-plateforme`, `repartition-taches-vision` (un PDF par sous-groupe, chacun visible dans le sommaire) |
| Réunion avec le client (Antoine Douchin) | `reunion-cerema` |
| Réunion avec le tuteur école | `reunion-tuteur` |
| Point d'étape sur un sujet | `point-etape-<sujet>` |

## Format d'un point de séance

En-tête (`\entete`) : surtitre `PROJET 20 CEREMA · POINT DE FIN DE SÉANCE À SIX · JJ/MM/AAAA`, titre « Point de séance du JJ/MM/AAAA », sous-titre, ligne « Participants · Rédacteur · Prochain point ».

1. **En bref** : trois puces au plus (plateforme, IA, ensuite).
2. **Suivi des actions précédentes** : tableau Action | Qui | État. À partir du deuxième point de séance.
3. **Qui fait quoi pour la prochaine séance** : un tableau par sous-groupe, colonnes Qui | Tâche | Détail (ajouter Échéance si elle a été dite). Une personne par ligne, jamais « l'équipe ». Tâche sans responsable : ligne en italique « à confirmer ».
4. **Fait depuis la dernière séance.**
5. **Décisions** : numérotées, formulées comme des décisions. Une opinion (« je pense que ça ne vaut pas le coup ») n'est pas une décision.
6. **Points ouverts et blocages** : ce qui n'est pas tranché, ce qui bloque, ce dont un sous-groupe a besoin de l'autre.
7. **Pour la suite.**
8. **Suivi du plan d'actions** : tableau d'indicateurs (A1 tableau GitHub, A4 tableau vérifié, A6 et A7 points tenus, A10 retards). « Non relevés » si la transcription n'en dit rien.

Pied de page (`\redige`) : « Rédigé par Reda El Mekkaoui d'après la transcription automatique », la liste des mots corrigés, « Une erreur ? Dites-le, on corrige. »

## Format d'une répartition de sous-groupe

Modèles : `sources/2026-11-05_repartition-taches-vision.tex` et `sources/2026-11-05_repartition-taches-plateforme.tex`. En-tête, En bref, frise « Ordre des étapes » (TikZ, 3 ou 4 étapes : maintenant, ensuite, plus tard, en dernier), « Qui fait quoi » en cartes `personne` (une couleur par personne, définies dans `style_cr.sty`), encadré `remarque` pour un responsable à confirmer, puis seulement les sections qui ont du contenu (cadrage, matériel, plus tard, décisions). Page 1 = les actions, page 2 éventuelle = le contexte.

## Format d'une réunion avec le client ou le tuteur

Modèle : `sources/2026-10-21_point-etape-gps-vision.tex`. Ordre du jour ou En bref, points abordés par volet (USV, IA), décisions, tableau Action | Responsable | Échéance, prochaine réunion.

## Règles d'écriture

- Français, phrases courtes et claires, pas de tiret cadratin.
- **Ne rien inventer.** Chaque information vient de la transcription, du dépôt ou de Reda. Pas de date, de lieu ou de chiffre ajouté pour faire joli.
- **Les corrections de Reda passent avant la transcription** (le 05/11 : « sans GPS » voulait dire « avec GPS » ; « moi » sur l'IA, c'est Reda).
- **Tact** : le dépôt est lu par Matthieu Arzel et peut l'être par le client. Reformuler les jugements sur des personnes (« idées absurdes » devient « certaines ne sont pas réalisables »). Jamais d'avis sur un camarade.
- Prénoms dans le corps du texte. Antoine Douchin et Matthieu Arzel en entier.

## Transcriptions : pièges connus

- « Speaker 1 / Speaker 2 » mélange plusieurs voix ; « You: » partout veut dire qu'il n'y a aucune séparation des voix. Les résumés automatiques attribuent des tâches à « Speaker N » : ne pas s'y fier.
- Attribuer par les indices : prénom cité (« Et Rana, sur le branchement ? »), « c'est moi qui ai fait » (l'auteur connu de la partie), rôle habituel (skill `projet-cerema`).

| Transcription | Correct |
|---|---|
| Eoen | Ewen |
| Ranel | Rana |
| Salma (orthographe de Reda) | Selma |
| l'Artois pilote | ArduPilot |
| ground control | QGroundControl |
| GST, GH | JST-GH (connecteur) |
| Olibro | Holybro |
| drawtech | Drotek |
| S9P, ZF9P | F9P |
| Zel, Ardel, Arzel | Matthieu Arzel (deux t) |
| Douchin | Antoine Douchin (Cerema) |
| base 4 | inconnu au 05/11 (peut-être un fichier de poids `best.pt`) : demander |

## Bonnes pratiques retenues (recherche du 05/11/2026)

- Toujours le même modèle : on retrouve l'information au même endroit.
- Séparer décisions, discussions et opinions ; marquer clairement ce qui reste ouvert.
- Chaque action : qui (une personne nommée), quoi (un verbe concret), quand. Sans responsable, ce n'est qu'un souhait.
- Reprendre au début de chaque compte rendu l'état des actions du précédent.
- Diffuser vite : le jour même, au plus tard sous 24 h.
- Un seul endroit, classé par date : le sommaire de `comptes_rendus/`.
- Suivre risques, blocages et dépendances entre sous-groupes (version légère d'un registre RAID).

Sources : [Fireflies](https://fireflies.ai/blog/tips-for-taking-meeting-minutes), [resolution.de](https://www.resolution.de/?p=77175), [Reflect](https://reflect.app/blog/perfect-meeting-minutes-template), [Wrike (fr)](https://www.wrike.com/fr/blog/modele-de-compte-rendu-de-reunion-guide-avec-exemples-et-points-daction/), [Slite (fr)](https://slite.com/fr/learn/proces-verbal-de-reunion), [UW CSE 403](https://courses.cs.washington.edu/courses/cse403/23au/project/index.html), [Asana, RAID log](https://asana.com/sv/resources/raid-log.md).

## Git

- La copie locale `cerema-usv-ia` est souvent sur une autre branche (`ia/chaine-squelette`) avec des modifications non commitées : **ne jamais y toucher**. Travailler dans un worktree de `main` :
  ```bash
  cd ~/Desktop/imt/cerema/cerema-usv-ia
  WT=<scratchpad>/wt-main
  git fetch -q origin && git worktree add -q "$WT" main && git -C "$WT" merge --ff-only -q origin/main
  # … écrire, compiler, git -C "$WT" add …, commit …
  git -C "$WT" fetch -q origin && git -C "$WT" merge --ff-only -q origin/main && git -C "$WT" push origin main
  git worktree remove "$WT" && git branch -f main origin/main
  ```
- Les comptes rendus vont directement sur `main` : c'est la pratique établie, et Reda le demande. Message de commit en français, qui dit ce qui change (`Compte rendu du 05/11 : …`).
- Compiler avant de pousser, toujours.

## Tableau GitHub des tâches (action A1, pas encore fait)

Le plan prévoit un tableau GitHub Projects lié au dépôt (colonnes À faire, En cours, Fait ; une étiquette par sous-groupe), une issue par tâche, assignée, avec échéance. Au 05/11/2026 il n'existe pas : le jeton `gh` n'a pas le droit `project` (Reda doit lancer `gh auth refresh -s project`). Créer des issues assignées envoie une notification aux personnes : demander l'accord de Reda la première fois. Une fois le tableau en place, mettre le numéro d'issue (`#12`) en face de chaque tâche du compte rendu.

Comptes GitHub : Reda `Redaelm47`, Guillaume `guillaumeleroy76`, Adam-Sabri `a04Hlaoua`, Ewen `ewengourmelen-gif`, Selma `selma876`, Rana probablement `ElNormando` (déduit par élimination, à confirmer avant d'assigner), Matthieu Arzel `marzelbr`.

## Erreurs déjà faites

- Livrer un `.md` à l'équipe : il faut un PDF.
- Ranger la répartition de la plateforme dans le point de séance seulement : chaque sous-groupe a son PDF, visible dans le sommaire.
- Se fier aux noms « Speaker N » du résumé automatique.
- Écrire « Mathieu » au lieu de « Matthieu ».
- Laisser un titre seul en bas de page ou la note de bas de page seule sur une page : toujours regarder les aperçus.
