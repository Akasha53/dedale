"""Correctif en un clic : POST /api/incidents/{id}/retirer-droit (moindre privilège)."""

from fastapi.testclient import TestClient

from app import main
from app.store import Store
from tests import scenario_jury
from tests.conftest import BASE, evenement, horo


def _incident(client, sid: str) -> dict:
    iid = next(i["id"] for i in client.get("/api/incidents").json()["incidents"]
               if i["session_id"] == sid)
    return client.get(f"/api/incidents/{iid}").json()


def _retirer(client, iid: str, droit: str):
    return client.post(f"/api/incidents/{iid}/retirer-droit",
                       json={"droit": droit, "analyste": "analyste-test"})


def _nouvelle_session(client, sid: str, agent: str = "orbis-assistant") -> dict:
    return client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="entree_agent",
        details={"agent": agent, "droits": {
            "tache": "rapport_paiements", "accordes": scenario_jury.ACCORDES,
            "necessaires": scenario_jury.NECESSAIRES, "jeton": scenario_jury.JETON}},
        horodatage=horo(BASE, 30))).json()


def test_droits_retirables_dans_le_detail(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    inc = _incident(client, "jury-1")
    codes = [d["code"] for d in inc["droits_retirables"]]
    assert "coffre:lire" in codes and "document:lire" not in codes
    assert next(d for d in inc["droits_retirables"] if d["code"] == "coffre:lire")["libelle"]


def test_retirer_un_droit_en_trop(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    inc = _incident(client, "jury-1")
    r = _retirer(client, inc["id"], "coffre:lire")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "coffre:lire" in [a["code"] for a in d["avant"]["accordes"]]
    assert "coffre:lire" not in [a["code"] for a in d["apres"]["accordes"]]
    assert "coffre:lire" in d["avant"]["surplus"] and "coffre:lire" not in d["apres"]["surplus"]
    assert [x["code"] for x in d["apres"]["retires"]] == ["coffre:lire"]
    assert "lire_coffre" in d["message"]
    # Maillon « correctif » dans la boîte noire de l'incident.
    assert d["maillon"]["phase"] == "correctif" and "coffre:lire" in d["maillon"]["detail"]
    apres = _incident(client, "jury-1")
    assert apres["chaine"][-1]["etape"] == "correctif"
    assert "coffre:lire" not in [x["code"] for x in apres["droits_retirables"]]
    assert apres["correctifs"][0]["analyste"] == "analyste-test"


def test_session_en_cours_et_sessions_suivantes(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    _retirer(client, _incident(client, "jury-1")["id"], "coffre:lire")
    # Même session : la réponse à l'événement suivant porte le retrait.
    rep = client.post("/api/evenements", json=evenement(
        session_id="jury-1", source="interne", surface="outil", type="appel_outil",
        outil="resumer", details={"scope_requis": "resume:local"}, horodatage=horo(BASE, 20))).json()
    assert rep["session"]["droits_retires"] == ["coffre:lire"]
    # Nouvelle session du même agent fictif : héritée dès le premier événement.
    rep = _nouvelle_session(client, "jury-2")
    assert rep["session"]["droits_retires"] == ["coffre:lire"]
    sess = client.get("/api/sessions/jury-2").json()
    assert "coffre:lire" not in [a["code"] for a in sess["droits"]["accordes"]]
    assert sess["droits"]["retires"][0]["code"] == "coffre:lire"
    # Un autre agent n'est pas touché.
    rep = _nouvelle_session(client, "autre-1", agent="orbis-compta")
    assert "droits_retires" not in rep["session"]


def test_refus(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    iid = _incident(client, "jury-1")["id"]
    assert _retirer(client, "INC-9999", "coffre:lire").status_code == 404
    r = _retirer(client, iid, "document:lire")  # nécessaire à la tâche
    assert r.status_code == 400 and "pas un droit en trop" in r.json()["detail"]
    assert _retirer(client, iid, "inconnu:droit").status_code == 400
    assert client.post(f"/api/incidents/{iid}/retirer-droit", json={}).status_code == 400
    assert _retirer(client, iid, "coffre:lire").status_code == 200
    r = _retirer(client, iid, "coffre:lire")
    assert r.status_code == 400 and "déjà retiré" in r.json()["detail"]


def test_refus_sur_un_geste_humain(client):
    client.post("/api/evenements", json=evenement(
        session_id="poste-1", source="humain", surface="poste", type="avertissement",
        details={"categorie": "secret", "choix": "continuer"}))
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    r = _retirer(client, iid, "coffre:lire")
    assert r.status_code == 400 and "agent interne" in r.json()["detail"]


def test_synthese_mentionne_le_correctif(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    iid = _incident(client, "jury-1")["id"]
    _retirer(client, iid, "coffre:lire")
    synth = client.get(f"/api/incidents/{iid}/synthese").json()
    assert "Le droit coffre:lire a ensuite été retiré à l’agent." in synth["phrases"][-1]["texte"]
    assert synth["correctif_suggere"] is None  # déjà appliqué


def test_retrait_survit_au_redemarrage(monkeypatch):
    with TestClient(main.app) as client:
        scenario_jury.jouer(client, "jury-1", "couper")
        _retirer(client, _incident(client, "jury-1")["id"], "coffre:lire")
    # Arrêt normal : la file d'écriture est vidée. Un Store neuf ne connaît que la base.
    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        inc = _incident(client, "jury-1")
        assert inc["chaine"][-1]["etape"] == "correctif"
        assert inc["droits"]["retires"][0]["code"] == "coffre:lire"
        rep = _nouvelle_session(client, "jury-apres")
        assert rep["session"]["droits_retires"] == ["coffre:lire"]
        fil = client.get("/api/activite").json()["activite"]
        assert any(a["session_id"] == "jury-1" for a in fil)
