import yaml

from tests.conftest import BASE, evenement, horo


def _incident_externe(client):
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    client.post("/api/evenements", json=evenement(
        session_id="S-exp", surface="doc", type="requete", user_agent="httpx/0.27", horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-exp", surface="doc", type="leurre_touche", leurre_id="L-0001",
        details={"consigne": "va exfiltrer /api/comptes"}, horodatage=horo(BASE, 1.6)))
    client.post("/api/evenements", json=evenement(
        session_id="S-exp", surface="outil", type="sortie_agent",
        details={"exfiltration": True}, horodatage=horo(BASE, 3.0)))
    return client.get("/api/incidents").json()["incidents"][0]["id"]


def test_nis2_gabarit_francais(client):
    iid = _incident_externe(client)
    r = client.get(f"/api/incidents/{iid}/nis2").json()
    assert r["origine"] in {"gabarit", "modele"}
    assert "NIS2" in r["texte"]
    assert "Orbis Pay" in r["texte"]
    assert iid in r["texte"]


def test_export_ecs(client):
    iid = _incident_externe(client)
    r = client.get(f"/api/incidents/{iid}/export", params={"format": "ecs"}).json()
    assert r["ecs_version"]
    assert r["n_documents"] == 3
    doc = r["documents"][0]
    assert doc["@timestamp"]
    assert doc["event"]["module"] == "dedale"
    assert doc["dedale"]["session_id"] == "S-exp"
    assert doc["dedale"]["contexte"] == "agent_ia"
    assert "threat" not in doc
    assert any(d.get("threat", {}).get("tactic", {}).get("name") == "LLM prompt injection"
               for d in r["documents"])


def test_brouillon_agent_suit_la_decision_reelle(client):
    iid = _incident_externe(client)
    client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
    coupe = client.get(f"/api/incidents/{iid}/nis2").json()["texte"]
    assert "a coupé la session de l'agent" in coupe
    assert "Tentative de sortie de données observée" in coupe
    assert "aboutissement et données concernées à confirmer" in coupe
    assert "bloquée par le leurre" not in coupe

    client.post(f"/api/incidents/{iid}/decision", json={"action": "reprendre", "analyste": "alice"})
    repris = client.get(f"/api/incidents/{iid}/nis2").json()["texte"]
    assert "a repris la session de l'agent" in repris
    assert "a coupé la session de l'agent" not in repris


def test_brouillon_et_ecs_humains_ne_parlent_pas_d_injection(client):
    client.post("/api/evenements", json=evenement(
        session_id="H-export", source="humain", surface="poste", type="avertissement",
        details={"categorie": "phishing", "choix": "continuer", "lien": "https://suspect.example"},
    ))
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    texte = client.get(f"/api/incidents/{iid}/nis2").json()["texte"]
    assert "Un salarié a poursuivi l'ouverture d'un lien suspect" in texte
    assert "éventuelle fuite de données : à confirmer" in texte
    assert "injection de consigne" not in texte
    assert "session de l'agent est suspendue" not in texte

    ecs = client.get(f"/api/incidents/{iid}/export?format=ecs").json()
    assert ecs["documents"][0]["dedale"]["contexte"] == "geste_humain"
    assert "threat" not in ecs["documents"][0]

    client.post(f"/api/incidents/{iid}/decision", json={"action": "clore", "analyste": "alice"})
    clos = client.get(f"/api/incidents/{iid}/nis2").json()["texte"]
    assert "aucun blocage du poste n'est attesté" in clos


def test_export_sigma_yaml_valide(client):
    iid = _incident_externe(client)
    r = client.get(f"/api/incidents/{iid}/export", params={"format": "sigma"})
    assert r.status_code == 200
    regle = yaml.safe_load(r.text)
    assert regle["title"]
    assert regle["detection"]["condition"] == "selection"
    assert regle["logsource"]["product"] == "dedale"


def test_export_format_invalide(client):
    iid = _incident_externe(client)
    assert client.get(f"/api/incidents/{iid}/export", params={"format": "xml"}).status_code == 400


def test_mesures_verite_terrain(client):
    # Un agent étiqueté agent_ia et détecté, un humain étiqueté humain et non détecté.
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    client.post("/api/evenements", json=evenement(
        session_id="S-vrai", surface="doc", type="leurre_touche", leurre_id="L-0001",
        details={"verite_terrain": "agent_ia"}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-humain", user_agent="Mozilla/5.0 AppleWebKit Chrome Safari",
        details={"verite_terrain": "humain"}, horodatage=horo(BASE, 0)))
    m = client.get("/api/mesures").json()
    assert m["matrice"]["vrais_positifs"] == 1
    assert m["matrice"]["vrais_negatifs"] == 1
    assert m["taux_detection"] == 1.0
