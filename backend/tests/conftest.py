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

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config, journal_scelle
from app.store import store
from app import gouvernance


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
