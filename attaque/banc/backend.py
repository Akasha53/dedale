"""Client du backend Dédale (Console API, 8700).

Le banc poste les événements qu'il simule (mode autonome) et lit les mesures et
sessions. Tout est en boucle fermée sur 127.0.0.1. Si le backend ne répond pas,
les appels renvoient ``None`` sans faire tomber le banc : la surface, comme le
banc, « continue sans consigne » (contrat).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Le banc écrit comme la passerelle ; il lit mesures et sessions comme la console.
ECRITURES = {"/api/evenements", "/api/leurres", "/api/resistance/campagnes"}


def entete_jeton(role: str) -> dict[str, str]:
    """En-tête `Authorization` du rôle, lu hors du dépôt dans `~/.config/dedale/jeton-<rôle>`
    (ou le dossier `DEDALE_JETONS`). Jeton absent : aucun en-tête, et le backend répond 401."""
    brut = os.environ.get("DEDALE_JETONS", "").strip()
    dossier = Path(brut).expanduser() if brut else Path.home() / ".config" / "dedale"
    try:
        jeton = (dossier / f"jeton-{role}").read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return {}
    return {"Authorization": f"Bearer {jeton}"} if jeton else {}


class Backend:
    def __init__(self, base: str = "http://127.0.0.1:8700", delai: float = 2.0):
        self.base = base.rstrip("/")
        self.delai = delai
        self.disponible: bool | None = None
        # Latence de l'aller-retour du dernier appel réussi, en millisecondes (horloge
        # réelle du banc). None si le dernier appel a échoué.
        self.derniere_latence_ms: float | None = None

    def _appel(self, chemin: str, methode: str = "GET",
               corps: Any = None) -> dict | list | None:
        donnees = json.dumps(corps).encode() if corps is not None else None
        role = "passerelle" if methode == "POST" and chemin in ECRITURES else "analyste"
        req = urllib.request.Request(self.base + chemin, data=donnees, method=methode,
                                     headers=entete_jeton(role))
        if donnees is not None:
            req.add_header("Content-Type", "application/json")
        debut = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.delai) as rep:
                brut = rep.read().decode("utf-8", "replace")
                self.disponible = True
                self.derniere_latence_ms = (time.perf_counter() - debut) * 1000
                return json.loads(brut) if brut else {}
        except urllib.error.HTTPError:
            # Le backend répond (404 sur une session inconnue, par exemple).
            self.disponible = True
            self.derniere_latence_ms = None
            return None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            self.disponible = False
            self.derniere_latence_ms = None
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
        """Sessions du backend. L'API renvoie ``{"sessions": [...]}`` ; l'ancien
        format liste reste accepté. None si le backend ne répond pas."""
        rep = self._appel("/api/sessions")
        return _liste(rep, "sessions")

    def incidents(self) -> list | None:
        """Incidents du backend (``{"incidents": [...]}`` ou liste). None si absent."""
        rep = self._appel("/api/incidents")
        return _liste(rep, "incidents")


def _liste(rep: Any, cle: str) -> list | None:
    if isinstance(rep, list):
        return rep
    if isinstance(rep, dict) and isinstance(rep.get(cle), list):
        return rep[cle]
    return None
