"""Client du backend Dédale (Console API, 8700).

Le banc poste les événements qu'il simule (mode autonome) et lit les mesures et
sessions. Tout est en boucle fermée sur 127.0.0.1. Si le backend ne répond pas,
les appels renvoient ``None`` sans faire tomber le banc : la surface, comme le
banc, « continue sans consigne » (contrat).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class Backend:
    def __init__(self, base: str = "http://127.0.0.1:8700", delai: float = 2.0):
        self.base = base.rstrip("/")
        self.delai = delai
        self.disponible: bool | None = None

    def _appel(self, chemin: str, methode: str = "GET",
               corps: Any = None) -> dict | list | None:
        donnees = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(self.base + chemin, data=donnees, method=methode)
        if donnees is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.delai) as rep:
                self.disponible = True
                brut = rep.read().decode("utf-8", "replace")
                return json.loads(brut) if brut else {}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            self.disponible = False
            return None

    def enregistrer_leurres(self, leurres: list[dict]) -> bool:
        return self._appel("/api/leurres", "POST", leurres) is not None

    def emettre(self, evenement: dict) -> dict:
        """Poste un événement, renvoie ``{session, consigne}`` ou un repli neutre."""
        rep = self._appel("/api/evenements", "POST", evenement)
        if isinstance(rep, dict) and "consigne" in rep:
            return rep
        return {"session": {"id": evenement.get("session_id"), "classement": "inconnu",
                            "score": 0.0, "etat": "active"}, "consigne": "aucune"}

    def session(self, session_id: str) -> dict | None:
        rep = self._appel(f"/api/sessions/{session_id}")
        return rep if isinstance(rep, dict) else None

    def mesures(self) -> dict | None:
        rep = self._appel("/api/mesures")
        return rep if isinstance(rep, dict) else None

    def sessions(self) -> list | None:
        rep = self._appel("/api/sessions")
        return rep if isinstance(rep, list) else None
