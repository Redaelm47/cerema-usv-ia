import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from chaine import contrats
from chaine.experts import DroneSimule
from chaine.fiche import Observation
from chaine.sources import ScenarioSimule, SourceRejouee, SourceVideo


def ecrire_video(chemin: Path, images: int = 5, taille=(320, 180)) -> None:
    ecrivain = cv2.VideoWriter(str(chemin), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, taille)
    for i in range(images):
        image = np.full((taille[1], taille[0], 3), 40 * i, np.uint8)
        ecrivain.write(image)
    ecrivain.release()


class TestScenarioSimule(unittest.TestCase):
    def test_le_navire_lointain_grossit_pendant_l_approche(self):
        drone = DroneSimule()
        largeurs = []
        for message, image in ScenarioSimule(drone, duree_s=30.0):
            drone.contexte(message["t"])
            if message["t"] == 1.0:
                drone.approcher(7, 400.0, 100.0)
            largeurs.append(next(p["boite"][2] for p in message["pistes"] if p["id_piste"] == 7))
            self.assertIsNone(image)
        self.assertEqual(largeurs[0], 150.0)
        self.assertGreater(largeurs[-1], 180.0)
        self.assertEqual(largeurs, sorted(largeurs))


class TestSourceRejouee(unittest.TestCase):
    def test_observations_et_images_rejouees_ensemble(self):
        with tempfile.TemporaryDirectory() as dossier:
            video, fichier = Path(dossier) / "v.mp4", Path(dossier) / "obs.jsonl"
            ecrire_video(video)
            messages = [contrats.observations(i / 10, [Observation(1, (10, 20, 30, 10), 0.9)]) for i in range(5)]
            fichier.write_text("\n".join(json.dumps(m) for m in messages) + "\n")
            source = SourceRejouee(str(video), str(fichier))
            rejoue = list(source)
        self.assertEqual(source.images_par_s, 10.0)
        self.assertEqual([m for m, _ in rejoue], messages)
        self.assertEqual({image.shape for _, image in rejoue}, {(180, 320, 3)})


class TestVueDeLaCameraSimulee(unittest.TestCase):
    """Le zoom de l'approche, sans lancer la détection."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        video = Path(self.dossier.name) / "v.mp4"
        ecrire_video(video, taille=(640, 360))
        self.video = str(video)
        self.image = np.zeros((360, 640, 3), np.uint8)
        self.image[100:140, 400:480] = 255   # un « navire » de 80 px

    def tearDown(self):
        self.dossier.cleanup()

    def test_video_illisible(self):
        with self.assertRaises(FileNotFoundError):
            SourceVideo("/nulle/part.mp4")

    def test_sans_approche_la_vue_est_l_image(self):
        source = SourceVideo(self.video, drone=DroneSimule())
        self.assertIs(source._vue(self.image), self.image)

    def test_vue_large_reduite(self):
        source = SourceVideo(self.video, drone=DroneSimule(), largeur_vue=320)
        self.assertEqual(source._vue(self.image).shape, (180, 320, 3))
        self.assertEqual(source._fenetre, (0.0, 0.0, 0.5))

    def test_l_approche_grossit_le_navire_et_le_garde_dans_la_vue(self):
        drone = DroneSimule()
        source = SourceVideo(self.video, drone=drone, largeur_vue=320)
        drone.approcher(1, 200.0, 100.0)
        boite = (200.0, 50.0, 40.0, 20.0)    # le navire dans la vue réduite de moitié
        for t in range(100):
            drone.contexte(float(t))
            vue = source._vue(self.image)
            source._suivre_la_cible([Observation(1, boite, 0.9)], vue)
            colonnes = np.flatnonzero(vue.max(axis=(0, 2)) > 128)
            lignes = np.flatnonzero(vue.max(axis=(1, 2)) > 128)
            boite = (float(colonnes[0]), float(lignes[0]), float(len(colonnes)), float(len(lignes)))
        self.assertAlmostEqual(drone.rapprochement, 2.0)
        self.assertEqual(vue.shape, (180, 320, 3))
        self.assertAlmostEqual(boite[2], 80.0, delta=2)          # deux fois plus gros : les pixels d'origine
        self.assertAlmostEqual(source._fenetre[2], 1.0, places=2)
        self.assertLess(abs(boite[0] + boite[2] / 2 - 160), 40)  # proche du centre de la vue


if __name__ == "__main__":
    unittest.main()
