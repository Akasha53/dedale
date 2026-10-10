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
    assert next(f for f in poste if f["serveur"] == "recherche")["risque"]["niveau"] == "moyen"
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


# --- calcul du risque : un test par cas -------------------------------------------------------

def _risque_de(client, **agent) -> dict:
    a = {"client": "Cursor", "client_id": "cursor", "serveur": "essai", "types": ["autre"],
         "droits_risques": [], "transport": "local", **agent}
    client.post("/api/agents/poste", json=_corps(agents=[a]))
    fiche = next(f for f in client.get("/api/agents").json()["inventaire"] if f.get("contexte") == "poste")
    return fiche["risque"]


def test_risque_mail_lit_et_envoie_est_moyen_et_nomme_le_droit(client):
    r = _risque_de(client, serveur="boite-mail-finance", types=["mail"], droits_risques=["mail"])
    assert r["niveau"] == "moyen"
    assert r["canal_de_sortie"] is True
    codes = [x["code"] for x in r["raisons"]]
    assert codes == ["droit_mail", "canal_de_sortie"]
    assert "Droit « mails »" in r["explication"] and "envoyer des mails" in r["explication"]
    assert "lit (des mails) et peut envoyer (des mails)" in r["explication"]


def test_risque_shell_seul_fait_monter_le_niveau(client):
    r = _risque_de(client, types=["shell"], droits_risques=["shell"])
    assert r["niveau"] == "eleve"  # shell 6 + canal de sortie 2 (le shell lit et fait sortir)
    assert "Droit « shell »" in r["explication"]


def test_risque_tout_le_disque(client):
    r = _risque_de(client, types=["fichiers"], droits_risques=["disque_entier"])
    assert r["niveau"] == "moyen"
    assert r["canal_de_sortie"] is False
    assert "Droit « tout le disque »" in r["explication"]


def test_risque_navigateur_pilote(client):
    r = _risque_de(client, types=["navigateur"])
    assert r["niveau"] == "moyen"
    assert [x["code"] for x in r["raisons"]] == ["navigateur_pilote", "canal_de_sortie"]
    assert "Navigateur piloté" in r["explication"]


def test_risque_serveur_distant_non_verifie(client):
    r = _risque_de(client, types=["reseau"], transport="distant")
    assert r["niveau"] == "moyen"
    assert "Serveur distant non vérifié" in r["explication"]


def test_risque_canal_de_sortie_sans_droit_a_risque_reste_au_moins_moyen(client):
    # Lit des fichiers d'un seul dossier et peut les envoyer sur le réseau : score 2, plancher moyen.
    r = _risque_de(client, types=["fichiers", "reseau"])
    assert r["score"] == 2
    assert r["niveau"] == "moyen"
    assert "Canal de sortie : le même serveur lit (des fichiers) et peut envoyer (vers le réseau)." in r["explication"]
    assert "au moins comme un risque moyen" in r["explication"]


def test_risque_cumule_eleve(client):
    r = _risque_de(client, types=["shell", "fichiers"], droits_risques=["shell", "disque_entier"])
    assert r["niveau"] == "eleve"
    assert {"droit_shell", "droit_disque_entier", "canal_de_sortie"} <= {x["code"] for x in r["raisons"]}


def test_risque_faible_sans_droit_ni_canal(client):
    r = _risque_de(client, types=["reseau"])
    assert r["niveau"] == "faible"
    assert r["raisons"] == []
    assert r["explication"] == "Risque faible : ni droit à risque, ni canal de sortie."
    r2 = _risque_de(client, types=["fichiers"])
    assert r2["niveau"] == "faible"
