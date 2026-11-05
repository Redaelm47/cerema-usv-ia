---
name: projet-cerema
description: Conventions du projet 20 Cerema (USV-IA, IMT Atlantique) pour tout travail dans ~/Desktop/imt/cerema — équipe et rôles, où sont les fichiers, dépôt GitHub et Git (worktree, push), documents LaTeX (tectonic, style, Gantt), Overleaf partagé, Raspberry Pi et caméra IMX500, choix d'architecture déjà arrêtés, et manière de répondre à Reda. À lire avant d'écrire un document du projet, de pousser sur le dépôt, de toucher à l'Overleaf ou au Pi, ou quand Reda parle du projet Cerema, du drone, de la vision embarquée ou de ses camarades.
---

# Projet 20 Cerema : conventions de travail

Ce que Reda m'a déjà dit, pour ne pas avoir à le redire. Pour les comptes rendus de réunion, voir le skill `compte-rendu-reunion`.

## Le projet en bref

- Projet de commande entreprise (PCE 2A, sujet 20), IMT Atlantique × Cerema, 2026-2027. Il prend la suite du projet 2025 (groupe 11, « Micro drone de surface »).
- But : un drone de surface (USV) de surveillance maritime qui détecte et identifie les navires (catégorie, immatriculation par OCR, suivi) et envoie des alertes.
- **Client et tuteur entreprise** : Antoine Douchin, Cerema (DTecREM, pôle drone et traitement de données, Plouzané), GitHub `ElNormando`. **Tuteur école** : Matthieu Arzel, deux t, GitHub `marzelbr`.
- **Les deux ont accès au dépôt pour suivre l'avancement.** Ne jamais les assigner, les mentionner (`@`) ni leur envoyer quoi que ce soit, et n'écrire dans le dépôt que ce qu'ils peuvent lire.
- **Exigence de fond** : le drone est vraiment autonome. L'approche d'un navire est décidée et exécutée à bord, sans validation de l'opérateur, qui reçoit les alertes et peut reprendre la main. Ne pas proposer d'architecture où une décision de mission attend un humain ; prévoir plutôt des garde-fous embarqués.

## Équipe

| Lot | Qui | Rôle organisationnel |
|---|---|---|
| L1 Plateforme (bateau, matériel) | Ewen Gourmelen, Rana Brini, Selma Ben-Abdelkader | Ewen : matériel et responsable du suivi plateforme · Rana : matériel · Selma : livrables |
| L2 Vision embarquée (IA) | Reda El Mekkaoui, Guillaume Leroy, Adam-Sabri Hlaoua | Reda : communication client et responsable du suivi IA · Guillaume : responsable projet · Adam-Sabri : comptes rendus |
| L0 Gestion de projet, L3 Intégration | toute l'équipe | |

Rana n'est pas encore dans le dépôt GitHub.

**Qui fait quoi en ce moment** : toujours dans `cerema-usv-ia/docs/comptes_rendus/README.md` (tableau « Répartition des tâches en cours »). Ne pas recopier les tâches ici, elles changent à chaque séance.

Priorités décidées le 05/11/2026 : côté IA, une vision et des alertes parfaitement fiables d'abord (tests de dégradation, tests d'hallucination), puis la ré-identification, puis la vision nocturne, et le mode d'emploi en dernier livrable. Côté plateforme, une dernière tentative sur le GPS actuel (sinon on change de module, plan B F9P), puis moteurs, ESC, télémétrie, ArduPilot et QGroundControl, avec une mission préprogrammée comme objectif.

## Où sont les choses

```
~/Desktop/imt/cerema/
├── cerema-usv-ia/          dépôt d'équipe (GitHub Redaelm47/cerema-usv-ia, privé)
│   ├── docs/               tout ce qui se lit
│   │   ├── docs/comptes_rendus/ PDF des réunions + sommaire ; sources/ = .tex, style, modèles
│   │   ├── guides/         raspberry_pi/ (prise en main du Pi), git.md
│   │   ├── revue_de_projet/
│   │   ├── CHANGELOG.md    historique du dépôt
│   │   └── *.pdf           sujet, synthèse, architecture, plan d'actions
│   ├── ia/                 vision embarquée ; chaine/, suivi/, embarque/ et INTERFACES.md sont sur la branche ia/chaine-squelette
│   ├── station_sol/        serveur et page opérateur
│   ├── usv/                assemblage, motorisation, missions, matériel
│   ├── ressources/         travail de l'équipe 2025
│   └── .claude/skills/     copie partagée de ces skills
├── overleaf/projet-partage/        Overleaf de la synthèse, partagé à six (clone git)
├── overleaf/architecture-vision/   Overleaf personnel de Reda (architecture de la vision)
├── diapo/                  présentations (revue de projet, réunions tuteur)
└── .claude/skills/         ces skills, chargés à chaque session ouverte ici
```

**Racine du dépôt sobre** (demandé par Reda le 05/11/2026, « comme font les professionnels ») : à la racine, seulement `README.md` (une page), `.gitignore`, `.github/`, `.claude/` et les dossiers `docs/`, `ia/`, `station_sol/`, `usv/`, `ressources/`. Ne rien créer d'autre à la racine : un document va dans `docs/`, un résultat de script ne se commite pas (l'ajouter au `.gitignore`). Le README reste court ; le détail va dans le README du dossier concerné.

Le dossier parent `~/Desktop/imt/cerema` est un dépôt local sans remote qui ignore les sous-dépôts. Ne rien y pousser.

