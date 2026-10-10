"""Fixtures de test. Base SQLite isolée en /tmp, Store remis à zéro entre les tests."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

# Isole la base avant tout import de l'app (config lit l'env à l'import).
_TMPDB = os.path.join(tempfile.gettempdir(), "dedale_test.db")
os.environ["DEDALE_DB"] = _TMPDB
os.environ["DEDALE_LLM"] = "off"  # pas d'appel modèle en test : repli gabarit déterministe
os.environ["DEDALE_RELECTEUR"] = "off"  # relecteur IA coupé, sauf dans test_relecteur.py
os.environ.pop("DEDALE_WEBHOOK_URL", None)  # aucune alerte ne sort pendant les tests
# Jetons d'accès tirés dans un dossier jetable, jamais ~/.config/dedale.
os.environ["DEDALE_JETONS"] = tempfile.mkdtemp(prefix="dedale-jetons-")
# Ancrage : clés de signature dans un dossier jetable, jamais ~/.config/dedale, et aucun
# appel au réseau Fuji (tests/test_ancrage.py passe par un faux client RPC).
_CLES = tempfile.mkdtemp(prefix="dedale-cles-")
os.environ["DEDALE_CLES"] = os.path.join(_CLES, "cles")
os.environ["DEDALE_ANCRAGE_CLE"] = os.path.join(_CLES, "ancrage.key")
os.environ["DEDALE_ANCRAGE"] = "off"

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app import auth
from app import config, journal_scelle
from app.store import store
from app import gouvernance
from app import besoin_d_en_connaitre


@pytest.fixture(autouse=True)
def _reset_store(tmp_path, monkeypatch):
    # Chaque cycle de vie recharge sa base ; les tests doivent partir d'un journal isolé.
    monkeypatch.setattr(config, "CHEMIN_DB", tmp_path / "dedale.db")
    store.sessions.clear()
    store.leurres.clear()
    store.incidents.clear()
    store.evenements.clear()
    store.decisions.clear()
    store.routes_leurres.clear()
    store.outils_leurres.clear()
    store.retraits.clear()
    store._compteur = 0
    store._incident_seq = 0
    store.tete_evenements = journal_scelle.GENESE
    store.tete_decisions = journal_scelle.GENESE
    gouvernance.vider()
    auth.vider_bilan()
    besoin_d_en_connaitre.vider()
    yield


def jeton(role: str) -> dict[str, str]:
    """En-tête d'une identité, pour les tests qui choisissent leur jeton."""
    return {"Authorization": "Bearer " + auth.chemin_jeton(role).read_text().strip()}


def _routes(routeur):
    """Routes de l'app, routeurs inclus (FastAPI les garde imbriqués depuis la 0.140)."""
    for route in routeur.routes:
        sous = getattr(route, "original_router", None)
        if sous is not None:
            yield from _routes(sous)
        else:
            yield route


def role_de_la_route(methode: str, chemin: str) -> str:
    """Première identité que la route déclare (auth.exiger), l'analyste si elle ne déclare rien."""
    for route in _routes(app.router):
        if (isinstance(route, APIRoute) and methode in route.methods
                and route.path_regex.match(chemin)):
            roles = auth._roles_declares(route)
            return roles[0] if roles else "analyste"
    return "analyste"


def _jeton_de_la_route(requete: httpx.Request) -> None:
    """Le client de test se présente comme l'appelant légitime de chaque route, d'après la
    dépendance qu'elle déclare : la passerelle pour un événement, le poste pour son inventaire,
    le validateur pour un geste métier, l'analyste pour le reste. Un test qui pose son propre
    en-tête Authorization le garde ; tests/test_auth.py vérifie les refus."""
    if "authorization" not in requete.headers:
        requete.headers.update(jeton(role_de_la_route(requete.method, requete.url.path)))


@pytest.fixture(autouse=True)
def _jetons_par_defaut(monkeypatch):
    origine = TestClient.__init__

    def initialiser(self, *args, **kwargs):
        origine(self, *args, **kwargs)
        self.event_hooks = {"request": [_jeton_de_la_route], "response": []}

    monkeypatch.setattr(TestClient, "__init__", initialiser)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def horo(base: datetime, secondes: float) -> str:
    return (base + timedelta(seconds=secondes)).isoformat()


BASE = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)


def evenement(**kw) -> dict:
    """Construit un corps d'événement avec des valeurs par défaut raisonnables."""
    corps = {
        "source": "externe",
        "surface": "site",
        "type": "requete",
        "session_id": "S-1",
        "horodatage": BASE.isoformat(),
        "details": {},
    }
    corps.update(kw)
    return corps
