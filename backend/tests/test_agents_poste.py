"""Inventaire des agents IA d'un poste, envoyé par l'app Mac (POST /api/agents/poste)."""

from __future__ import annotations

import json

from app import agents_poste

# Assemblé à l'exécution : les détecteurs de secrets du dépôt ne voient jamais la valeur.
JETON = "ghp_" + "Zq7" * 12


def _corps(**kw) -> dict:
    corps = {
        "poste": "poste-mac-1a2b3c4d",
        "contexte": "poste",
        "source_config": "demo",
        "horodatage": "2026-10-10T21:40:00.000+02:00",
        "clients": ["Claude Desktop", "Cursor"],
        "agents": [
            {"client": "Claude Desktop", "client_id": "claude_desktop", "serveur": "fichiers-camille",
             "types": ["fichiers"], "droits_risques": ["disque_entier"], "transport": "local"},
            {"client": "Cursor", "client_id": "cursor", "serveur": "terminal",
             "types": ["shell", "fichiers"], "droits_risques": ["shell", "disque_entier"], "transport": "local"},
            {"client": "Cursor", "client_id": "cursor", "serveur": "recherche",
             "types": ["reseau"], "droits_risques": [], "transport": "distant"},
        ],
    }
    corps.update(kw)
    return corps


def test_inventaire_recu_puis_visible_dans_api_agents(client):
    r = client.post("/api/agents/poste", json=_corps())
    assert r.status_code == 201
    assert r.json()["total"] == 3
    assert r.json()["risques"] == 2

    inv = client.get("/api/agents").json()["inventaire"]
    poste = [f for f in inv if f.get("contexte") == "poste"]
    assert len(poste) == 3
    terminal = next(f for f in poste if f["serveur"] == "terminal")
    assert terminal["id"] == "poste:poste-mac-1a2b3c4d:cursor:terminal"
    assert terminal["risque"]["niveau"] == "eleve"
    assert [d["code"] for d in terminal["droits"]["accordes"]] == ["shell", "disque_entier"]
    assert next(f for f in poste if f["serveur"] == "recherche")["risque"]["niveau"] == "faible"
    # Les agents d'Orbis restent en tête, inchangés.
    assert inv[0]["id"] == "orbis-assistant"

    postes = client.get("/api/agents/poste").json()["postes"]
    assert postes[0]["poste"] == "poste-mac-1a2b3c4d"
    assert postes[0]["phrase"] == "3 serveurs MCP sur ce poste, dont 2 avec des droits risqués."


def test_un_nouvel_envoi_remplace_l_inventaire_du_poste(client):
    client.post("/api/agents/poste", json=_corps())
    client.post("/api/agents/poste", json=_corps(agents=[]))
    assert client.get("/api/agents/poste").json()["postes"][0]["total"] == 0
    assert not [f for f in client.get("/api/agents").json()["inventaire"] if f.get("contexte") == "poste"]


def test_champs_en_trop_et_secrets_ne_sont_jamais_gardes(client):
    agents = _corps()["agents"]
    agents[0] = {**agents[0], "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": JETON}, "args": ["--token", JETON],
                 "headers": {"Authorization": "Bearer " + JETON}}
    agents.append({"client": "Cursor", "client_id": "cursor", "serveur": JETON, "types": ["reseau"]})
    r = client.post("/api/agents/poste", json=_corps(agents=agents, jeton=JETON))
    assert r.status_code == 201
    stocke = agents_poste.chemin_fichier().read_text(encoding="utf-8")
    assert JETON not in stocke
    assert JETON not in json.dumps(client.get("/api/agents").json())
    assert "nom masqué" in stocke
    assert "Authorization" not in stocke and "GITHUB_PERSONAL_ACCESS_TOKEN" not in stocke


def test_valeurs_hors_liste_ramenees_aux_valeurs_admises(client):
    agents = [{"client": "<b>Cursor</b>", "client_id": "Cursor!", "serveur": "x‮exe.txt",
               "types": ["fichiers", "inconnu"], "droits_risques": ["root"], "transport": "ailleurs"}]
    client.post("/api/agents/poste", json=_corps(agents=agents))
    a = client.get("/api/agents/poste").json()["postes"][0]["agents"][0]
    assert a["client"] == "&lt;b&gt;Cursor&lt;/b&gt;"
    assert a["client_id"] == "inconnu"
    assert "‮" not in a["serveur"]
    assert a["types"] == ["fichiers"] and a["droits_risques"] == [] and a["transport"] == "local"


def test_corps_invalides(client):
    assert client.post("/api/agents/poste", json=_corps(poste="poste de camille")).status_code == 400
    assert client.post("/api/agents/poste", json=_corps(contexte="interne")).status_code == 400
    assert client.post("/api/agents/poste", json=_corps(agents="tous")).status_code == 400
    assert client.post("/api/agents/poste", json=_corps(agents=["x"])).status_code == 400


def test_la_fiche_d_un_agent_d_orbis_reste_servie(client):
    assert client.get("/api/agents/orbis-assistant").status_code == 200
