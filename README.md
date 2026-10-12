# Projet USV-IA — Drone de surface et détection de navires

Projet de commande entreprise **IMT Atlantique × Cerema** (2026-2027).

Ce dépôt est la base de travail commune entre l'équipe étudiante et le Cerema : documents, code, comptes rendus et suivi des décisions. Il prend la suite du projet 2025 (groupe 11, « Micro drone de surface »).

## Contexte

Le Cerema (Direction technique risques, eaux et mer, pôle drone et traitement de données) développe un drone de surface autonome (USV, *Unmanned Surface Vehicle*) capable de détecter et d'identifier les navires qui passent dans son champ de vision.

Le projet 2025 a posé les bases :

- assemblage d'une première version du drone ;
- choix d'une architecture à deux niveaux de caméras : une caméra basse résolution en fonctionnement permanent, qui passe la main à la caméra IA lorsqu'une détection plus gourmande en énergie et en ressources est nécessaire ;
- tests YOLO sur la dégradation des images (baisse de résolution, masquage par gouttes de pluie).

Les documents du projet 2025 sont listés dans [ressources/projet_2025](ressources/projet_2025).

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

## Matériel à disposition

| Élément | Quantité | Remarque |
|---|---|---|
| Caméras | 3 | dont une orientée IA |
| Raspberry Pi 4 | 1 | calculateur embarqué |
| Composants du drone | — | inventaire à compléter dans [usv/assemblage](usv/assemblage) |

## Organisation du dépôt

- [comptes_rendus](comptes_rendus) : comptes rendus des réunions avec le Cerema et des réunions d'équipe ;
- [ressources](ressources) : documents utiles (fiches techniques, articles, travail des prédécesseurs) ;
- [usv](usv) : assemblage, motorisation et missions du drone ;
- [ia](ia) : détection, OCR, tracking et portage sur Raspberry Pi ;
- [station_sol](station_sol) : serveur et page opérateur qui affichent en direct les alertes et l'état du drone ;
- [docs](docs) : livrables du projet (rapports, présentations, poster) ;
- [CHANGELOG.md](CHANGELOG.md) : historique des principales évolutions.

## Équipe

**Client :** Antoine Douchin, chargé d'études, pôle drone et traitement de données, Cerema (DTecREM).

**Équipe IMT Atlantique :**

- Adam-Sabri Hlaoua
- Ewen Gourmelen
- Guillaume Leroy
- Selma Ben-Abdelkader
- Rana Brini
- Reda El Mekkaoui

## Suivi

Des échanges réguliers avec le Cerema sont prévus, toutes les 2 à 3 semaines. Chaque réunion fait l'objet d'un compte rendu dans [comptes_rendus](comptes_rendus), à partir du [modèle](comptes_rendus/modele_compte_rendu.md).

## Contribuer

1. Créer une branche par sujet (`usv/motorisation`, `ia/ocr`…).
2. Ouvrir une *pull request* vers `main` et la faire relire par un membre de l'équipe.
3. Noter les évolutions importantes dans [CHANGELOG.md](CHANGELOG.md).

Les fichiers lourds (jeux de données, poids de modèles, vidéos) ne sont pas versionnés dans Git : on indique dans le dossier concerné où les trouver.

## Licence

À définir avec le Cerema. Le modèle de dépôt [cnigfr/cnig-template](https://github.com/cnigfr/cnig-template), dont ce dépôt s'inspire, utilise la [Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
