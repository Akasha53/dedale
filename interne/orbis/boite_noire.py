"""Client de la boîte noire : tout passe par le backend (console API, port 8700).

Fire-and-forget pour les événements : si le backend ne répond pas, l'agent interne
continue sans tomber (contrat Dédale). Seule la lecture de session (décision humaine)
peut vouloir attendre, et c'est la passerelle qui gère ce cas.

Dépendances zéro : urllib de la lib standard.
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
    url = base + chemin
    donnees = json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(
        url, data=donnees, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            brut = rep.read().decode("utf-8")
            return json.loads(brut) if brut else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _lire(base: str, chemin: str, timeout: float = 1.0) -> dict | None:
    url = base + chemin
    try:
        with urllib.request.urlopen(url, timeout=timeout) as rep:
            brut = rep.read().decode("utf-8")
            return json.loads(brut) if brut else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


class BoiteNoire:
    """Enveloppe les appels au backend pour le module interne."""

    def __init__(self, base: str | None = None):
        self.base = base or config.BACKEND_BASE

    def enregistrer_leurres(self, leurres: list[dict]) -> bool:
        """POST /api/leurres au démarrage. True si le backend a accusé réception."""
        rep = _poster(self.base, "/api/leurres", leurres)
        return rep is not None

    def evenement(
        self,
        type: str,
        surface: str,
        session_id: str,
        *,
        leurre_id: str | None = None,
        outil: str | None = None,
        methode: str | None = None,
        chemin: str | None = None,
        details: dict | None = None,
    ) -> dict | None:
        """POST /api/evenements. Renvoie la réponse {session, consigne} ou None si muet."""
        corps = {
            "horodatage": _horodatage(),
            "source": "interne",
            "surface": surface,
            "type": type,
            "session_id": session_id,
            "leurre_id": leurre_id,
            "ip": "127.0.0.1",
            "user_agent": "orbis-interne/0.1",
            "methode": methode,
            "chemin": chemin,
            "outil": outil,
            "details": details or {},
        }
        return _poster(self.base, "/api/evenements", corps)

    def lire_session(self, session_id: str) -> dict | None:
        """GET /api/sessions/{id}. Renvoie le détail de session ou None si muet."""
        return _lire(self.base, f"/api/sessions/{session_id}")
