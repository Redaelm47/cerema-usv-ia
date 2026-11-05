# Projet USV-IA — Drone de surface et détection de navires

Projet de commande entreprise **IMT Atlantique × Cerema** (2026-2027).

Ce dépôt est la base de travail commune entre l'équipe étudiante et le Cerema : documents, code, comptes rendus et suivi des décisions. Il prend la suite du projet 2025 (groupe 11, « Micro drone de surface »).

## Par où commencer

| Je cherche… | Aller à |
|---|---|
| Qui fait quoi en ce moment | le dernier point de séance, en tête de [comptes_rendus](comptes_rendus/README.md) |
| Comment l'équipe s'organise (horaires, points de séance, suivi des tâches) | [docs/plan_actions_USV-IA.pdf](docs/plan_actions_USV-IA.pdf) |
| Le sujet et le cadrage du projet | [docs/sujet_projet20_cerema.pdf](docs/sujet_projet20_cerema.pdf), [docs/20_synthese_PCE_2026_v2.pdf](docs/20_synthese_PCE_2026_v2.pdf) |
| L'architecture de la vision embarquée | [docs/architecture_vision_embarquee.pdf](docs/architecture_vision_embarquee.pdf) |
| Qui fait quoi pour la démonstration, et les contrats JSON entre les parties | [docs/repartition_travail.pdf](docs/repartition_travail.pdf) |
| Me connecter au Raspberry Pi et lancer YOLO | [sandbox/use_raspberry_pi.md](sandbox/use_raspberry_pi.md) |
| Lancer la station sol (page opérateur) | [station_sol](station_sol) |
| Le travail de l'équipe 2025 | [ressources/projet_2025](ressources/projet_2025) |
| Les comptes rendus de réunion | [comptes_rendus](comptes_rendus) |
| Ce qui a changé récemment | [CHANGELOG.md](CHANGELOG.md) |

## Contexte

Le Cerema (Direction technique risques, eaux et mer, pôle drone et traitement de données) développe un drone de surface autonome (USV, *Unmanned Surface Vehicle*) capable de détecter et d'identifier les navires qui passent dans son champ de vision.

Le projet 2025 a posé les bases :

- assemblage d'une première version du drone ;
- choix d'une architecture à deux niveaux de caméras : une caméra basse résolution en fonctionnement permanent, qui passe la main à la caméra IA lorsqu'une détection plus gourmande en énergie et en ressources est nécessaire ;
- tests YOLO sur la dégradation des images (baisse de résolution, masquage par gouttes de pluie).

## Objectifs

### Volet USV

Assembler de manière pérenne les composants du drone et rendre opérationnelle l'exécution de missions préprogrammées (waypoints).

- [ ] Confirmer le schéma d'assemblage entre les différents composants et identifier les manques (modem…) → [usv/assemblage](usv/assemblage)
- [ ] Valider une motorisation (gouverne ? gestion du sens de rotation moteur ?) → [usv/motorisation](usv/motorisation)
- [ ] Exécuter une mission préprogrammée par waypoints → [usv/missions](usv/missions)

### Volet IA

Créer une chaîne fonctionnelle de détection des navires passant dans le champ de vision du drone : catégorie du navire, immatriculation (OCR), activité (tracking).

- [ ] Confirmer / améliorer le modèle de détection en conditions environnementales difficiles (pluie, roulis, mouvement) → [ia/detection](ia/detection)
- [ ] Lire l'immatriculation des navires (OCR) → [ia/ocr](ia/ocr)
- [ ] Suivre l'activité des navires (tracking) → [ia/tracking](ia/tracking)
- [ ] Monter 2 caméras (si possible) sur un Raspberry Pi 4 → [ia/raspberry_pi](ia/raspberry_pi)
- [ ] Porter le projet de manière pérenne sur Raspberry Pi → [ia/raspberry_pi](ia/raspberry_pi)
- [ ] Afficher les alertes et l'état du drone au sol → [station_sol](station_sol)

## Équipe et lots

| Lot | Responsables | Dossiers |
|---|---|---|
| L0 — Gestion de projet | toute l'équipe | [docs](docs), [comptes_rendus](comptes_rendus) |
| L1 — Intégration du bateau | Ewen, Rana, Selma | [usv](usv) |
| L2 — Vision embarquée | Guillaume, Reda, Adam-Sabri | [ia](ia), [station_sol](station_sol), [sandbox](sandbox) |
| L3 — Intégration vision et bateau | toute l'équipe | — |

