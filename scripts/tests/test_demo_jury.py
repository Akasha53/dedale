"""Démo du jury : sauvegarde de la base, mesure du flux, garde-fous sur les processus."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_jury as jury


def creer_base(chemin: Path, evenements: int) -> None:
    connexion = sqlite3.connect(chemin)
    connexion.execute("CREATE TABLE evenements (id INTEGER PRIMARY KEY, type TEXT)")
    connexion.executemany("INSERT INTO evenements (type) VALUES (?)", [("requete",)] * evenements)
    connexion.commit()
    connexion.close()


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.base = Path(self.dossier.name) / "dedale.db"

    def tearDown(self):
        self.dossier.cleanup()

    def mettre_de_cote(self, **options):
        return jury.mettre_base_de_cote(self.base, maintenant=datetime(2026, 10, 10, 18, 0, 0),
                                        fichiers_ouverts=lambda _p: [], **options)

    def test_base_copiee_verifiee_puis_retiree(self):
        creer_base(self.base, 3)
        copie, evenements = self.mettre_de_cote()
        self.assertEqual(copie.name, "dedale-20261010-180000.db")
        self.assertEqual(evenements, 3)
        self.assertFalse(self.base.exists())
        self.assertEqual(jury.compter_evenements(copie), 3)

    def test_regles_du_soc_mises_de_cote_avec_la_base(self):
        creer_base(self.base, 2)
        regles = self.base.with_name("dedale-politiques.json")
        regles.write_text('{"regles": [{"id": "R-0001", "active": true}]}', encoding="utf-8")
        copie, _ = self.mettre_de_cote()
        self.assertFalse(regles.exists())
        self.assertEqual(copie.with_name(copie.stem + "-politiques.json").read_text(encoding="utf-8"),
                         '{"regles": [{"id": "R-0001", "active": true}]}')

    def test_deux_sauvegardes_la_meme_seconde_ne_s_ecrasent_pas(self):
        creer_base(self.base, 1)
        premiere, _ = self.mettre_de_cote()
        creer_base(self.base, 2)
        seconde, _ = self.mettre_de_cote()
        self.assertNotEqual(premiere, seconde)
        self.assertEqual(jury.compter_evenements(premiere), 1)

    def test_copie_illisible_laisse_l_original(self):
        self.base.write_bytes(b"pas une base sqlite" * 100)
        with self.assertRaisesRegex(jury.ErreurDemo, "Original laissé en place"):
            self.mettre_de_cote()
        self.assertTrue(self.base.exists())

    def test_base_ouverte_par_un_processus_refusee(self):
        creer_base(self.base, 1)
        with self.assertRaisesRegex(jury.ErreurDemo, "encore ouverte"):
            jury.mettre_base_de_cote(self.base, fichiers_ouverts=lambda _p: ["4242"])
        self.assertTrue(self.base.exists())
        self.assertFalse((self.base.parent / "sauvegardes").exists())

    def test_sans_base_rien_a_faire(self):
        self.assertIsNone(self.mettre_de_cote())


class MesureTest(unittest.TestCase):
    def test_durees_lisibles(self):
        self.assertEqual(jury.duree(0.0004), "0,4 ms")
        self.assertEqual(jury.duree(0.0123), "12 ms")
        self.assertEqual(jury.duree(1.25), "1,2 s")
        self.assertEqual(jury.duree(None), "non mesuré")

    def test_arrivee_avant_alerte_non_mesuree(self):
        self.assertIsNone(jury.ecart(10.0, (9.5, {})))
        self.assertIsNone(jury.ecart(10.0, None))
        self.assertAlmostEqual(jury.ecart(10.0, (10.25, {})), 0.25)

    def test_flux_garde_la_premiere_arrivee_d_un_incident(self):
        flux = jury.FluxConsole("http://localhost:5173")
        flux.recevoir(1.0, json.dumps({"type": "session", "donnees": {"session_id": "s"}}).encode())
        flux.recevoir(2.0, json.dumps({"type": "incident", "donnees": {"id": "INC-0001", "session_id": "s"}}).encode())
        flux.recevoir(3.0, json.dumps({"type": "incident", "donnees": {"id": "INC-0001", "session_id": "s"}}).encode())
        flux.recevoir(4.0, b"pas du json")
        self.assertEqual(flux.attendre("s", delai=0.1)[0], 2.0)
        self.assertIsNone(flux.attendre("autre", delai=0.05))

    def test_trames_websocket_lues_et_ping_renvoye(self):
        flux = jury.FluxConsole("http://127.0.0.1:5173")
        serveur, client = socket.socketpair()
        texte = json.dumps({"type": "incident", "donnees": {"id": "INC-0002", "session_id": "a"}}).encode()
        try:
            client.settimeout(0.5)
            flux._prise = client
            serveur.sendall(bytes([0x89, 2]) + b"ok")                       # ping
            serveur.sendall(bytes([0x81, 126]) + len(texte).to_bytes(2, "big") + texte)
            serveur.sendall(bytes([0x88, 0]))                               # fermeture
            flux._boucle()
            self.assertEqual(flux.arrivees["a"][1]["id"], "INC-0002")
            pong = serveur.recv(16)
            self.assertEqual(pong[0], 0x8A)
            masque = pong[2:6]
            self.assertEqual(bytes(c ^ masque[i % 4] for i, c in enumerate(pong[6:8])), b"ok")
        finally:
            serveur.close()
            client.close()


class ProcessusTest(unittest.TestCase):
    def test_autre_processus_sur_le_port_jamais_arrete(self):
        with patch.object(jury, "pids_ecoute", return_value=[4242]), \
                patch.object(jury, "commande_de", return_value="python -m http.server 8700"), \
                patch.object(jury.os, "kill") as tuer:
            with self.assertRaisesRegex(jury.ErreurDemo, "autre chose qu'un backend"):
                jury.arreter_backend(8700)
        tuer.assert_not_called()

    def test_backend_d_un_autre_dossier_jamais_arrete(self):
        with patch.object(jury, "pids_ecoute", return_value=[4242]), \
                patch.object(jury, "commande_de", return_value="uvicorn app.main:app --port 8700"), \
                patch.object(jury, "dossier_de", return_value=Path("/ailleurs/backend")), \
                patch.object(jury.os, "kill") as tuer:
            with self.assertRaisesRegex(jury.ErreurDemo, "autre dossier"):
                jury.arreter_backend(8700)
        tuer.assert_not_called()

    def test_arret_ne_vise_que_les_services_de_la_demo(self):
        with tempfile.TemporaryDirectory() as dossier:
            services = Path(dossier) / "services.json"
            services.write_text(json.dumps({"console": {"pid": 4242, "commande": "npm run dev"}}))
            with patch.object(jury, "SERVICES", services), \
                    patch.object(jury, "vivant", return_value=True), \
                    patch.object(jury, "commande_de", return_value="vim notes.txt"), \
                    patch.object(jury.os, "killpg") as tuer:
                messages = []
                jury.arreter_services(afficher=messages.append)
            tuer.assert_not_called()
            self.assertIn("laissé tel quel", messages[0])


if __name__ == "__main__":
    unittest.main()
