# Station sol

Responsable : Adam-Sabri Hlaoua (lot L2, vision embarquée). Voir [docs/repartition_travail.pdf](../docs/repartition_travail.pdf).

Serveur qui tourne sur le Mac, reçoit les messages du drone (contrat n°3) et les affiche **en direct** sur une page opérateur : alertes, navires suivis, état du drone.

Uniquement la bibliothèque standard de Python (3.10 ou plus) : rien à installer.

## Lancer

```bash
cd station_sol
python serveur.py           # puis ouvrir http://localhost:8000
```

Dans un second terminal, pour tester sans le drone :

```bash
python rejouer.py                   # rejoue exemples/scenario_demo.jsonl (~22 s)
python rejouer.py --vitesse 3 --boucle
```

## Suivre la mission depuis un téléphone

Le téléphone doit être sur le même réseau que le Mac. Le serveur affiche au démarrage l'adresse à ouvrir, de la forme `http://nom-du-mac.local:8000`. La page s'adapte à un écran étroit.

## Quand le Pi et le Mac ne sont pas sur le même réseau

Le Pi ne peut alors pas joindre le Mac directement. Il faut une adresse publique qui mène au serveur du Mac : un tunnel. Avec `cloudflared` (`brew install cloudflared`), dans un second terminal :

```bash
cloudflared tunnel --url http://localhost:8000
```

La commande affiche une adresse de la forme `https://quelque-chose.trycloudflare.com`. Cette adresse sert à tout : le Pi y envoie ses messages (`--station https://quelque-chose.trycloudflare.com`), et la page s'ouvre dessus depuis n'importe quel appareil, téléphone compris. Elle change à chaque lancement.

Tant que le tunnel est ouvert, quiconque connaît l'adresse peut voir la page et envoyer de faux messages : le fermer (Ctrl+C) après l'essai.

La copie de la page sur GitHub Pages (https://redaelm47.github.io/cerema-station-sol-test/) fonctionne aussi avec le tunnel, en ajoutant `?serveur=https://quelque-chose.trycloudflare.com` à son adresse. GitHub Pages ne peut pas remplacer le serveur : il ne sait que distribuer des fichiers, pas recevoir les messages du Pi.

## Envoyer des messages depuis le drone

Le décideur (Reda) envoie chaque message par `POST /message` vers `http://<ip-du-mac>:8000`. Le Mac et le Pi doivent être sur le même réseau ; l'adresse du Mac s'obtient avec `ipconfig getifaddr en0`.

```python
from client import envoyer   # station_sol/client.py, à copier sur le Pi

envoyer({"genre": "decision", "t": 0.6, "id_piste": 7,
         "action": "approche", "raison": "navire trop petit pour lire"},
        url="http://192.168.1.20:8000")
```

Ou depuis un terminal :

```bash
curl -X POST http://localhost:8000/message -d '{"genre": "etat", "t": 48.0, "mode": "patrouille", "batterie": 0.82, "navires_suivis": 2, "temperature_pi": 61.5}'
```

Le serveur vérifie chaque message ([contrat.py](contrat.py)) et refuse ceux qui ne respectent pas le contrat (réponse 400 avec la liste des erreurs). On peut aussi envoyer plusieurs messages d'un coup, un objet JSON par ligne.

## Contrat n°3 : messages de Reda vers Adam-Sabri

Un objet JSON par message, aucune image.

| Genre | Champs |
|---|---|
| `alerte` | `t`, `id_piste`, `complete`, `types` (liste, vide si inconnu), `immatriculation` (ou `null`), `confiance_immatriculation` (ou `null`), `raison`, et parfois `textes_lus` (liste des textes lus sur la coque qui ne sont pas une immatriculation française) |
| `decision` | `t`, `id_piste`, `action`, `raison` |
| `etat` | `t`, `mode`, `batterie` (simulée, entre 0 et 1), `navires_suivis`, `temperature_pi` (`null` ailleurs que sur le Pi) |

- `t` : secondes depuis le démarrage du drone.
- Actions : `expert_type`, `expert_ocr`, `approche`, `alerte_complete`, `alerte_partielle`.
- Modes : `patrouille`, `approche`.

Si le contrat change, mettre à jour ensemble `contrat.py`, ce tableau et `exemples/scenario_demo.jsonl`.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `serveur.py` | reçoit les messages, les vérifie, les pousse vers la page (Server-Sent Events) et les enregistre dans `journaux/` |
| `contrat.py` | vérification des messages selon le contrat n°3 |
| `client.py` | fonction `envoyer()` à utiliser côté drone |
| `rejouer.py` | rejoue un fichier de faux messages au rythme de leur `t` |
| `exemples/scenario_demo.jsonl` | scénario de démonstration : trois navires, une alerte partielle, une montée en température |
| `page/` | page opérateur (HTML, CSS, JavaScript sans bibliothèque) |
| `journaux/` | messages reçus, un fichier par lancement (non versionné) |

Un journal enregistré peut être rejoué : `python rejouer.py journaux/messages_<date>.jsonl`.

## Jalons

- [x] 09/10 (prévu) : faux messages rejoués pour le tableau de bord
- [ ] 12/10 : chaîne complète sur ordinateur (messages réels du décideur)
- [ ] 14/10 : tout sur le Pi, station sol sur le Mac
- [ ] Veille de la réunion : répétition
