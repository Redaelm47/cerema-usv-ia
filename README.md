# USV-IA · Drone de surface et détection de navires

Projet de commande entreprise **IMT Atlantique × Cerema**, 2026-2027.

Un drone de surface autonome qui détecte et identifie les navires (catégorie, immatriculation, suivi) et envoie des alertes à terre. Le projet prend la suite du travail de l'équipe 2025.

## Documents

| | |
|---|---|
| **Qui fait quoi en ce moment** | [Comptes rendus](docs/comptes_rendus) |
| Organisation de l'équipe | [Plan d'actions](docs/plan_actions_USV-IA.pdf) |
| Cadrage | [Sujet](docs/sujet_projet20_cerema.pdf) · [Document de synthèse](docs/20_synthese_PCE_2026_v2.pdf) |
| Vision embarquée | [Architecture](docs/architecture_vision_embarquee.pdf) · [Contrats entre les parties](docs/repartition_travail.pdf) |
| Revue de projet | [Présentation et suivi](docs/revue_de_projet) |

Tous les documents : [docs](docs).

## Structure

```
docs/          documents : comptes rendus, livrables, guides
ia/            vision embarquée : détection, OCR, suivi, Raspberry Pi
station_sol/   serveur et page opérateur
usv/           plateforme : assemblage, motorisation, missions
ressources/    travail de l'équipe 2025
```

## Équipe

| Membre | Lot | Rôle |
|---|---|---|
| Guillaume Leroy | Vision embarquée | Responsable projet |
| Reda El Mekkaoui | Vision embarquée | Communication client |
| Adam-Sabri Hlaoua | Vision embarquée | Comptes rendus |
| Ewen Gourmelen | Plateforme | Matériel |
| Rana Brini | Plateforme | Matériel |
| Selma Ben-Abdelkader | Plateforme | Livrables |

**Client** : Antoine Douchin, Cerema (pôle drone et traitement de données). **Tuteur école** : Matthieu Arzel, IMT Atlantique.

## Contribuer

Une branche par sujet, puis une pull request relue par un autre membre : voir le [guide Git](docs/guides/git.md). Les évolutions importantes sont notées dans l'[historique](docs/CHANGELOG.md).

Licence : à définir avec le Cerema.
