"""Bilan par campagne : deux campagnes sur un même backend, formats de
GET /api/sessions, session absente, session non classée, backend absent."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from banc import evenement as ev
from banc import rapport
import campagne

ATTENDU = {"humain": "humain", "script": "script", "agentia": "agent_ia",
           "interne": "agent_ia"}


class _BackendSimule(BaseHTTPRequestHandler):
    """Backend minimal : classe chaque session sur son préfixe, garde l'état entre
    deux campagnes, et permet de perdre ou de laisser « inconnu » une session."""

    sessions: dict = {}
    format_liste = False
    absentes: set = set()
    non_classees: set = set()

    @classmethod
    def remettre_a_zero(cls):
        cls.sessions, cls.format_liste = {}, False
        cls.absentes, cls.non_classees = set(), set()

    def _repondre(self, code, charge):
        corps = json.dumps(charge).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _classement(self, sid):
        if any(sid.endswith(s) for s in self.non_classees):
            return "inconnu"
        return ATTENDU[sid.split("-")[1]]

    def do_POST(self):
        taille = int(self.headers.get("Content-Length", 0))
        charge = json.loads(self.rfile.read(taille) or "null")
        if self.path == "/api/leurres":
            return self._repondre(200, {"enregistres": len(charge)})
        if self.path != "/api/evenements":
            return self._repondre(404, {})
        sid = charge["session_id"]
        classement = self._classement(sid)
        if not any(sid.endswith(s) for s in self.absentes):
            s = self.sessions.setdefault(sid, {"id": sid, "evenements": []})
            s["classement"], s["etat"] = classement, "active"
            n = len(s["evenements"])
            s["evenements"].append({"horodatage": charge["horodatage"],
                                    "recu_a": datetime.now().astimezone().isoformat()})
            s.setdefault("premier_vu", charge["horodatage"])
            if classement == "agent_ia" and n == 1:
                s["detecte_a"] = charge["horodatage"]
        return self._repondre(200, {"session": {"id": sid, "classement": classement,
                                                "score": 0.0, "etat": "active"},
                                    "consigne": "aucune"})

    def do_GET(self):
        abreges = [{k: v for k, v in s.items() if k != "evenements"}
                   for s in self.sessions.values()]
        if self.path == "/api/sessions":
            return self._repondre(200, abreges if self.format_liste else {"sessions": abreges})
        m = re.fullmatch(r"/api/sessions/(.+)", self.path)
        if m:
            s = self.sessions.get(m.group(1))
            return self._repondre(200, s) if s else self._repondre(404, {"detail": "inconnue"})
        if self.path == "/api/incidents":
            return self._repondre(200, {"incidents": []})
        if self.path == "/api/mesures":
            return self._repondre(200, {"sessions_total": len(self.sessions)})
        self._repondre(404, {})

    def log_message(self, *a):
        pass


@pytest.fixture
def backend():
    _BackendSimule.remettre_a_zero()
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _BackendSimule)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def test_deux_campagnes_ne_melangent_pas_leurs_sessions(backend):
    a = campagne.lancer(n=2, mode="autonome", base_backend=backend, campagne="essaia")
    b = campagne.lancer(n=2, mode="autonome", base_backend=backend, campagne="essaib")
    assert all("-essaia-" in s for s in a["manifeste"])
    assert all("-essaib-" in s for s in b["manifeste"])
    # le backend porte les deux campagnes, chaque bilan ne compte que la sienne
    assert b["mesures"]["sessions_total"] == 16
    for res in (a, b):
        bil = res["bilan"]
        assert bil["campagne"] == res["campagne"]
        assert bil["sessions_emises"] == 8 and bil["sessions_observees"] == 8
        assert bil["detection"] == {"positives_emises": 4, "detectees": 4, "taux": 1.0,
                                    "faux_negatifs": 0, "dont_absentes": 0,
                                    "dont_non_classees": 0}
        assert bil["faux_positifs"]["classees_agent_ia"] == 0
        assert bil["faux_positifs"]["negatives_emises"] == 4
        assert len(res["sessions"]) == 8
    # temps : détecté au 2e événement, latences HTTP mesurées
    assert a["bilan"]["temps"]["evenements_avant_detection"]["mediane"] == 2
    assert a["bilan"]["temps"]["latence_post_evenement_ms"]["n"] > 0


def test_ancien_format_liste_accepte(backend):
    _BackendSimule.format_liste = True
    res = campagne.lancer(n=1, mode="autonome", base_backend=backend, campagne="liste")
    assert res["bilan"]["sessions_observees"] == 4
    assert res["bilan"]["detection"]["taux"] == 1.0


def test_session_absente_compte_contre_la_detection(backend):
    _BackendSimule.absentes = {"agentia-perdue-0001"}
    res = campagne.lancer(n=2, mode="autonome", base_backend=backend, campagne="perdue")
    d = res["bilan"]["detection"]
    assert d["positives_emises"] == 4 and d["detectees"] == 3
    assert d["taux"] == 0.75
    assert d["faux_negatifs"] == 1 and d["dont_absentes"] == 1
    assert res["bilan"]["absentes"] == {"sessions": 1, "sur": 8}
    ligne = next(s for s in res["bilan"]["sessions"] if s["id"].endswith("agentia-perdue-0001"))
    assert ligne["obtenu"] == "absente"


def test_session_non_classee_ni_detectee_ni_bien_classee(backend):
    _BackendSimule.non_classees = {"interne-flou-0002", "humain-flou-0001"}
    res = campagne.lancer(n=2, mode="autonome", base_backend=backend, campagne="flou")
    bil = res["bilan"]
    assert bil["detection"]["detectees"] == 3
    assert bil["detection"]["dont_non_classees"] == 1
    # un humain « inconnu » n'est pas un faux positif, mais pas un succès non plus
    assert bil["faux_positifs"]["classees_agent_ia"] == 0
    assert bil["faux_positifs"]["dont_non_classees"] == 1
    assert bil["par_type"][ev.HUMAIN]["bien_classees"] == 1
    assert bil["non_classees"] == {"sessions": 2, "sur": 8}
    assert bil["bien_classees"] == {"sessions": 6, "sur": 8}


def test_backend_absent_donne_non_mesure(tmp_path):
    res = campagne.lancer(n=1, mode="autonome", base_backend="http://127.0.0.1:9",
                          campagne="horsligne")
    bil = res["bilan"]
    assert bil["mesure"] is False
    assert bil["detection"]["taux"] is None and bil["faux_positifs"]["taux"] is None
    texte = rapport.resume_texte(res["stats"], mode=res["mode"], client_ia=res["client_ia"],
                                 graine=res["graine"], n_par_type=1, mesures=res["mesures"],
                                 backend_ok=res["backend_ok"], campagne=res["campagne"],
                                 bilan=bil)
    assert "campagne=horsligne" in texte
    assert "non mesuré" in texte
    assert "= 0" not in texte
    chemins = campagne.ecrire_sorties(res, texte, tmp_path / "s", tmp_path / "r")
    md = chemins["rapport_md"].read_text(encoding="utf-8")
    assert "# Campagne horsligne" in md and "non mesuré" in md.lower()
    donnees = json.loads(chemins["rapport_json"].read_text(encoding="utf-8"))
    assert donnees["campagne"] == "horsligne" and "manifeste" not in donnees


def test_identifiant_de_campagne_valide():
    assert ev.campagne_depuis_session(ev.nom_session(ev.SCRIPT, 3, "abc1")) == "abc1"
    assert ev.campagne_depuis_session("banc-script-0003") is None
    assert ev.verite_depuis_session(ev.nom_session(ev.AGENT_INTERNE, 1, "x9")) == ev.AGENT_INTERNE
    with pytest.raises(ValueError):
        ev.nom_session(ev.HUMAIN, 1, "avec-tiret")
    assert re.fullmatch(r"c\d{10}[0-9a-f]{4}", ev.nouvelle_campagne())


def test_types_restreints_sans_taux_invente(backend):
    res = campagne.lancer(n=2, mode="autonome", base_backend=backend, campagne="seul",
                          types=(ev.AGENT_INTERNE,))
    bil = res["bilan"]
    assert set(res["manifeste"]) == {"banc-interne-seul-0001", "banc-interne-seul-0002"}
    assert bil["detection"]["positives_emises"] == 2
    # aucune session humain ou script émise : pas de taux de faux positifs
    assert bil["faux_positifs"]["negatives_emises"] == 0
    assert bil["faux_positifs"]["taux"] is None
    with pytest.raises(ValueError):
        campagne.lancer(n=1, mode="autonome", base_backend=backend, types=("robot",))
