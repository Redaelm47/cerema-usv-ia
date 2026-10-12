"""Journal des décisions : une ligne JSON par action. Sert de preuve et de données d'entraînement."""
import json
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, chemin: str | Path | None = None):
        self.lignes: list[dict[str, Any]] = []
        self._fichier = None
        if chemin is not None:
            chemin = Path(chemin)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            self._fichier = chemin.open("w", encoding="utf-8")

    def noter(self, **ligne: Any) -> None:
        self.lignes.append(ligne)
        if self._fichier:
            self._fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            self._fichier.flush()

    def fermer(self) -> None:
        if self._fichier:
            self._fichier.close()
            self._fichier = None
