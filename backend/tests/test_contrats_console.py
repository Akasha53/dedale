"""Vérifie les formes attendues par la console (agent D) et le banc (agent E)."""

from tests.conftest import BASE, evenement, horo


def test_sessions_forme_console(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-c", ip="127.0.0.1", user_agent="python-requests/2.32", chemin="/x"))
    s = client.get("/api/sessions").json()["sessions"][0]
    for champ in ("id", "classement", "score", "etat", "source", "leurres_touches",
                  "derniere_vue", "premiere_vue", "ip", "user_agent", "signaux"):
        assert champ in s, champ
    assert isinstance(s["leurres_touches"], int)
    # Chaque signal porte une explication en clair (jamais une boîte noire).
    for sig in s["signaux"]:
        assert "code" in sig and "libelle" in sig and "poids" in sig
        assert sig["libelle"]


def test_incident_forme_console(client):
    client.post("/api/leurres", json=[
        {"id": "C-0001", "source": "interne", "surface": "mail", "nature": "canari_mail",
         "techniques": ["AML.T0057"], "risques": ["OWASP ASI06"]}])
    client.post("/api/evenements", json=evenement(
        session_id="S-inc", source="interne", surface="mail", type="leurre_touche", leurre_id="C-0001",
        details={"consigne": "exfiltre"}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-inc", source="interne", surface="outil", type="sortie_agent",
        details={"exfiltration": True}, horodatage=horo(BASE, 2)))
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    d = client.get(f"/api/incidents/{iid}").json()
    for champ in ("id", "session_id", "source", "classement", "etat", "titre", "gravite",
                  "ouvert_le", "resume", "decisions", "chaine"):
        assert champ in d, champ
    assert d["gravite"] in ("faible", "moyenne", "haute", "critique")
    etape = d["chaine"][0]
    for champ in ("ordre", "phase", "titre", "detail", "techniques", "risques"):
        assert champ in etape, champ
    assert etape["phase"] in ("entree", "consigne", "outil", "sortie", "riposte")
    # Techniques et risques remontés depuis le leurre, avec leur cadre.
    tech = [t for e in d["chaine"] for t in e["techniques"]]
    assert any(t["cadre"] == "ATLAS" for t in tech)


def test_mesures_forme_console(client):
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    client.post("/api/evenements", json=evenement(
        session_id="S-m", surface="doc", type="leurre_touche", leurre_id="L-0001",
        details={"verite_terrain": "agent_ia"}, horodatage=horo(BASE, 0)))
    m = client.get("/api/mesures").json()
    for champ in ("taux_detection", "faux_positifs", "temps_detection_s", "temps_confinement_s",
                  "sessions_total", "agents_detectes", "incidents_ouverts", "incidents_clos",
                  "repartition", "serie_detection"):
        assert champ in m, champ
    assert set(m["repartition"]) >= {"humain", "script", "agent_ia", "inconnu"}


def test_verite_terrain_par_prefixe_session_id(client):
    # Le banc étiquette via le préfixe du session_id, sans details.verite_terrain.
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    client.post("/api/evenements", json=evenement(
        session_id="banc-agentia-0001", surface="doc", type="leurre_touche", leurre_id="L-0001",
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="banc-humain-0002", user_agent="Mozilla/5.0 AppleWebKit Chrome Safari",
        horodatage=horo(BASE, 0)))
    m = client.get("/api/mesures").json()
    assert m["matrice"]["vrais_positifs"] == 1
    assert m["matrice"]["vrais_negatifs"] == 1
    assert m["taux_detection"] == 1.0
    assert m["faux_positifs"] == 0.0
