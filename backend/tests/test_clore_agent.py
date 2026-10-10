"""« clore » sur un incident d'agent : le dossier se ferme, la session ne bouge pas."""

from tests.conftest import BASE, evenement, horo


def _refus_hors_droits(client, sid: str) -> str:
    """Action hors du jeton de tâche, refusée d'office par la passerelle."""
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="executer_paiement",
        details={"parametres": {}, "verdict": "refuse",
                 "violation_droits": {"outil": "executer_paiement", "scope_requis": "paiement:executer",
                                      "scopes_jeton": ["mail:lire"], "tache": "resume_mails"}},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="riposte", outil="executer_paiement",
        details={"action": "bloquer_hors_scope", "scope_requis": "paiement:executer", "jeton_revoque": True},
        horodatage=horo(BASE, 0.01)))
    return next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)


def test_clore_un_refus_d_office(client):
    iid = _refus_hors_droits(client, "S-refus")
    avant = client.get("/api/sessions/S-refus").json()["etat"]
    r = client.post(f"/api/incidents/{iid}/decision", json={"action": "clore", "analyste": "alice"})
    assert r.status_code == 200, r.text
    inc = client.get(f"/api/incidents/{iid}").json()
    assert inc["statut"] == "clos"
    assert [d["action"] for d in inc["decisions"]] == ["clore"]
    assert client.get("/api/sessions/S-refus").json()["etat"] == avant
