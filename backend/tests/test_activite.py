"""Fil des agents : GET /api/activite et message WS `activite`."""

from tests import scenario_jury
from tests.conftest import BASE, evenement, horo


def test_fil_du_scenario_jury(client):
    scenario_jury.jouer(client, "jury-fil", "reprendre")
    fil = client.get("/api/activite").json()["activite"]
    fil = [a for a in fil if a["session_id"] == "jury-fil"]
    # Du plus récent au plus ancien ; l'annonce d'intention n'est pas un appel.
    assert [(a["outil"], a["verdict"], a["etape"]) for a in reversed(fil)] == [
        ("chercher_document", "autorise", "appel"),
        ("lire_coffre", "retenu", "appel"),
        ("lire_coffre", "autorise", "issue"),
        ("envoyer_rapport", "retenu", "appel"),
        ("envoyer_rapport", "refuse", "issue"),
        ("envoyer_rapport", "refuse", "issue"),
    ]
    inc = client.get("/api/incidents").json()["incidents"][0]
    for a in fil:
        assert a["agent"] == "orbis-assistant"
        assert a["incident_id"] == inc["id"]
        assert a["raison"] and a["heure"]
    retenu = next(a for a in fil if a["outil"] == "lire_coffre" and a["verdict"] == "retenu")
    assert retenu["droit"] == "coffre:lire" and "absent du jeton" in retenu["raison"]


def test_limite(client):
    scenario_jury.jouer(client, "jury-lim", "couper")
    assert len(client.get("/api/activite?limite=2").json()["activite"]) == 2
    assert client.get("/api/activite?limite=0").status_code == 422
    assert client.get("/api/activite?limite=501").status_code == 422


def test_verdict_deduit_pour_un_ancien_evenement(client):
    """Sans `details.verdict` (ancienne passerelle) : verdict déduit, raison en clair."""
    client.post("/api/evenements", json=evenement(
        session_id="S-ancien", source="interne", surface="outil", type="appel_outil",
        outil="lire_mail", details={"scope_requis": "mail:lire", "scope_dans_jeton": True},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-ancien", source="interne", surface="outil", type="appel_outil",
        outil="executer_paiement", details={"violation_droits": {
            "outil": "executer_paiement", "scope_requis": "paiement:executer"}},
        horodatage=horo(BASE, 1)))
    fil = client.get("/api/activite").json()["activite"]
    assert [(a["outil"], a["verdict"]) for a in fil] == [
        ("executer_paiement", "refuse"), ("lire_mail", "autorise")]
    assert fil[0]["raison"] == "droit paiement:executer absent du jeton, appel bloqué"
    assert fil[0]["incident_id"] is not None and fil[1]["agent"] is None


def test_surface_externe_hors_du_fil(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-ext", source="externe", surface="mcp", type="appel_outil", outil="lister"))
    assert client.get("/api/activite").json()["activite"] == []


def test_meme_objet_pousse_sur_le_ws(client):
    with client.websocket_connect("/ws") as ws:
        client.post("/api/evenements", json=evenement(
            session_id="S-ws", source="interne", surface="outil", type="appel_outil",
            outil="lire_mail", details={"scope_requis": "mail:lire", "verdict": "autorise",
                                        "raison": "droit mail:lire dans le jeton"}))
        for _ in range(10):
            message = ws.receive_json()
            if message["type"] == "activite":
                break
        assert message["type"] == "activite"
    attendu = client.get("/api/activite").json()["activite"][0]
    assert message["donnees"] == attendu
