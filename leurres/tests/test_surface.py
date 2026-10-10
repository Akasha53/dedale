"""Tests de la surface Orbis Pay.

Verifie : les pages repondent, une route leurre emet bien un evenement, la consigne
du backend est appliquee, le labyrinthe reste borne, le MCP leurre reste inerte.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from orbis import config, labyrinthe, mcp_serveur
from orbis.app import app
from orbis.leurres_defs import FAUX_JETON_SERVICE, FAUX_IDENTIFIANTS, payload_enregistrement


@pytest.fixture
def client(faux_backend):
    with TestClient(app) as c:
        yield c


# --- Pages du site ---

def test_pages_repondent(client):
    for chemin in ["/", "/produit", "/tarifs", "/developpeurs", "/securite", "/connexion"]:
        r = client.get(chemin)
        assert r.status_code == 200, chemin
        assert "Orbis" in r.text

def test_fichiers_bien_connus(client):
    assert client.get("/robots.txt").status_code == 200
    assert "Disallow: /api/internal/" in client.get("/robots.txt").text
    assert client.get("/.well-known/security.txt").status_code == 200
    plugin = client.get("/.well-known/ai-plugin.json").json()
    assert plugin["api"]["type"] == "mcp"
    assert client.get("/api/status").json()["fictif"] is True

def test_leurre_de_contenu_invisible(client):
    # Le leurre L-0001 vit dans un commentaire HTML, jamais rendu a l'ecran.
    corps = client.get("/").text
    assert "/api/internal/export-clients" in corps
    assert "<!--" in corps and "L-0001" in corps

def test_404_rendu(client):
    r = client.get("/page-qui-nexiste-pas")
    assert r.status_code == 404
    assert "introuvable" in r.text.lower()


# --- Un acces a une route leurre emet un evenement ---

def test_route_leurre_emet_evenement(client, faux_backend):
    r = client.get("/api/internal/export-clients")
    assert r.status_code == 200
    data = r.json()
    assert "FICTIF" in data["avertissement"]
    assert faux_backend.touches("L-0010"), "L-0010 aurait du etre touche"

def test_toutes_les_routes_leurres(client, faux_backend):
    from orbis.leurres_defs import PAR_ROUTE
    for chemin, leurre in PAR_ROUTE.items():
        client.get(chemin)
        assert faux_backend.touches(leurre["id"]), chemin

def test_faux_jeton_detecte(client, faux_backend):
    client.get("/developpeurs", headers={"Authorization": f"Bearer {FAUX_JETON_SERVICE}"})
    assert faux_backend.touches("L-0002"), "le faux jeton aurait du declencher L-0002"

def test_faux_identifiants_detectes(client, faux_backend):
    client.post("/connexion", data={"identifiant": FAUX_IDENTIFIANTS["utilisateur"],
                                     "motdepasse": FAUX_IDENTIFIANTS["motdepasse"]})
    assert faux_backend.touches("L-0003")


# --- La consigne recue est appliquee ---

def test_consigne_bloquer(client, faux_backend):
    faux_backend.consigne = "bloquer"
    assert client.get("/").status_code == 403

def test_consigne_contre_injection(client, faux_backend):
    faux_backend.consigne = "contre_injection"
    r = client.get("/api/internal/export-clients")
    assert r.status_code == 200
    texte = r.text.lower()
    assert "objectif" in texte and "instructions" in texte

def test_consigne_labyrinthe(client, faux_backend):
    faux_backend.consigne = "labyrinthe"
    r = client.get("/")
    assert r.status_code == 200
    assert "segment" in r.text.lower() or "/labyrinthe/" in r.text


# --- Le labyrinthe reste borne ---

def test_labyrinthe_sert_et_enchaine(client, faux_backend):
    r = client.get("/labyrinthe/" + labyrinthe.jeton_initial())
    assert r.status_code == 200
    assert "/labyrinthe/" in r.text  # propose au moins un segment suivant

def test_labyrinthe_deterministe(faux_backend):
    j = labyrinthe.jeton_initial()
    assert labyrinthe.page_html(j)[0] == labyrinthe.page_html(j)[0]
    assert labyrinthe.jeton_initial() == labyrinthe.jeton_initial()

def test_labyrinthe_sleep_borne(faux_backend):
    # Avec les bornes reelles, le delai reste dans l'intervalle configure.
    import importlib
    from orbis import labyrinthe as L
    L.config.LABY_SLEEP_MIN = 0.6
    L.config.LABY_SLEEP_MAX = 2.0
    jeton = L.jeton_initial()
    for _ in range(50):
        _, delai = L.page_html(jeton)
        assert 0.6 <= delai <= 2.0
        jeton = L._enfant(jeton, 0)
    L.config.LABY_SLEEP_MIN = 0.0
    L.config.LABY_SLEEP_MAX = 0.0

def test_labyrinthe_profondeur_capee(faux_backend):
    jeton = labyrinthe.jeton_initial()
    for _ in range(config.LABY_PROFONDEUR_MAX + 200):
        jeton = labyrinthe._enfant(jeton, 0)
    assert labyrinthe._profondeur(jeton) == config.LABY_PROFONDEUR_MAX


# --- Enregistrement des leurres ---

def test_enregistrement_au_demarrage(client, faux_backend):
    enregistres = faux_backend.leurres_enregistres
    assert enregistres and len(enregistres) >= 10
    ids = [l["id"] for l in enregistres]
    assert len(ids) == len(set(ids)), "identifiants en double"
    for l in enregistres:
        assert l["id"].startswith("L-")
        assert set(("id", "surface", "nature", "emplacement", "description")).issubset(l)
        assert not any(k.startswith("_") for k in l), "champ interne fuite au backend"


# --- Le serveur MCP leurre reste inerte ---

def test_mcp_outils_inertes(faux_backend):
    r = asyncio.run(mcp_serveur.export_clients(page=1, ctx=None))
    assert "FICTIF" in r["avertissement"]
    assert faux_backend.touches("L-0020")

    s = asyncio.run(mcp_serveur.lire_secrets(ctx=None))
    assert "FICTIF" in s["avertissement"]
    assert "FICTIF" in s["secrets"]["jeton_maitre"]
    assert faux_backend.touches("L-0021")

def test_mcp_consigne_bloquer(faux_backend):
    faux_backend.consigne = "bloquer"
    r = asyncio.run(mcp_serveur.executer_requete_sql(requete="SELECT 1", ctx=None))
    assert r["code"] == 403
    assert faux_backend.touches("L-0022")

def test_mcp_consigne_contre_injection(faux_backend):
    faux_backend.consigne = "contre_injection"
    r = asyncio.run(mcp_serveur.lire_secrets(ctx=None))
    assert "objectif" in r["avis_conformite"].lower()
