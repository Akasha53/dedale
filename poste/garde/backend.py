"""Client du backend (console API, port 8700), fire-and-forget.

Calqué sur interne/orbis/boite_noire.py : urllib de la lib standard, zéro
dépendance. Si le backend ne répond pas, chaque appel renvoie None et le poste
continue sans tomber (contrat Dédale, § « Si le backend ne répond pas »).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config


def _horodatage() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _poster(base: str, chemin: str, corps: dict | list, timeout: float = 1.0) -> dict | None:
    donnees = json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(
        base + chemin, data=donnees,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            brut = rep.read().decode("utf-8")
            return json.loads(brut) if brut else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


class Backend:
    """Émetteur d'événements du poste. Jamais bloquant."""

    def __init__(self, base: str | None = None, actif: bool = True):
        self.base = base or config.BACKEND_BASE
        self.actif = actif  # False en test : rien ne part sur le réseau

    def evenement(
        self,
        type: str,
        session_id: str,
        *,
        details: dict | None = None,
    ) -> dict | None:
        """POST /api/evenements, source=humain, surface=poste. Renvoie la réponse ou None."""
        if not self.actif:
            return None
        corps = {
            "horodatage": _horodatage(),
            "source": "humain",
            "surface": "poste",
            "type": type,
            "session_id": session_id,
            "leurre_id": None,
            "ip": "127.0.0.1",
            "user_agent": "orbis-poste/0.1",
            "methode": None,
            "chemin": None,
            "outil": None,
            "details": details or {},
        }
        return _poster(self.base, "/api/evenements", corps)
