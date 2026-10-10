"""Le banc d'attaque (attaque/) rejoue l'agent interne détourné en mode autonome. Le vrai
backend doit classer cette session `agent_ia`, pas seulement ouvrir l'incident.

Régression mesurée le 10 octobre : 0/25 sessions « agent interne » classées en mode autonome,
alors que le canari ouvrait bien l'incident. Le banc n'utilise que la bibliothèque standard :
on l'importe tel quel et on branche son client backend sur le TestClient, sans réseau.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RACINE_ATTAQUE = Path(__file__).resolve().parents[2] / "attaque"


class _BackendTest:
    """Même interface que `banc.backend.Backend`, servie par le TestClient."""

    def __init__(self, client):
        self.client = client
        self.base = "http://testserver"
        self.disponible = True
        self.derniere_latence_ms = 0.0

    def enregistrer_leurres(self, leurres: list[dict]) -> bool:
        return self.client.post("/api/leurres", json=leurres).status_code == 200

    def emettre(self, evenement: dict) -> dict:
        return self.client.post("/api/evenements", json=evenement).json()

    def session(self, session_id: str) -> dict | None:
        rep = self.client.get(f"/api/sessions/{session_id}")
        return rep.json() if rep.status_code == 200 else None


@pytest.fixture
def banc():
    if not (RACINE_ATTAQUE / "banc").is_dir():
        pytest.skip("module attaque/ absent")
    sys.path.insert(0, str(RACINE_ATTAQUE))
    try:
        from banc import trafic
        from banc.client_ia import ClientIA
        from banc.monde import Monde
        from banc.surface import LEURRES_SEMES, SurfaceLocale
    finally:
        sys.path.remove(str(RACINE_ATTAQUE))
    return SimpleNamespace(trafic=trafic, ClientIA=ClientIA, Monde=Monde,
                           LEURRES_SEMES=LEURRES_SEMES, SurfaceLocale=SurfaceLocale)


def test_agent_interne_du_banc_classe_agent_ia(client, banc):
    backend = _BackendTest(client)
    assert backend.enregistrer_leurres(banc.LEURRES_SEMES)
    monde = banc.Monde("autonome", banc.SurfaceLocale(), backend, campagne="test")
    sid = banc.trafic.agent_interne(monde, 1, random.Random("i"),
                                    client=banc.ClientIA("simulateur"))

    sess = client.get(f"/api/sessions/{sid}").json()
    assert sess["classement"] == "agent_ia"
    signaux = {s["code"] for s in sess["signaux"] if s["present"]}
    assert "consigne_cachee_suivie" in signaux

    incidents = [i for i in client.get("/api/incidents").json()["incidents"]
                 if i["session_id"] == sid]
    assert len(incidents) == 1 and incidents[0]["type"] == "interne_canari"

    matrice = client.get("/api/mesures").json()["matrice"]
    assert matrice["vrais_positifs"] == 1 and matrice["faux_negatifs"] == 0
