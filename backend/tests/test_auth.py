"""Authentification : trois jetons, refus par défaut, décisions réservées à l'analyste.

Le premier test rejoue le `curl` du testeur : sans jeton, un virement de 380 000 € retenu par
les quatre yeux avait été accordé sous le nom de Marc.
"""

from __future__ import annotations

import logging
import os
import re
import stat

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import auth
from app.main import app

from .conftest import BASE, evenement, horo, jeton

SID = "poste-mac-virement"


def _client_nu() -> TestClient:
    """Client sans l'en-tête que pose la fixture : il ne présente que ce qu'on lui donne."""
    c = TestClient(app)
    c.event_hooks = {"request": [], "response": []}
    return c


def _virement_retenu(client) -> str:
    """Le salarié demande un virement de 380 000 € : le geste attend les quatre yeux."""
    entete = jeton("poste")
    client.post("/api/evenements", headers=entete, json=evenement(
        session_id=SID, source="humain", surface="poste", type="contexte",
        details={"contexte": "Marc prépare un virement fournisseur"}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", headers=entete, json=evenement(
        session_id=SID, source="humain", surface="poste", type="avertissement",
        details={"categorie": "phishing", "choix": "continuer", "contexte": "virement",
                 "message": "Virement de 380 000 € vers un IBAN inconnu.", "geste": "virement",
                 "quatre_yeux": "demande", "demande_id": "v380", "delai_s": 90,
                 "gravite": "critique"},
        horodatage=horo(BASE, 2)))
    incidents = client.get("/api/incidents", headers=jeton("analyste")).json()["incidents"]
    return next(i["id"] for i in incidents if i["session_id"] == SID)


def _decisions(client, iid: str) -> list[dict]:
    return client.get(f"/api/incidents/{iid}", headers=jeton("analyste")).json()["decisions"]


# ------------------------------------------------------------------ le curl du testeur
def test_curl_sans_jeton_n_accorde_plus_rien():
    with _client_nu() as c:
        iid = _virement_retenu(c)
        r = c.post(f"/api/incidents/{iid}/decision",
                   json={"action": "accorder", "analyste": "Marc"})
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert _decisions(c, iid) == []


@pytest.mark.parametrize("role", ["poste", "passerelle"])
def test_decision_avec_un_jeton_de_machine_refusee(role):
    with _client_nu() as c:
        iid = _virement_retenu(c)
        r = c.post(f"/api/incidents/{iid}/decision", headers=jeton(role),
                   json={"action": "accorder", "analyste": "Marc"})
        assert r.status_code == 403
        assert _decisions(c, iid) == []


def test_decision_avec_le_jeton_analyste_signee_du_nom():
    with _client_nu() as c:
        iid = _virement_retenu(c)
        r = c.post(f"/api/incidents/{iid}/decision", headers=jeton("analyste"),
                   json={"action": "refuser", "analyste": "Marc", "motif": "IBAN inconnu."})
        assert r.status_code == 200
        derniere = _decisions(c, iid)[-1]
        assert derniere["action"] == "refuser" and derniere["analyste"] == "Marc"


def test_faux_jeton_et_mauvais_schema_refuses():
    with _client_nu() as c:
        iid = _virement_retenu(c)
        vrai = auth.chemin_jeton("analyste").read_text().strip()
        for entete in ({"Authorization": "Bearer " + vrai[:-1] + "x"},
                       {"Authorization": "Basic " + vrai},
                       {"Authorization": vrai},
                       {"Authorization": "Bearer "}):
            r = c.post(f"/api/incidents/{iid}/decision", headers=entete,
                       json={"action": "accorder", "analyste": "Marc"})
            assert r.status_code == 401, entete
        assert _decisions(c, iid) == []


def test_corps_mal_forme_sans_jeton_donne_401_pas_422():
    with _client_nu() as c:
        r = c.post("/api/incidents/INC-1/decision", content=b"{pas du json",
                   headers={"content-type": "application/json"})
        assert r.status_code == 401


