# Programme embarqué

Ce qui tourne sur le Raspberry Pi : la caméra et le suivi (`ia/suivi`), puis la décision et les experts (`ia/chaine`), dans un seul processus. Les messages partent vers la station sol, qui tourne sur le Mac. Voir [INTERFACES.md](../INTERFACES.md).

```
python3 -m embarque --pi --station http://<adresse-du-mac>:8000                  # sur le Pi
python3 -m embarque --video ../data/scene-blender-01.mp4 --temps-reel --seuil-ocr 300 \
                    --station http://localhost:8000                              # répétition sur le Mac
```

Installation sur le Pi, depuis le Mac : `sh ia/raspberry_pi/deployer.sh`.

Chaque lancement écrit trois fichiers dans `runs/` : `observations.jsonl` (sortie du suivi), `journal.jsonl` (décisions, avec la fiche du navire) et `messages.jsonl` (copie de ce qui est envoyé à la station sol). Ctrl+C arrête proprement : les navires en cours donnent une alerte partielle.

Le Pi ne reçoit rien de la station sol et n'attend jamais de réponse. Si elle est injoignable, la chaîne continue et le nombre de messages perdus est affiché à la fin.
