"""Vue en direct : images annotées écrites en JPEG sur un flux, et arrêt quand le lecteur s'en va."""
import io
import os
import sys
import tempfile
import unittest

import cv2
import numpy as np

from chaine.__main__ import derouler
from chaine.affichage import FluxAnnote
from chaine.experts import DroneSimule
from chaine.reglages import Reglages


class FluxCoupe(io.RawIOBase):
    """Flux dont le lecteur disparaît après quelques images."""

    def __init__(self, images_avant_coupure: int):
        self.restantes = images_avant_coupure

    def write(self, donnees) -> int:
        if self.restantes == 0:
            raise BrokenPipeError
        self.restantes -= 1
        return len(donnees)

    def flush(self) -> None:
        pass


class TestFluxAnnote(unittest.TestCase):
    def test_ecrit_un_jpeg_reduit_sans_toucher_a_l_image(self):
        flux = io.BytesIO()
        image = np.zeros((3040, 4056, 3), dtype=np.uint8)

        FluxAnnote(flux, largeur=1280).ecrire(image, [], 1.0)

        lue = cv2.imdecode(np.frombuffer(flux.getvalue(), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(lue.shape[1], 1280)
        self.assertEqual(lue.shape[0], 959)
        self.assertEqual(int(image.max()), 0)

    def test_lecteur_parti_la_chaine_se_cloture_et_alerte(self):
        self.addCleanup(setattr, sys, "stdout", sys.stdout)
        self.addCleanup(setattr, sys, "stderr", sys.stderr)
        image = np.zeros((200, 300, 3), dtype=np.uint8)
        piste = {"id_piste": 1, "boite": [10.0, 10.0, 100.0, 50.0], "confiance": 0.9}
        source = [({"t": i * 0.1, "pistes": [piste]}, image) for i in range(20)]

        with tempfile.TemporaryDirectory() as dossier:
            chaine = derouler(source, Reglages(), DroneSimule(), vrais_experts=False,
                              journal=os.path.join(dossier, "journal.jsonl"),
                              messages=[os.path.join(dossier, "messages.jsonl")], direct=FluxCoupe(5))

        self.assertEqual(len(chaine.alertes), 1)
        self.assertFalse(chaine.alertes[0]["complete"])


if __name__ == "__main__":
    unittest.main()