# ------------------------------------------------------------------ toutes les routes
def _chemin_concret(gabarit: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", gabarit)


def _routes_api() -> list[tuple[str, str]]:
    """Toutes les routes de l'API, routeurs inclus, telles que les publie OpenAPI."""
    return sorted((methode.upper(), chemin)
                  for chemin, operations in app.openapi()["paths"].items()
                  for methode in operations if chemin.startswith("/api/"))


# Routes qui décident : un jeton de machine n'y entre jamais.
DECISIONS = {
    ("POST", "/api/incidents/{iid}/decision"), ("POST", "/api/incidents/{iid}/identite"),
    ("POST", "/api/incidents/{iid}/remediation"), ("POST", "/api/incidents/{iid}/retirer-droit"),
    ("POST", "/api/politiques"), ("DELETE", "/api/politiques/{rid}"),
    ("POST", "/api/politiques/analyser"),
}
# Routes ouvertes à une machine ; toute autre route n'admet que l'analyste.
MACHINES = {
    ("POST", "/api/evenements"): {"passerelle", "poste"},
    ("POST", "/api/leurres"): {"passerelle"},
    ("GET", "/api/sessions/{sid}"): {"analyste", "passerelle"},
    ("POST", "/api/politiques/evaluer"): {"passerelle"},
    ("POST", "/api/resistance/campagnes"): {"passerelle"},
    ("POST", "/api/agents/poste"): {"poste"},
    ("GET", "/api/relecteur/demandes/{demande_id}"): {"analyste", "poste"},
    ("GET", "/api/poste/decisions/{session_id}"): {"analyste", "poste"},
}


def test_toute_route_de_l_api_refuse_sans_jeton_sauf_la_sante():
    routes = _routes_api()
    assert DECISIONS <= set(routes) and set(MACHINES) <= set(routes)
    with _client_nu() as c:
        for methode, gabarit in routes:
            r = c.request(methode, _chemin_concret(gabarit))
            if (methode, gabarit) in auth.OUVERTES:
                assert r.status_code == 200, gabarit
            else:
                assert r.status_code == 401, f"{methode} {gabarit} : {r.status_code}"
    assert len(routes) > 40


def test_chaque_identite_n_ouvre_que_ses_routes():
    """Requête réelle par route et par jeton : 403 si l'identité n'est pas admise. Les routes
    qui décident n'admettent que l'analyste ; une route sans déclaration aussi."""
    with _client_nu() as c:
        for methode, gabarit in _routes_api():
            if (methode, gabarit) in auth.OUVERTES:
                continue
            attendus = MACHINES.get((methode, gabarit),
                                    {"validateur"} if gabarit.startswith("/api/validation/")
                                    else {"analyste"})
            if (methode, gabarit) in DECISIONS:
                assert attendus == {"analyste"}
            for role in auth.ROLES:
                r = c.request(methode, _chemin_concret(gabarit), headers=jeton(role), json={})
                admis = r.status_code not in (401, 403)
                assert admis == (role in attendus), f"{role} {methode} {gabarit} : {r.status_code}"


def test_le_poste_ne_lit_pas_les_incidents_des_autres():
    with _client_nu() as c:
        _virement_retenu(c)
        assert c.get("/api/incidents", headers=jeton("poste")).status_code == 403
        assert c.get("/api/sessions", headers=jeton("passerelle")).status_code == 403
        r = c.get(f"/api/poste/decisions/{SID}", headers=jeton("poste"))
        assert r.status_code == 200
        incidents = r.json()["incidents"]
        assert len(incidents) == 1 and incidents[0]["session_id"] == SID
        assert set(incidents[0]) == {"id", "session_id", "statut", "decisions"}
        assert c.get("/api/poste/decisions/autre", headers=jeton("poste")).json() == {"incidents": []}


# ------------------------------------------------------------------ espace de validation
def test_validateur_seul_sur_un_geste_metier_et_jamais_dans_la_console():
    """Une route de l'espace /validation déclare auth.VALIDATEUR : l'analyste y reçoit 403, et
    le validateur reçoit 403 partout dans la console du SOC."""
    from fastapi import FastAPI

    espace = FastAPI()

    @espace.post("/api/validation/gestes/{gid}", dependencies=[auth.VALIDATEUR])
    async def confirmer(gid: str):
        return {"geste": gid, "confirme": True}

    c = TestClient(espace)
    c.event_hooks = {"request": [], "response": []}
    assert c.post("/api/validation/gestes/g1").status_code == 401
    for role in ("analyste", "passerelle", "poste"):
        assert c.post("/api/validation/gestes/g1", headers=jeton(role)).status_code == 403, role
    assert c.post("/api/validation/gestes/g1", headers=jeton("validateur")).json()["confirme"]
    with _client_nu() as console:
        iid = _virement_retenu(console)
        for methode, chemin in (("GET", "/api/incidents"), ("GET", f"/api/incidents/{iid}"),
                                ("POST", f"/api/incidents/{iid}/decision")):
            r = console.request(methode, chemin, headers=jeton("validateur"),
                                json={"action": "accorder", "analyste": "Marc"})
            assert r.status_code == 403, chemin
        assert _decisions(console, iid) == []
        with pytest.raises(WebSocketDisconnect):
            with console.websocket_connect("/ws", headers=jeton("validateur")):
                pass


# ------------------------------------------------------------------ flux temps réel
def test_flux_ws_reserve_a_l_analyste():
    with _client_nu() as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws"):
                pass
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws", headers=jeton("poste")):
                pass
        with c.websocket_connect("/ws", headers=jeton("analyste")) as ws:
            ws.send_text("ping")


# ------------------------------------------------------------------ journal et mesures
def test_refus_journalises_sans_le_jeton_et_comptes(caplog):
    poste = auth.chemin_jeton("poste").read_text().strip()
    with _client_nu() as c, caplog.at_level(logging.WARNING, logger="dedale.auth"):
        iid = _virement_retenu(c)
        c.post(f"/api/incidents/{iid}/decision", json={"action": "accorder", "analyste": "Marc"})
        c.post(f"/api/incidents/{iid}/decision", headers=jeton("poste"),
               json={"action": "accorder", "analyste": "Marc"})
        mesures = c.get("/api/mesures", headers=jeton("analyste")).json()
    refus = mesures["acces_refuses"]
    assert refus["refus_401"] == 1 and refus["refus_403"] == 1
    assert refus["derniers"][0]["code"] == 403 and refus["derniers"][0]["identite"] == "poste"
    assert "Accès refusé 401" in caplog.text and "Accès refusé 403" in caplog.text
    assert poste not in caplog.text and poste not in str(refus)


# ------------------------------------------------------------------ jetons sur disque
def test_jetons_hors_depot_en_600_dans_un_dossier_en_700():
    dossier = auth.dossier()
    assert stat.S_IMODE(os.stat(dossier).st_mode) == 0o700
    valeurs = set()
    for role in auth.ROLES:
        chemin = auth.chemin_jeton(role)
        assert stat.S_IMODE(os.stat(chemin).st_mode) == 0o600
        valeurs.add(chemin.read_text().strip())
    assert len(valeurs) == len(auth.ROLES) == 4 and all(len(v) >= 32 for v in valeurs)
    assert "dedale-jetons-" in str(dossier)  # les tests n'écrivent jamais dans ~/.config


def test_preparer_garde_les_jetons_existants():
    avant = {r: auth.chemin_jeton(r).read_text() for r in auth.ROLES}
    auth.preparer()
    assert {r: auth.chemin_jeton(r).read_text() for r in auth.ROLES} == avant


def test_jetons_identiques_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("DEDALE_JETONS", str(tmp_path / "jetons"))
    try:
        auth.preparer()
        meme = auth.chemin_jeton("analyste").read_text()
        auth.chemin_jeton("poste").write_text(meme)
        with pytest.raises(RuntimeError):
            auth.preparer()
    finally:
        monkeypatch.undo()
        auth.preparer()  # recharge les jetons du dossier des tests
