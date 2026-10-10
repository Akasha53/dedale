"""Fixtures des tests : un backend simulé en mémoire par test."""

from __future__ import annotations

import pytest

from orbis.backend_simule import BackendSimule
from orbis.boite_noire import BoiteNoire


@pytest.fixture
def backend():
    b = BackendSimule().demarrer()
    try:
        yield b
    finally:
        b.arreter()


@pytest.fixture
def boite(backend):
    return BoiteNoire(base=backend.base)
