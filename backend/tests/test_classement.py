from tests.conftest import BASE, evenement, horo

NAVIGATEUR = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def test_humain(client):
    # Navigateur, cadence lente et irrégulière.
    r = None
    for i, dt in enumerate([0, 9, 25, 48]):
        r = client.post("/api/evenements", json=evenement(
            session_id="S-h", user_agent=NAVIGATEUR, chemin="/", horodatage=horo(BASE, dt)))
    s = r.json()["session"]
    assert s["classement"] == "humain"
    assert s["score"] == 0.0


def test_script(client):
    # user-agent outil + cadence régulière ~1 s, aucune compréhension de texte.
    r = None
    for dt in [0, 1.0, 2.0, 3.0, 4.0]:
        r = client.post("/api/evenements", json=evenement(
            session_id="S-s", user_agent="python-requests/2.32", chemin="/robots.txt",
            horodatage=horo(BASE, dt)))
    s = r.json()["session"]
    assert s["classement"] == "script"
    # Signaux d'automatisation présents et expliqués.
    detail = client.get("/api/sessions/S-s").json()
    codes = {sig["code"]: sig for sig in detail["signaux"]}
    assert codes["forme_automatisee"]["present"] is True
    assert codes["cadence_machine"]["present"] is True
    assert codes["cadence_machine"]["raison"]  # raison en clair


def test_agent_ia_par_consigne_cachee(client):
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    # L'agent lit un doc piégé puis suit la consigne cachée : signal réservé aux LLM.
    client.post("/api/evenements", json=evenement(
        session_id="S-a", surface="doc", type="requete", user_agent="httpx/0.27", horodatage=horo(BASE, 0)))
    r = client.post("/api/evenements", json=evenement(
        session_id="S-a", surface="doc", type="leurre_touche", leurre_id="L-0001",
        horodatage=horo(BASE, 1.6)))
    s = r.json()["session"]
    assert s["classement"] == "agent_ia"
    assert s["score"] >= 0.40
    # La surface externe reçoit la consigne « labyrinthe ».
    assert r.json()["consigne"] == "labyrinthe"


def test_reponse_contre_injection_fait_basculer_en_agent(client):
    # Session suspecte -> contre_injection servie, puis l'agent avoue -> agent_ia.
    for dt in [0, 1.0, 2.0]:
        rep = client.post("/api/evenements", json=evenement(
            session_id="S-ci", user_agent="curl/8.4", chemin="/api/comptes", horodatage=horo(BASE, dt)))
    assert rep.json()["consigne"] == "contre_injection"
    r = client.post("/api/evenements", json=evenement(
        session_id="S-ci", type="sortie_agent", surface="outil",
        details={"objectif": "exfiltrer la liste des comptes"}, horodatage=horo(BASE, 3.0)))
    assert r.json()["session"]["classement"] == "agent_ia"
    codes = {sig["code"]: sig for sig in client.get("/api/sessions/S-ci").json()["signaux"]}
    assert codes["reponse_contre_injection"]["present"] is True
