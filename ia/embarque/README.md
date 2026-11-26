# Programme embarqué

Ce qui tourne sur le Raspberry Pi : la caméra et le suivi (`ia/suivi`), puis la décision et les experts (`ia/chaine`), dans un seul processus. Les messages partent vers la station sol, qui tourne sur le Mac. Voir [INTERFACES.md](../INTERFACES.md).

```
python3 -m embarque --pi --station http://<adresse-du-mac>:8000                  # sur le Pi
# en mer, ajouter --boite runs/boite.db : les messages attendent la station au lieu d'être perdus si la liaison coupe
python3 -m embarque --video ../data/scene-blender-01.mp4 --temps-reel --seuil-ocr 300 \
                    --station http://localhost:8000                              # répétition sur le Mac
```

Pour voir en direct sur le Mac la caméra, les boîtes et les fiches des navires, à travers ssh (fermer la fenêtre arrête le programme et envoie les alertes en cours) :

```
ssh pi@cerema-pi.local "cd cerema/ia && exec ../env/bin/python -u -m embarque --pi --direct --station http://[<ipv6-du-mac>]:8000" \
    | ffplay -f mjpeg -fflags nobuffer -flags low_delay -framedrop -analyzeduration 0 -probesize 32 -
```

Sur un partage de connexion iPhone, le Pi ne trouve pas le Mac par son nom : donner son adresse IPv6, entre crochets. En 4056 x 3040 (`--resolution`), le réseau de la caméra ne rend un résultat qu'une image sur deux : le programme travaille à environ 5 images/s. `--sans-filtre-flou` retire le rejet des images floues, `--sans-retournement` se met quand la caméra est montée à l'endroit.

Installation sur le Pi, depuis le Mac : `sh ia/raspberry_pi/deployer.sh`.

Chaque lancement écrit trois fichiers dans `runs/` : `observations.jsonl` (sortie du suivi), `journal.jsonl` (décisions, avec la fiche du navire) et `messages.jsonl` (copie de ce qui est envoyé à la station sol). Ctrl+C arrête proprement : les navires en cours donnent une alerte partielle.

Le Pi ne reçoit rien de la station sol et n'attend jamais de réponse. Si elle est injoignable, la chaîne continue et le nombre de messages perdus est affiché à la fin.
