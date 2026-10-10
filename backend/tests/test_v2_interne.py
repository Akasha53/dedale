"""V2 côté backend : incidents interne_outil_mcp (tool poisoning) et interne_droits
(moindre privilège), plus la vue /api/agents. Les formes suivent CONTRATS.md et la console."""

from tests.conftest import BASE, evenement, horo


# --------------------------------------------------------- Fonction 1 : outil MCP piégé
def _scenario_outil_mcp(client):
    client.post("/api/leurres", json=[
        {"id": "C-9F2E", "source": "interne", "surface": "outil", "nature": "outil_mcp_piege",
         "emplacement": "serveur MCP conformite-express-mcp, outil verifier_conformite",
         "description": "Outil MCP d'apparence utile dont la description cache une consigne.",
         "techniques": ["AML.T0053", "AML.T0051"], "risques": ["OWASP ASI02", "OWASP ASI06"]},
    ])
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="mail", type="entree_agent",
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="appel_outil",
        outil="verifier_conformite",
        details={"outil_mcp_suspect": True, "serveur_mcp": "conformite-express-mcp",
                 "consigne_outil": "note cachée"},
        horodatage=horo(BASE, 1.0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="leurre_touche",
        leurre_id="C-9F2E", details={"detail": "a suivi la consigne cachée de l'outil MCP"},
        horodatage=horo(BASE, 1.5)))
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="sortie_agent",
        details={"exfiltration": True}, horodatage=horo(BASE, 3.0)))


def test_incident_outil_mcp(client):
    _scenario_outil_mcp(client)
    incidents = client.get("/api/incidents").json()["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["type"] == "interne_outil_mcp"
    iid = incidents[0]["id"]
    d = client.get(f"/api/incidents/{iid}").json()
    phases = {e["phase"] for e in d["chaine"]}
    assert "consigne" in phases          # consigne cachée de la description d'outil
    assert "sortie" in phases            # tentative d'exfiltration
    # Les techniques ATLAS du canari MCP remontent dans la chaîne.
    tech = {t["id"] for e in d["chaine"] for t in e["techniques"]}
    assert "AML.T0053" in tech
    # Le compteur de touches du canari MCP est à jour.
    inv = {l["id"]: l for l in client.get("/api/leurres").json()["leurres"]}
    assert inv["C-9F2E"]["touches"] == 1
    assert inv["C-9F2E"]["nature"] == "outil_mcp_piege"


# --------------------------------------------------------- Fonction 2 : droits trop larges
_ACCORDES = [
    {"code": "mail:lire", "libelle": "Lire la boîte mail"},
    {"code": "rapport:envoyer", "libelle": "Envoyer un rapport interne"},
    {"code": "paiement:executer", "libelle": "Exécuter un virement"},
    {"code": "contact:exporter", "libelle": "Exporter la base contacts"},
    {"code": "resume:local", "libelle": "Résumer en local"},
]
_NECESSAIRES = [
    {"code": "mail:lire", "libelle": "Lire la boîte mail"},
    {"code": "resume:local", "libelle": "Résumer en local"},
    {"code": "rapport:envoyer", "libelle": "Envoyer un rapport interne"},
]


def _scenario_droits(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-dr", source="interne", surface="mail", type="entree_agent",
        details={"droits": {"tache": "resume_mails", "accordes": _ACCORDES,
                            "necessaires": _NECESSAIRES,
                            "jeton": ["mail:lire", "resume:local", "rapport:envoyer"]}},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-dr", source="interne", surface="outil", type="appel_outil",
        outil="lire_mail", details={"scope_requis": "mail:lire"}, horodatage=horo(BASE, 1)))
    client.post("/api/evenements", json=evenement(
        session_id="S-dr", source="interne", surface="outil", type="appel_outil",
        outil="executer_paiement",
        details={"violation_droits": {"outil": "executer_paiement",
                                      "scope_requis": "paiement:executer",
                                      "scopes_jeton": ["mail:lire", "resume:local", "rapport:envoyer"],
                                      "tache": "resume_mails"}},
        horodatage=horo(BASE, 2)))
    client.post("/api/evenements", json=evenement(
        session_id="S-dr", source="interne", surface="outil", type="riposte",
        details={"action": "bloquer_hors_scope", "scope_requis": "paiement:executer"},
        horodatage=horo(BASE, 2.1)))


def test_incident_droits(client):
    _scenario_droits(client)
    incidents = client.get("/api/incidents").json()["incidents"]
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["type"] == "interne_droits"
    assert inc["droits"] is not None
    # L'écart accordés / nécessaires est exposé : « l'agent avait accès à X, sa tâche non ».
    assert "paiement:executer" in inc["droits"]["surplus"]
    assert inc["droits"]["tentatives_hors_scope"][0]["scope_requis"] == "paiement:executer"


def test_api_agents(client):
    _scenario_droits(client)
    agents = client.get("/api/agents").json()["agents"]
    assert len(agents) == 1
    a = agents[0]
    assert a["session_id"] == "S-dr"
    assert a["tache"] == "resume_mails"
    # Format console : accordes / utilises / necessaires.
    assert {"accordes", "utilises", "necessaires"} <= set(a["droits"])
    assert "mail:lire" in a["droits"]["utilises"]
    # L'action refusée n'est jamais comptée comme « utilisée ».
    assert "paiement:executer" not in a["droits"]["utilises"]
    assert "paiement:executer" in a["droits"]["surplus"]


def test_session_porte_les_droits(client):
    _scenario_droits(client)
    s = next(s for s in client.get("/api/sessions").json()["sessions"] if s["id"] == "S-dr")
    assert s["droits"] is not None
    assert s["droits"]["tache"] == "resume_mails"


def test_mesures_restent_coherentes_avec_v2(client):
    _scenario_outil_mcp(client)
    _scenario_droits(client)
    m = client.get("/api/mesures").json()
    for champ in ("taux_detection", "faux_positifs", "sessions_total", "agents_detectes",
                  "incidents_ouverts", "repartition", "serie_detection"):
        assert champ in m, champ
    # Les deux sessions internes V2 n'ont pas de vérité terrain : elles n'altèrent pas le taux.
    assert m["sessions_sans_verite_terrain"] >= 2
    assert set(m["repartition"]) >= {"humain", "script", "agent_ia", "inconnu"}