Pour la démonstration de la semaine du 12/10/2026, le lot L2 est réparti ainsi ([détails](docs/repartition_travail.pdf)) :

- **Guillaume** : caméra IMX500 et suivi des navires, sur le Pi ;
- **Reda** : décideur, experts (type, OCR, approche) et vidéo de test Blender ;
- **Adam-Sabri** : station sol, c'est-à-dire le serveur et la page opérateur.

La répartition en cours, pour les deux lots, est dans le dernier point de séance : voir [comptes_rendus](comptes_rendus/README.md).

| Membre | Rôle organisationnel |
|---|---|
| Guillaume Leroy | responsable projet |
| Reda El Mekkaoui | responsable communication client |
| Adam-Sabri Hlaoua | responsable comptes rendus |
| Ewen Gourmelen | responsable matériel |
| Rana Brini | responsable matériel |
| Selma Ben-Abdelkader | responsable livrables |

**Client :** Antoine Douchin, chargé d'études, pôle drone et traitement de données, Cerema (DTecREM).

## Matériel à disposition

| Élément | Quantité | Remarque |
|---|---|---|
| Caméras | 3 | dont une orientée IA (IMX500) |
| Raspberry Pi 4 | 1 | calculateur embarqué |
| Composants du drone | — | inventaire à compléter dans [usv/assemblage](usv/assemblage) |

## Organisation du dépôt

```
cerema-usv-ia/
├── docs/             livrables : sujet, synthèse, architecture, répartition du travail
├── comptes_rendus/   réunions avec le Cerema, points de séance de l'équipe
├── usv/              volet bateau : assemblage, motorisation, missions
├── ia/               volet IA : détection, OCR, tracking, Raspberry Pi
├── station_sol/      serveur et page opérateur (alertes et état du drone en direct)
├── sandbox/          essais et notes de prise en main (Raspberry Pi, caméra)
├── ressources/       documents utiles et travail de l'équipe 2025
└── CHANGELOG.md      historique des principales évolutions
```

Chaque dossier a son propre `README.md` : il dit ce qu'on y trouve, comment s'en servir, et ce qui reste à faire.

Les fichiers lourds (jeux de données, poids de modèles, vidéos) ne sont pas versionnés dans Git : on indique dans le README du dossier concerné où les trouver.

## Travailler avec Git

On ne travaille jamais directement sur `main` : chacun travaille sur sa branche, et le travail entre dans `main` après relecture.

```bash
# 1. Récupérer le travail des autres
git checkout main
git pull

# 2. Créer sa branche (une par sujet), ou revenir sur une branche existante
git checkout -b ia/ocr          # nouvelle branche
git checkout ia/ocr             # branche existante

# 3. Enregistrer son travail
git add <fichiers>
git commit -m "OCR : lecture des immatriculations sur image fixe"

# 4. Envoyer sa branche sur GitHub
git push -u origin ia/ocr       # la première fois
git push                        # ensuite
```

5. Sur GitHub, ouvrir une *pull request* vers `main` et remplir le modèle (objet, volet, vérifications).
6. Un autre membre de l'équipe relit, puis fusionne (*merge*).
7. Tout le monde refait `git checkout main` puis `git pull`.

Si `main` a avancé pendant qu'on travaillait : `git pull origin main` depuis sa branche, puis régler les éventuels conflits.

Conventions :

- noms de branches : `volet/sujet` (`usv/motorisation`, `ia/ocr`, `station_sol`…) ;
- messages de commit en français, qui disent ce qui change ;
- noter les évolutions importantes dans [CHANGELOG.md](CHANGELOG.md).

## Suivi

Des échanges réguliers avec le Cerema sont prévus, toutes les 2 à 3 semaines. Chaque réunion fait l'objet d'un compte rendu dans [comptes_rendus](comptes_rendus), à partir du [modèle](comptes_rendus/sources/modele_compte_rendu.md).

Depuis le 05/11/2026, chaque séance commence (8h30) et se termine (11h40) par un point à six. Le point de fin est résumé dans [comptes_rendus](comptes_rendus/README.md), à partir du [modèle de point de séance](comptes_rendus/sources/modele_point_de_seance.md). Voir le [plan d'actions](docs/plan_actions_USV-IA.pdf).

## Licence

À définir avec le Cerema. Le modèle de dépôt [cnigfr/cnig-template](https://github.com/cnigfr/cnig-template), dont ce dépôt s'inspire, utilise la [Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
