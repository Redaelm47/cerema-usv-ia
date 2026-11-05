# Travailler avec Git

Guide de l'équipe, repris de l'ancienne page d'accueil du dépôt.

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
- noter les évolutions importantes dans [CHANGELOG.md](../CHANGELOG.md).
