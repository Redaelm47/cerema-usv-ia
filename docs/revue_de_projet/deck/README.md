# Revue de projet : version web (21/10/2026)

Version refaite de la présentation, après la réunion client du 15/10/2026.

- [revue-projet-P20.pdf](revue-projet-P20.pdf) : la présentation en PDF (15 diapositives).
- `index.html` : la même présentation, à ouvrir dans Chrome (flèches pour avancer, F pour le plein écran).
- `slides.js` : le contenu des diapositives ; `build.js` : l'assemblage de `index.html`.
- `assets/` : images de la simulation et Gantt du document de synthèse (`gantt-synthese.tex`, compilé avec tectonic).

Pour regénérer `index.html`, il faut le dépôt `claude-presentation-skills` :
`NODE_PATH=<outils>/node_modules node build.js <claude-presentation-skills>/.claude/skills`
