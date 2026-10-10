"""Contrôle des choix et de l'attente sans délai réel ni service externe."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_commune as demo


class Horloge:
    def __init__(self):
        self.maintenant = 0.0

    def lire(self):
        return self.maintenant

    def avancer(self, duree):
        self.maintenant += duree


class ApiTest:
    def __init__(self, decisions=None, etat="suspendue"):
        self.decisions = decisions or []
        self.etat = etat
        self.lectures = []

    def incident(self, session_id):
        return {"id": "INC-test", "session_id": session_id}

    def lire(self, chemin):
        self.lectures.append(chemin)
        return {"id": "INC-test", "session_id": "demo-test", "decisions": self.decisions}

    def session(self, session_id):
        return {"id": session_id, "etat": self.etat}


class AttenteTest(unittest.TestCase):
    def attendre(self, api, **options):
        self.horloge = Horloge()
        return demo.attendre_decision(
            api, "demo-test", attente=1.0, intervalle=0.2,
            console="http://localhost:8700", afficher=lambda _texte: None,
            horloge=self.horloge.lire, pause=self.horloge.avancer, **options,
        )

    def test_sans_decision_meme_active_aucune_reprise(self):
        api = ApiTest(etat="active")
        with self.assertRaises(demo.AttenteExpiree):
            self.attendre(api)
        self.assertEqual(self.horloge.maintenant, 1.0)

    def test_decision_et_etat_doivent_correspondre(self):
        api = ApiTest(decisions=[{"action": "reprendre"}], etat="suspendue")
        with self.assertRaises(demo.AttenteExpiree):
            self.attendre(api)

    def test_dernier_choix_du_soc_fait_foi(self):
        api = ApiTest(decisions=[{"action": "reprendre"}, {"action": "couper"}], etat="coupee")
        self.assertEqual(self.attendre(api), "couper")

    def test_les_actions_de_la_console_sont_reconnues(self):
        for action, etat, attendu in [
            ("couper", "coupee", "couper"),
            ("valider_riposte", "coupee", "couper"),
            ("reprendre", "active", "reprendre"),
            ("ignorer", "active", "reprendre"),
        ]:
            with self.subTest(action=action):
                self.assertEqual(self.attendre(ApiTest([{"action": action}], etat)), attendu)

    def test_panne_backend_arrête_l_attente(self):
        api = ApiTest()
        with patch.object(api, "lire", side_effect=demo.ErreurDemo("backend absent")):
            with self.assertRaisesRegex(demo.ErreurDemo, "backend absent"):
                self.attendre(api)

    def test_incident_absent_ne_passe_pas_inaperçu(self):
        api = ApiTest()
        with patch.object(api, "incident", return_value=None):
            with self.assertRaisesRegex(demo.ErreurDemo, "Aucun incident"):
                self.attendre(api)

    def test_interruption_ne_devient_pas_une_decision(self):
        api = ApiTest()
        with patch.object(api, "lire", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.attendre(api)


class ChoixTest(unittest.TestCase):
    def test_entree_vide_ne_choisit_pas(self):
        entrees = iter(["", "oui", "continuer"])
        with patch.object(demo, "rendu_terminal", return_value="Avertissement"):
            choix = demo.choisir_salarie(None, None, lire=lambda _invite: next(entrees),
                                         afficher=lambda _texte: None)
        self.assertEqual(choix, "continuer")

    def test_fin_entree_n_envoie_pas_un_choix(self):
        with patch.object(demo, "rendu_terminal", return_value="Avertissement"):
            with self.assertRaisesRegex(demo.ErreurDemo, "aucun choix envoyé"):
                demo.choisir_salarie(None, None, lire=lambda _: (_ for _ in ()).throw(EOFError),
                                     afficher=lambda _texte: None)

    def test_options_par_defaut_restent_interactives(self):
        options = demo.arguments([])
        self.assertEqual(options.choix_salarie, "interactif")
        self.assertEqual(options.attente, 120)
        self.assertEqual(options.console, "http://127.0.0.1:5173")
        self.assertFalse(options.avec_mcp)
        self.assertFalse(options.avec_droits)

    def test_url_avec_chemin_est_refusee(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            demo.url_backend("http://127.0.0.1:8700/ancienne-console")

    def test_attente_bornee(self):
        for valeur in ["0", "-1", "nan", "inf", "texte"]:
            with self.subTest(valeur=valeur), self.assertRaises(argparse.ArgumentTypeError):
                demo.nombre_positif(valeur)

    def test_reception_non_confirmee_ne_devient_pas_un_succes(self):
        for reponse in [None, {}, {"session": {"id": "autre"}}]:
            with self.subTest(reponse=reponse), self.assertRaises(demo.ErreurDemo):
                demo.verifier_reception(reponse, "demo-test", "avertissement")

    def test_client_poste_expose_perte_evenement(self):
        with patch.object(demo.Backend, "evenement", return_value=None):
            with self.assertRaises(demo.ErreurDemo):
                demo.BackendControle().evenement("avertissement", "demo-test")

    def test_client_interne_expose_perte_evenement(self):
        with patch.object(demo.BoiteNoire, "evenement", return_value=None):
            with self.assertRaises(demo.ErreurDemo):
                demo.BoiteNoireControlee().evenement("appel_outil", "outil", "demo-test")

    def test_ctrl_c_renvoie_130_sans_trace_python(self):
        with patch.object(demo.Api, "verifier_sante", side_effect=KeyboardInterrupt):
            with patch("sys.stderr", new_callable=io.StringIO) as sortie:
                self.assertEqual(demo.main([]), 130)
            self.assertIn("Aucun appel retenu n'est libéré", sortie.getvalue())

    def test_backend_indisponible_arrête_la_demo(self):
        with patch.object(demo.urllib.request, "urlopen", side_effect=URLError("absent")):
            with patch("sys.stderr", new_callable=io.StringIO) as sortie:
                self.assertEqual(demo.main(["--choix-salarie", "annuler"]), 2)
        self.assertIn("Lecture impossible", sortie.getvalue())


class ParcoursSalarieTest(unittest.TestCase):
    def test_le_vrai_garde_enregistre_le_choix_sans_ecrire_la_popup(self):
        popup = demo.RACINE / "poste" / "demo" / "popup.html"
        avant = popup.read_bytes()

        class BackendMemo:
            def __init__(self):
                self.evenements = []

            def evenement(self, type, session_id, **options):
                self.evenements.append({"type": type, "details": options.get("details", {})})
                return {"session": {"id": session_id}}

        class ApiMemo:
            base = "http://127.0.0.1:8700"

            def __init__(self, backend):
                self.backend = backend

            def session(self, _session_id):
                return {"evenements": self.backend.evenements}

            def incident(self, _session_id):
                if any(e["type"] == "humain_phishing" for e in self.backend.evenements):
                    return {"id": "INC-test", "type": "humain_phishing"}
                return None

        for choix, incident_attendu in [("annuler", False), ("continuer", True)]:
            with self.subTest(choix=choix):
                backend = BackendMemo()
                with patch.object(demo, "BackendControle", return_value=backend):
                    with patch("sys.stdout", new_callable=io.StringIO) as sortie:
                        demo.jouer_salarie(
                            ApiMemo(backend), "demo-test-poste", choix,
                            console="http://127.0.0.1:5173",
                        )
                types = [e["type"] for e in backend.evenements]
                self.assertIn("avertissement", types)
                self.assertEqual("humain_phishing" in types, incident_attendu)
                if incident_attendu:
                    self.assertIn("/?incident=INC-test", sortie.getvalue())
                self.assertEqual(popup.read_bytes(), avant)


class SanteTest(unittest.TestCase):
    def verifier(self, sante):
        api = demo.Api("http://127.0.0.1:1")
        messages = []
        with patch.object(api, "lire", return_value=sante):
            api.verifier_sante(afficher=messages.append)
        return messages

    def test_sante_ok(self):
        self.assertEqual(self.verifier({"service": "dedale-backend", "statut": "ok"}), [])

    def test_anciens_journaux_incomplets_acceptes_avec_avertissement(self):
        messages = self.verifier({"service": "dedale-backend", "statut": "degrade",
                                  "journaux_anciens_incomplets": 8})
        self.assertEqual(len(messages), 1)
        self.assertIn("8 anciens journaux incomplets", messages[0])

    def test_ecriture_sqlite_en_echec_refusee(self):
        with self.assertRaises(demo.ErreurDemo):
            self.verifier({"service": "dedale-backend", "statut": "degrade",
                           "erreur": "persistance SQLite indisponible"})

    def test_autre_service_refuse(self):
        with self.assertRaises(demo.ErreurDemo):
            self.verifier({"service": "autre", "statut": "ok"})


if __name__ == "__main__":
    unittest.main()
