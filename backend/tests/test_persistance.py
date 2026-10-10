"""Un redémarrage recharge le journal et permet de poursuivre les mêmes incidents."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import ancrage, main
from app.store import Store
from tests.conftest import BASE, evenement, horo


def _instantane(client, incident_id):
    return {
        "leurres": client.get("/api/leurres").json(),
        "sessions": client.get("/api/sessions").json(),
        "agents": client.get("/api/agents").json(),
        "incidents": client.get("/api/incidents").json(),
        "detail": client.get(f"/api/incidents/{incident_id}").json(),
        "session": client.get("/api/sessions/S-reprise").json(),
        "mesures": client.get("/api/mesures").json(),
        "ecs": client.get(f"/api/incidents/{incident_id}/export?format=ecs").json(),
    }


def test_redemarrage_recharge_tout_et_permet_de_continuer(monkeypatch):
    with TestClient(main.app) as client:
        assert client.post("/api/leurres", json=[{
            "id": "C-REPRISE", "source": "interne", "surface": "doc",
            "nature": "canari_document", "emplacement": "/docs/reprise",
        }]).status_code == 200
        droits = {
            "tache": "résumer un contrat", "accordes": ["document:lire", "contact:exporter"],
            "necessaires": ["document:lire"], "jeton": ["document:lire"],
        }
        assert client.post("/api/evenements", json=evenement(
            session_id="S-reprise", source="interne", surface="doc", type="entree_agent",
            details={"droits": droits}, horodatage=horo(BASE, 0),
        )).status_code == 200
        client.post("/api/evenements", json=evenement(
            session_id="S-reprise", source="interne", surface="doc", type="leurre_touche",
            leurre_id="C-REPRISE", horodatage=horo(BASE, 1),
        ))
        client.post("/api/evenements", json=evenement(
            session_id="S-reprise", source="interne", surface="outil", type="sortie_agent",
            details={"exfiltration": True}, horodatage=horo(BASE, 2),
        ))
        iid = client.get("/api/incidents").json()["incidents"][0]["id"]
        assert client.get("/api/sessions/S-reprise").json()["etat"] == "suspendue"
        assert client.post(f"/api/incidents/{iid}/decision", json={
            "action": "couper", "analyste": "alice",
        }).status_code == 200
        avant = _instantane(client, iid)
        assert avant["session"]["etat"] == "coupee"
        assert avant["detail"]["decisions"][0]["action"] == "couper"

    nouveau = Store()
    monkeypatch.setattr(main, "store", nouveau)
    with TestClient(main.app) as client:
        assert _instantane(client, iid) == avant
        assert client.get("/api/sante").json()["statut"] == "ok"
        assert client.post(f"/api/incidents/{iid}/decision", json={
            "action": "reprendre", "analyste": "bob",
        }).status_code == 200
        assert client.post("/api/evenements", json=evenement(
            session_id="S-reprise", source="interne", surface="outil", type="appel_outil",
            details={"scope_requis": "document:lire"}, horodatage=horo(BASE, 3),
        )).status_code == 200
        apres = _instantane(client, iid)
        assert len(apres["incidents"]["incidents"]) == 1
        assert apres["session"]["etat"] == "active"
        assert [e["id"] for e in apres["session"]["evenements"]] == [1, 2, 3, 4]
        assert [d["action"] for d in apres["detail"]["decisions"]] == ["couper", "reprendre"]
        assert apres["agents"]["agents"][0]["droits"]["utilises"] == ["document:lire"]

    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        assert _instantane(client, iid) == apres

    from app import config
    with sqlite3.connect(config.CHEMIN_DB) as conn:
        assert conn.execute(
            "SELECT touches FROM leurres WHERE id = ?", ("C-REPRISE",)
        ).fetchone()[0] == 1


def test_redemarrage_conserve_choix_humain_sans_couper_poste(monkeypatch):
    with TestClient(main.app) as client:
        client.post("/api/evenements", json=evenement(
            session_id="H-reprise", source="humain", surface="poste", type="avertissement",
            details={"categorie": "phishing", "choix": "annuler"}, horodatage=horo(BASE, 0),
        ))
        client.post("/api/evenements", json=evenement(
            session_id="H-reprise", source="humain", surface="poste", type="avertissement",
            details={"categorie": "phishing", "choix": "continuer"}, horodatage=horo(BASE, 1),
        ))
        iid = client.get("/api/incidents").json()["incidents"][0]["id"]
        assert client.post(f"/api/incidents/{iid}/decision", json={
            "action": "couper", "analyste": "alice",
        }).status_code == 400
        assert client.post(f"/api/incidents/{iid}/decision", json={
            "action": "clore", "analyste": "alice",
        }).status_code == 200
        avant = client.get("/api/incidents/" + iid).json()
        mesures = client.get("/api/mesures").json()["gestes_humains"]
        assert mesures["arretes"] == 1 and mesures["passes_outre"] == 1
        assert client.get("/api/sessions/H-reprise").json()["etat"] == "active"

    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        assert client.get("/api/incidents/" + iid).json() == avant
        assert client.get("/api/mesures").json()["gestes_humains"] == mesures
        assert client.get("/api/sessions/H-reprise").json()["etat"] == "active"


def test_base_illisible_interrompt_le_demarrage(monkeypatch):
    with TestClient(main.app) as client:
        client.post("/api/evenements", json=evenement(session_id="S-corrupt"))

    from app import config
    with sqlite3.connect(config.CHEMIN_DB) as conn:
        conn.execute("UPDATE sessions SET etat_json = ? WHERE id = ?", ("{json tronqué", "S-corrupt"))
    monkeypatch.setattr(main, "store", Store())
    with pytest.raises(RuntimeError, match="Impossible de recharger la base Dédale"):
        with TestClient(main.app):
            pass
    assert config.CHEMIN_DB.exists()


def test_ancienne_base_sans_etat_complet_est_rejouee(monkeypatch):
    with TestClient(main.app) as client:
        client.post("/api/leurres", json=[{
            "id": "C-ANCIEN", "source": "interne", "surface": "doc",
            "nature": "canari_document", "emplacement": "/docs/ancien",
        }])
        client.post("/api/evenements", json=evenement(
            session_id="S-ancien", source="interne", surface="doc", type="leurre_touche",
            leurre_id="C-ANCIEN", horodatage=horo(BASE, 0),
        ))
        iid = client.get("/api/incidents").json()["incidents"][0]["id"]

    from app import config
    with sqlite3.connect(config.CHEMIN_DB) as conn:
        ancrage.retirer_ajout_seul(conn)  # une base d'avant l'ajout seul
        conn.execute("UPDATE sessions SET etat_json = NULL")
        conn.execute("UPDATE evenements SET leurre_nature = NULL")
        conn.execute("UPDATE leurres SET touches = 0, premier_touche = NULL, dernier_touche = NULL")
        conn.execute("UPDATE incidents SET gravite = NULL, resume = NULL")

    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        session = client.get("/api/sessions/S-ancien").json()
        assert session["etat"] == "suspendue"
        assert session["leurres_touches_ids"] == ["C-ANCIEN"]
        assert session["evenements"][0]["leurre_nature"] == "canari_document"
        assert client.get("/api/leurres").json()["leurres"][0]["touches"] == 1
        inc = client.get(f"/api/incidents/{iid}").json()
        assert inc["gravite"] and inc["resume"]


def test_ancienne_base_avec_journal_partiel_preserve_incident(monkeypatch):
    with TestClient(main.app) as client:
        client.post("/api/leurres", json=[{
            "id": "C-PARTIEL", "source": "interne", "surface": "doc",
            "nature": "canari_document", "emplacement": "/docs/partiel",
        }])
        client.post("/api/evenements", json=evenement(
            session_id="S-partiel", source="interne", surface="doc", type="entree_agent",
            horodatage=horo(BASE, 0),
        ))
        client.post("/api/evenements", json=evenement(
            session_id="S-partiel", source="interne", surface="doc", type="leurre_touche",
            leurre_id="C-PARTIEL", horodatage=horo(BASE, 1),
        ))
        iid = client.get("/api/incidents").json()["incidents"][0]["id"]
        client.post(f"/api/incidents/{iid}/decision", json={
            "action": "couper", "analyste": "alice",
        })
        chaine_initiale = client.get(f"/api/incidents/{iid}").json()["chaine"]
        client.post("/api/evenements", json=evenement(
            session_id="S-en-retard", source="humain", surface="poste", type="requete",
            horodatage=horo(BASE, 2),
        ))
        client.post("/api/evenements", json=evenement(
            session_id="S-en-retard", source="humain", surface="poste", type="avertissement",
            details={"categorie": "phishing", "choix": "annuler"}, horodatage=horo(BASE, 3),
        ))

    from app import config
    with sqlite3.connect(config.CHEMIN_DB) as conn:
        ancrage.retirer_ajout_seul(conn)  # une base d'avant l'ajout seul
        conn.execute("UPDATE sessions SET etat_json = NULL, n_evenements = 4 WHERE id = 'S-partiel'")
        conn.execute("DELETE FROM evenements WHERE session_id = 'S-partiel' AND type = 'leurre_touche'")
        conn.execute("UPDATE sessions SET etat_json = NULL, n_evenements = 1 WHERE id = 'S-en-retard'")

    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        assert client.get("/api/sante").json()["statut"] == "degrade"
        assert client.get("/api/sante").json()["journaux_anciens_incomplets"] == 2
        inc = client.get(f"/api/incidents/{iid}").json()
        assert inc["statut"] == "clos"
        assert inc["decisions"][0]["action"] == "couper"
        assert len(inc["chaine"]) == len(chaine_initiale)
        assert any(e.get("source_non_persistee") for e in inc["chaine"])
        assert client.get("/api/sessions/S-partiel").json()["etat"] == "coupee"
        assert len(client.get("/api/sessions/S-partiel").json()["evenements"]) == 1
        assert len(client.get("/api/sessions/S-en-retard").json()["evenements"]) == 2
        client.post("/api/evenements", json=evenement(
            session_id="S-partiel", source="interne", surface="outil", type="appel_outil",
            horodatage=horo(BASE, 4),
        ))
        assert any(e.get("source_non_persistee") for e in client.get(f"/api/incidents/{iid}").json()["chaine"])

    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as client:
        assert client.get(f"/api/incidents/{iid}").status_code == 200
        assert any(e.get("source_non_persistee") for e in client.get(f"/api/incidents/{iid}").json()["chaine"])
