"""Campagne complète : cohérence, reproductibilité, et chaîne HTTP vers le backend."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from banc import evenement as ev
import campagne


def test_campagne_autonome_coherente_sans_backend():
    res = campagne.lancer(n=3, mode="autonome", base_backend="http://127.0.0.1:9")
    assert res["mode"] == "autonome"
    assert res["stats"]["anomalies"] == []
    par = res["stats"]["par_verite"]
    assert par[ev.HUMAIN]["sessions"] == 3
    assert par[ev.HUMAIN]["sessions_avec_leurre"] == 0
    assert par[ev.SCRIPT]["sessions_avec_leurre"] == 0
    assert par[ev.AGENT_IA]["sessions_avec_leurre"] == 3
    assert par[ev.AGENT_INTERNE]["sessions_avec_leurre"] == 3


def _signature(manifeste: dict, campagne_id: str) -> list:
    """Structure du manifeste sans l'horodatage ni l'identifiant de campagne."""
    out = []
    for sid in sorted(manifeste):
        for e in manifeste[sid]:
            out.append((sid.replace(campagne_id, "X"), e["type"], e["chemin"], e["outil"],
                        e["leurre_id"], e["details"].get("delai_avant_s")))
    return out


def test_reproductible_a_graine_fixe():
    a = campagne.lancer(n=4, mode="autonome", graine=1337, base_backend="http://127.0.0.1:9")
    b = campagne.lancer(n=4, mode="autonome", graine=1337, base_backend="http://127.0.0.1:9")
    # même trafic, mais deux campagnes distinctes : aucun session_id partagé
    assert a["campagne"] != b["campagne"]
    assert not set(a["manifeste"]) & set(b["manifeste"])
    assert _signature(a["manifeste"], a["campagne"]) == _signature(b["manifeste"], b["campagne"])


class _Collecteur(BaseHTTPRequestHandler):
    recus: list = []

    def _repondre(self, code, charge):
        corps = json.dumps(charge).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        taille = int(self.headers.get("Content-Length", 0))
        charge = json.loads(self.rfile.read(taille) or "null")
        if self.path == "/api/leurres":
            return self._repondre(200, {"enregistres": len(charge)})
        if self.path == "/api/evenements":
            _Collecteur.recus.append(charge)
            return self._repondre(200, {
                "session": {"id": charge["session_id"], "classement": "inconnu",
                            "score": 0.0, "etat": "active"},
                "consigne": "aucune"})
        self._repondre(404, {})

    def do_GET(self):
        if self.path == "/api/mesures":
            return self._repondre(200, {"taux_detection": 1.0, "faux_positifs": 0.0})
        if self.path == "/api/sessions":
            return self._repondre(200, [])
        self._repondre(404, {})

    def log_message(self, *a):  # silence
        pass


def test_chaine_http_vers_backend_reel():
    _Collecteur.recus = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Collecteur)
    port = serveur.server_address[1]
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        res = campagne.lancer(n=2, mode="autonome",
                              base_backend=f"http://127.0.0.1:{port}")
    finally:
        serveur.shutdown()

    assert res["backend_ok"] is True
    assert res["mesures"] == {"taux_detection": 1.0, "faux_positifs": 0.0}
    # chaque événement du manifeste a bien été posté, étiqueté de sa vérité
    total = sum(len(v) for v in res["manifeste"].values())
    assert len(_Collecteur.recus) == total
    assert all("verite_terrain" in e["details"] for e in _Collecteur.recus)
    verites_postees = {ev.verite_depuis_session(e["session_id"]) for e in _Collecteur.recus}
    assert verites_postees == set(ev.VERITES)
