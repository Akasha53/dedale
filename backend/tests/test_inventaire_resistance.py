"""Inventaire des agents (NIST « Identifier ») et score de résistance mesuré par le banc."""

from __future__ import annotations

from tests.conftest import BASE, evenement, horo

IDS = ["orbis-assistant", "orbis-rapprochement", "orbis-support"]


def _campagne(agent="orbis-assistant", issues=("bloque", "bloque", "ignore", "suivi"), cid="r1"):
    return {"campagne": cid, "date": "2026-10-10T21:00:00+02:00", "trafic": "synthetique",
            "graine": 7, "agents": [{"agent": agent, "essais": [
                {"contenu": f"P-0{i + 1}", "nature": "envoi_externe", "canal": "mail",
                 "outil": "envoyer_rapport", "issue": issue, "raison": "test"}
                for i, issue in enumerate(issues)]}]}


def test_trois_agents_declares_avec_leur_risque(client):
    rep = client.get("/api/agents").json()
    assert rep["agents"] == []  # la vue par session reste là, inchangée
    inv = {a["id"]: a for a in rep["inventaire"]}
    assert list(inv) == IDS
    for a in inv.values():
        assert a["declare"] and a["outils"] and a["role"]
        assert {"accordes", "utilises", "necessaires", "surplus", "inutilises", "retires"} <= set(a["droits"])
        r = a["risque"]
        assert r["niveau"] in ("faible", "moyen", "eleve")
        assert r["score"] == sum(x["points"] for x in r["raisons"])
        assert all(x["texte"] for x in r["raisons"])
        assert r["explication"].startswith("Risque ")
        assert a["derniere_activite"] is None and a["incidents"]["total"] == 0
        assert a["resistance"] is None
    tri = inv["orbis-assistant"]
    assert "coffre:lire" in tri["droits"]["surplus"]
    assert tri["risque"]["niveau"] == "eleve"
    assert "le coffre à mots de passe" in tri["risque"]["explication"]
    assert inv["orbis-support"]["risque"]["niveau"] == "moyen"


def test_activite_observee(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-sup", source="interne", surface="ticket", type="entree_agent",
        horodatage=horo(BASE, 0), details={"agent": "orbis-support"}))
    client.post("/api/evenements", json=evenement(
        session_id="S-sup", source="interne", surface="outil", type="appel_outil", outil="lire_ticket",
        horodatage=horo(BASE, 2), details={"agent": "orbis-support", "scope_requis": "ticket:lire",
                                           "parametres": {}}))
    a = client.get("/api/agents/orbis-support").json()
    assert a["sessions"] == 1 and a["appels"] == 1
    assert a["droits"]["utilises"] == ["ticket:lire"]
    assert "ticket:lire" not in a["droits"]["inutilises"]
    assert a["derniere_activite"] == horo(BASE, 2)


def test_un_incident_fait_monter_le_risque(client):
    avant = client.get("/api/agents/orbis-rapprochement").json()["risque"]
    client.post("/api/evenements", json=evenement(
        session_id="S-rap", source="interne", surface="outil", type="appel_outil",
        outil="executer_paiement", horodatage=horo(BASE, 1),
        details={"agent": "orbis-rapprochement", "parametres": {},
                 "violation_droits": {"outil": "executer_paiement", "scope_requis": "paiement:executer",
                                      "scopes_jeton": ["banque:lire"], "tache": "rapprochement"}}))
    a = client.get("/api/agents/orbis-rapprochement").json()
    assert a["incidents"]["total"] == 1 and a["incidents"]["recents_24h"] == 1
    codes = [r["code"] for r in a["risque"]["raisons"]]
    assert "incidents_recents" in codes
    assert a["risque"]["score"] > avant["score"]


def test_agent_vu_hors_registre(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-x", source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-nouveau"}))
    inv = client.get("/api/agents").json()["inventaire"]
    vu = next(a for a in inv if a["id"] == "orbis-nouveau")
    assert vu["declare"] is False and vu["sessions"] == 1


def test_agent_inconnu(client):
    assert client.get("/api/agents/personne").status_code == 404
    assert client.get("/api/agents/personne/resistance").status_code == 404


def test_resistance_sans_campagne(client):
    r = client.get("/api/agents/orbis-support/resistance").json()
    assert r["mesure"] is False and r["score"] is None
    assert r["etiquette"] == "trafic synthétique"


def test_resistance_d_une_campagne(client):
    rep = client.post("/api/resistance/campagnes", json=_campagne())
    assert rep.status_code == 201
    r = client.get("/api/agents/orbis-assistant/resistance").json()
    assert r["mesure"] is True
    assert r["etiquette"] == "trafic synthétique" and r["trafic"] == "synthetique"
    assert r["campagne"] == "r1" and r["date"] == "2026-10-10T21:00:00+02:00"
    assert r["score"] == 0.75 and r["score_pct"] == 75
    assert r["denominateurs"] == {"essais": 4, "ignores": 1, "bloques": 2, "suivis": 1, "tentes": 3}
    assert r["taux"] == {"resistance": 0.75, "blocage": 0.667, "credulite": 0.75}
    assert r["phrase"] == ("Sur 4 contenus piégés (trafic synthétique), 3 n'ont pas abouti "
                           "(dont 2 arrêtés par Dédale) et 1 a abouti.")
    assert len(r["essais"]) == 4
    # L'inventaire reprend la mesure et en tient compte dans le risque.
    a = client.get("/api/agents/orbis-assistant").json()
    assert a["resistance"]["score"] == 0.75
    assert "resistance_faible" in [x["code"] for x in a["risque"]["raisons"]]
    # Une seconde campagne devient la mesure courante, la première reste dans l'historique.
    client.post("/api/resistance/campagnes", json=_campagne(issues=("bloque",) * 4, cid="r2"))
    r = client.get("/api/agents/orbis-assistant/resistance").json()
    assert r["campagne"] == "r2" and r["score"] == 1.0
    assert [h["campagne"] for h in r["historique"]] == ["r1", "r2"]


def test_campagne_mal_formee(client):
    mauvaise = _campagne()
    mauvaise["agents"][0]["essais"][0]["issue"] = "peut-etre"
    assert client.post("/api/resistance/campagnes", json=mauvaise).status_code == 400
    reelle = _campagne()
    reelle["trafic"] = "reel"
    assert client.post("/api/resistance/campagnes", json=reelle).status_code == 400
    assert client.post("/api/resistance/campagnes", json={"campagne": "x y"}).status_code == 400
