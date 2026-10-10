"""Chaîne d'un incident d'agent interne : texte neutralisé une seule fois, repères ATT&CK.

Avant correctif, `construire_chaine` neutralisait une seconde fois un texte déjà neutralisé à
l'ingestion : préfixe « [leurre, neutralisé] » en double et « &amp;amp; » dans la console.
"""

import re

from tests.conftest import BASE, evenement, horo

PREFIXE = "[leurre, neutralisé]"


def _chaine(client, session_id: str) -> list[dict]:
    inc = next(i for i in client.get("/api/incidents").json()["incidents"]
               if i["session_id"] == session_id)
    return client.get(f"/api/incidents/{inc['id']}").json()["chaine"]


def _techniques(etape: dict) -> dict[str, dict]:
    return {t["id"]: t for t in etape["techniques"]}


def _scenario_jury(client, sid: str = "S-jury", extrait: str = "relevé « A&B » <b>gras</b>"):
    """Forme des événements du scénario jury : extrait déjà inerte côté interne/."""
    client.post("/api/leurres", json=[
        {"id": "C-3E58", "source": "interne", "surface": "document", "nature": "consigne_cachee",
         "techniques": ["AML.T0051"], "risques": ["OWASP ASI01"]},
        {"id": "C-1D4C", "source": "interne", "surface": "coffre", "nature": "canari_coffre",
         "techniques": ["AML.T0053", "T1555"], "risques": ["OWASP ASI02", "OWASP ASI03"]},
    ])
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="document", type="entree_agent",
        details={"maillon": "source", "extrait": extrait}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="document", type="entree_agent",
        leurre_id="C-3E58", details={"maillon": "consigne", "extrait": "consigne & cachée"},
        horodatage=horo(BASE, 0.1)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="lire_coffre",
        leurre_id="C-1D4C",
        details={"maillon": "appel_outil", "retenu": True, "motif": "droits",
                 "violation_droits": {"outil": "lire_coffre", "scope_requis": "coffre:lire",
                                      "scopes_jeton": ["document:lire"], "tache": "rapport"}},
        horodatage=horo(BASE, 0.2)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="coffre", type="leurre_touche",
        leurre_id="C-3E58", details={"extrait": "l’appel retenu suit la consigne"},
        horodatage=horo(BASE, 0.3)))


def test_texte_de_la_chaine_neutralise_une_seule_fois(client):
    _scenario_jury(client)
    chaine = _chaine(client, "S-jury")
    textes = [e["detail"] for e in chaine]
    for t in textes:
        assert t.count(PREFIXE) <= 1, t
        assert "&amp;amp;" not in t and "&amp;lt;" not in t, t
    source = next(t for t in textes if "relevé" in t)
    assert source == f"{PREFIXE} relevé « A&amp;B » &lt;b&gt;gras&lt;/b&gt;"
    # Même forme que l'événement exposé par l'API : une seule neutralisation, à l'ingestion.
    evs = client.get("/api/sessions/S-jury").json()["evenements"]
    stocke = next(e["details"]["extrait"] for e in evs if e["details"].get("maillon") == "source")
    assert source == stocke


def test_troncature_sans_entite_coupee(client):
    _scenario_jury(client, sid="S-long", extrait="&" * 300)
    detail = next(e["detail"] for e in _chaine(client, "S-long") if "&amp;" in e["detail"])
    assert detail.count(PREFIXE) == 1
    assert detail.endswith(" […]")
    assert re.search(r"(&amp;)+$", detail.removesuffix(" […]")), detail


def test_attack_pour_l_appel_hors_droits_vers_le_coffre(client):
    _scenario_jury(client)
    action = next(e for e in _chaine(client, "S-jury") if e["phase"] == "outil")
    tech = _techniques(action)
    # T1555 déjà posé par le canari du coffre : une seule entrée, nom officiel, établi.
    assert [t["id"] for t in action["techniques"]].count("T1555") == 1
    assert tech["T1555"]["nom"] == "Credentials from Password Stores"
    assert tech["T1555"]["a_confirmer"] is False
    # Abus de droits : comptes valides, rapprochement à confirmer.
    assert tech["T1078"]["cadre"] == "ATT&CK" and tech["T1078"]["a_confirmer"] is True
    # Les repères OWASP et ATLAS du canari restent.
    assert {"AML.T0053"} <= set(tech)
    assert {"OWASP ASI02", "OWASP ASI03"} <= {r["id"] for r in action["risques"]}


def test_attack_et_asi03_sur_un_virement_hors_jeton_sans_canari(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-droits", source="interne", surface="mail", type="entree_agent",
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-droits", source="interne", surface="outil", type="appel_outil",
        outil="executer_paiement",
        details={"violation_droits": {"outil": "executer_paiement",
                                      "scope_requis": "paiement:executer"}},
        horodatage=horo(BASE, 1)))
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_droits"
    action = next(e for e in _chaine(client, "S-droits") if e["phase"] == "outil" and e["techniques"])
    assert set(_techniques(action)) == {"T1078", "T1657"}
    assert all(t["a_confirmer"] for t in action["techniques"])
    assert [r["id"] for r in action["risques"]] == ["OWASP ASI03"]


def test_attack_pour_un_outil_mcp_piege_et_sa_sortie(client):
    client.post("/api/leurres", json=[
        {"id": "C-9F2E", "source": "interne", "surface": "outil", "nature": "outil_mcp_piege",
         "techniques": ["AML.T0053", "AML.T0051"], "risques": ["OWASP ASI02", "OWASP ASI06"]}])
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="appel_outil",
        outil="verifier_conformite",
        details={"outil_mcp_suspect": True, "serveur_mcp": "conformite-express-mcp"},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="leurre_touche",
        leurre_id="C-9F2E", details={"type": "exfiltration_markdown"}, horodatage=horo(BASE, 1)))
    client.post("/api/evenements", json=evenement(
        session_id="S-mcp", source="interne", surface="outil", type="sortie_agent",
        details={"exfiltration": True}, horodatage=horo(BASE, 2)))
    chaine = _chaine(client, "S-mcp")
    consignes = [e for e in chaine if e["phase"] == "consigne"]
    assert consignes and all("T1195" in _techniques(e) for e in consignes)
    sortie = next(e for e in chaine if e["phase"] == "sortie")
    assert _techniques(sortie)["T1048"]["a_confirmer"] is True
    # Le canari MCP relevé par l'inspection sortante porte aussi l'exfiltration.
    assert "T1048" in _techniques(next(e for e in consignes if e["leurre_id"] == "C-9F2E"))


def test_pas_d_attack_ajoute_hors_agent_interne(client):
    client.post("/api/leurres", json=[
        {"id": "L-0001", "source": "externe", "surface": "doc", "nature": "consigne_cachee",
         "techniques": ["AML.T0051"]}])
    client.post("/api/evenements", json=evenement(
        session_id="S-ext", surface="doc", type="leurre_touche", leurre_id="L-0001",
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-ext", type="sortie_agent", details={"exfiltration": True},
        horodatage=horo(BASE, 2)))
    tech = {t["id"] for e in _chaine(client, "S-ext") for t in e["techniques"]}
    assert tech == {"AML.T0051"}