**Les skills existent en deux copies** : `~/Desktop/imt/cerema/.claude/skills/` (celle que je lis) et `cerema-usv-ia/.claude/skills/` sur `main` (celle de l'équipe). Après toute modification, recopier vers le dépôt et pousser, pour que les deux restent identiques.

## Git (dépôt d'équipe)

- Ne pousser que quand Reda le demande.
- Le client et le tuteur école lisent le dépôt : chaque fichier poussé doit pouvoir être lu par eux.
- La copie locale est souvent sur une branche de travail (`ia/chaine-squelette`, non fusionnée) avec des modifications non commitées : ne jamais faire de checkout ni de stash dessus. Pour écrire sur `main`, passer par un worktree temporaire dans le scratchpad (commandes dans le skill `compte-rendu-reunion`), puis `git branch -f main origin/main`.
- Le README demande des branches et des pull requests pour le code. Les documents et les comptes rendus vont directement sur `main` quand Reda le demande.
- `git fetch` juste avant de pousser : les autres poussent aussi.
- Messages de commit en français, qui disent ce qui change. Noter les évolutions importantes dans `docs/CHANGELOG.md`, avec la date.
- Avant de publier un fichier fourni par Reda (un PDF des téléchargements, par exemple), le lire en entier. S'il en envoie une nouvelle version, comparer le texte avec l'ancienne et lui dire ce qui a changé.

## Documents (LaTeX, PDF)

- Compilation : `tectonic` (`/opt/homebrew/bin/tectonic`). Il n'y a ni `pdflatex`, ni `latexmk`, ni `pandoc`. Compiler avec `-o` vers le scratchpad ou le dossier cible, pour ne pas salir les sources.
- **Toujours compiler avant de pousser**, puis regarder le résultat : `pdftoppm -r 70 -png fichier.pdf <scratchpad>/apercu` et lire les images (pages, débordements, titres seuls en bas de page).
- Style maison : police TeX Gyre Heros, palette des schémas (caméra `0D9488`, experts `EA580C`, Pi `4F46E5`, encre `0F172A`, gris `64748B`). Pour les PDF de l'équipe, reprendre `docs/comptes_rendus/sources/style_cr.sty`.
- **Gantt** dans une présentation : reprendre le Gantt pgfgantt de la synthèse (`docs/document_synthese/src/sections/05-organisation.tex`), compilé à part, avec une ligne rouge « aujourd'hui ». La couleur code le lot, rien d'autre. Ne pas ajouter d'informations sans source.
- Les équipes lisent des PDF : ne pas livrer un `.md` comme document final.

## Overleaf partagé (synthèse à six)

- Clone git : `overleaf/projet-partage`, fichier principal `src/tp_latex_lab_006.tex`, une section par fichier dans `src/sections/`. On y travaille par `git fetch` / commit / `git push`, pas dans le navigateur.
- Annoncer les changements à Reda avant de les faire. **Ne jamais supprimer ce qu'un camarade a écrit** : ajouter plutôt. Chaque section a un rédacteur référent (tableau en tête du `.tex`).
- Compiler avec tectonic avant de pousser, et `git fetch` juste avant : les camarades éditent en direct.

## Raspberry Pi et caméra IMX500

- **Avant toute action sur le Pi** (connexion, installation, caméra) **et avant d'afficher quoi que ce soit en plein écran sur le Mac** : dire le plan en quelques lignes et attendre l'accord de Reda. Les lectures seules (état, fichiers) n'en demandent pas.
- Le Pi est partagé avec Guillaume : vérifier que la caméra est libre (`ps` sur le Pi) avant de la prendre ; un seul programme à la fois peut tenir la caméra. Ne pas toucher à son dossier `~/Desktop/Yolo_test`.
- Accès : `ssh pi@cerema-pi.local` (clé du Mac déjà installée), seulement quand le Mac et le Pi sont sur le même réseau. Déploiement : `sh ia/raspberry_pi/deployer.sh` vers `~/cerema`. Commandes de lancement : `ia/embarque/README.md` (ces deux fichiers sont sur la branche `ia/chaine-squelette`, pas encore sur `main`) et `docs/guides/raspberry_pi/use_raspberry_pi.md`.
- L'orientation de l'image dépend du montage : la vérifier à chaque séance (le 02/11, image droite, donc `--sans-retournement`).
- Ne pas installer de logiciel sur le Mac ou le Pi sans l'accord de Reda.

## Choix déjà arrêtés pour la vision

- Chaîne : caméra IMX500 (YOLO11n sur le capteur), suivi (un numéro par navire), décideur, experts (filtre qualité, type, OCR), alertes vers la station sol. Contrats JSON entre les parties : `docs/repartition_travail.pdf` et `ia/INTERFACES.md` (branche `ia/chaine-squelette`).
- Décideur : règles en Python d'abord, puis régression logistique calibrée par expert, apprise sur les journaux.
- Pas de service en ligne pour la démonstration (Supabase écarté) ; pas de MAVLink ni d'ArduPilot côté vision pour l'instant.
- Le GPS se branche directement sur le Pixhawk, pas via le Raspberry Pi.

## Répondre à Reda

- En français, direct et dense, sans tiret cadratin.
- « Dis-moi quoi faire » : une liste d'actions concrètes, et s'arrêter là. Ne pas se lancer dans du code, une installation ou un téléchargement sans demande explicite. Proposer en une ligne ce que je peux faire à sa place.
- Poser une question seulement si la réponse change ce que je fais, et grouper les questions en une fois. Sinon, choisir le plus raisonnable et le dire.
- Ne rien inventer ; dire clairement ce qui n'a pas été vérifié ou ce qui a été supposé.
- Quand il veut voir un résultat sur GitHub : `open "<url>"`.
