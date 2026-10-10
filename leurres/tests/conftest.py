"""Fixtures de test : backend simule et labyrinthe sans attente."""
from __future__ import annotations

import pytest

from orbis import backend, config


class BackendFaux:
    """Capture les evenements et renvoie une consigne reglable."""

    def __init__(self) -> None:
        self.evenements: list[dict] = []
        self.consigne = "aucune"
        self.leurres_enregistres: list[dict] | None = None

    async def envoyer_evenement(self, **champs):
        self.evenements.append(champs)
        return {
            "session": {"id": champs.get("session_id"), "classement": "agent_ia",
                        "score": 1.0, "etat": "active"},
            "consigne": self.consigne,
        }

    async def enregistrer_leurres(self, leurres):
        self.leurres_enregistres = leurres
        return True

    def touches(self, leurre_id: str) -> list[dict]:
        return [e for e in self.evenements
                if e.get("leurre_id") == leurre_id and e.get("type") in ("leurre_touche", "appel_outil")]


@pytest.fixture
def faux_backend(monkeypatch):
    bf = BackendFaux()
    monkeypatch.setattr(backend, "envoyer_evenement", bf.envoyer_evenement)
    monkeypatch.setattr(backend, "enregistrer_leurres", bf.enregistrer_leurres)
    # Pas d'attente du labyrinthe pendant les tests.
    monkeypatch.setattr(config, "LABY_SLEEP_MIN", 0.0)
    monkeypatch.setattr(config, "LABY_SLEEP_MAX", 0.0)
    return bf
