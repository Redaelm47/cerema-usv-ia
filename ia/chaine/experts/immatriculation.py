"""Immatriculation française d'un navire de pêche : contrôle du format et vote sur plusieurs images.

Format contrôlé : les deux lettres du quartier maritime puis six chiffres, par exemple « GV 123456 ».
Aucune dépendance : ce module se teste sans modèle ni image.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

# Quartiers maritimes. Liste écrite de mémoire, À VÉRIFIER avec le Cerema ou les Affaires maritimes :
# un quartier absent de la liste baisse la confiance de la lecture mais ne la rejette pas.
QUARTIERS = {
    "DK": "Dunkerque", "BL": "Boulogne-sur-Mer", "DP": "Dieppe", "FC": "Fécamp", "LH": "Le Havre",
    "CN": "Caen", "CH": "Cherbourg", "SM": "Saint-Malo", "SB": "Saint-Brieuc", "PL": "Paimpol",
    "MX": "Morlaix", "BR": "Brest", "CM": "Camaret", "DZ": "Douarnenez", "AD": "Audierne",
    "GV": "Le Guilvinec", "CC": "Concarneau", "LO": "Lorient", "AY": "Auray", "VA": "Vannes",
    "SN": "Saint-Nazaire", "NA": "Nantes", "NO": "Noirmoutier", "YE": "Île d'Yeu",
    "LS": "Les Sables-d'Olonne", "LR": "La Rochelle", "IO": "Île d'Oléron", "MN": "Marennes",
    "BX": "Bordeaux", "AC": "Arcachon", "BA": "Bayonne", "PV": "Port-Vendres", "ST": "Sète",
    "MT": "Martigues", "MA": "Marseille", "TL": "Toulon", "NI": "Nice", "AJ": "Ajaccio", "BI": "Bastia",
    "PP": "Pointe-à-Pitre", "FF": "Fort-de-France", "CY": "Cayenne", "RU": "La Réunion",
    "SP": "Saint-Pierre-et-Miquelon",
}

# Confusions habituelles de la lecture, corrigées selon la position (lettre ou chiffre attendu).
EN_LETTRE = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
EN_CHIFFRE = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "A": "4", "S": "5", "G": "6", "B": "8"}

PENALITE_CORRECTION = 0.9       # par caractère corrigé
PENALITE_QUARTIER_INCONNU = 0.8
MAX_CORRECTIONS = 2

# Deux caractères, un séparateur éventuel, six caractères parfois groupés (« BL 925 621 »), le tout isolé :
# « FAX 05 46 50 » ou un numéro à sept chiffres ne passent pas.
MOTIF = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{2})[ .\-]{0,3}((?:[A-Z0-9][ .]?){5}[A-Z0-9])(?![0-9])")


@dataclass
class Lecture:
    texte: str               # forme normalisée : « GV 123456 »
    corrections: int         # caractères corrigés pour respecter le format
    quartier_connu: bool

    @property
    def poids(self) -> float:
        """Facteur appliqué à la confiance de la lecture."""
        return PENALITE_CORRECTION ** self.corrections * (1.0 if self.quartier_connu else PENALITE_QUARTIER_INCONNU)


def interpreter(texte: str) -> Lecture | None:
    """Cherche une immatriculation au format français dans un texte lu, None s'il n'y en a pas."""
    texte = texte.upper()
    meilleure = None
    for debut in range(len(texte)):
        trouve = MOTIF.match(texte, debut)
        if not trouve:
            continue
        brut = trouve.group(1) + re.sub(r"[ .]", "", trouve.group(2))
        lettres = [c if c.isalpha() else EN_LETTRE.get(c) for c in brut[:2]]
        chiffres = [c if c.isdigit() else EN_CHIFFRE.get(c) for c in brut[2:]]
        if None in lettres or None in chiffres:
            continue
        corrige = "".join(lettres) + "".join(chiffres)
        lecture = Lecture(f"{corrige[:2]} {corrige[2:]}", sum(a != b for a, b in zip(brut, corrige)),
                          corrige[:2] in QUARTIERS)
        # Un quartier absent de la liste n'est accepté que lu sans aucune correction.
        if lecture.corrections > (MAX_CORRECTIONS if lecture.quartier_connu else 0):
            continue
        if meilleure is None or lecture.poids > meilleure.poids:
            meilleure = lecture
    return meilleure


@dataclass
class Vote:
    """Vote, caractère par caractère, sur les lectures d'une même piste."""
    lectures: list[tuple[str, float]] = field(default_factory=list)  # texte normalisé, confiance

    def ajouter(self, texte: str, confiance: float) -> None:
        self.lectures.append((texte, confiance))

    def resultat(self, lectures_pour_valider: int = 2, part_min: float = 0.6) -> tuple[str | None, float, bool]:
        """Immatriculation candidate, sa confiance, et si le vote la valide."""
        if not self.lectures:
            return None, 0.0, False
        candidate, part = "", 1.0
        for position in range(len(self.lectures[0][0])):
            poids: dict[str, float] = defaultdict(float)
            for texte, confiance in self.lectures:
                poids[texte[position]] += confiance
            gagnant = max(poids, key=poids.get)
            candidate += gagnant
            part = min(part, poids[gagnant] / sum(poids.values()))
        accords = [confiance for texte, confiance in self.lectures if texte == candidate]
        if not accords:
            return candidate, 0.0, False
        confiance = part * sum(accords) / len(accords)
        validee = part >= part_min and len(accords) >= lectures_pour_valider
        return candidate, confiance, validee
