"""Client minimal de l'API de Mailpit, la boîte de démo locale (127.0.0.1 seulement).

Bibliothèque standard seule. Lire un mail ne marque rien, n'ouvre aucun lien.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MAILPIT = os.environ.get("MESSAGERIE_MAILPIT", "http://127.0.0.1:8716").rstrip("/")


class BoiteIndisponible(Exception):
    """Mailpit ne répond pas (pas lancé, ou port différent)."""


class Boite:
    def __init__(self, base: str | None = None, timeout: float = 3.0):
        self.base = (base or MAILPIT).rstrip("/")
        self.timeout = timeout

    def _requete(self, chemin: str, methode: str = "GET") -> bytes:
        req = urllib.request.Request(self.base + chemin, method=methode)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                return rep.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise KeyError(chemin) from e
            raise BoiteIndisponible(f"{methode} {chemin} : HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise BoiteIndisponible(f"{methode} {chemin} : {e}") from e

    def joignable(self) -> bool:
        try:
            self._requete("/api/v1/info")
            return True
        except (BoiteIndisponible, KeyError):
            return False

    def lister(self, limite: int = 200) -> list[dict]:
        """Résumés des derniers mails, du plus récent au plus ancien (`ID`, `Created`, …)."""
        donnees = json.loads(self._requete(f"/api/v1/messages?limit={int(limite)}") or b"{}")
        return donnees.get("messages") or []

    def brut(self, identifiant: str) -> bytes:
        """Le mail tel qu'il est arrivé (RFC 5322). KeyError s'il n'existe pas."""
        if not identifiant or any(c in identifiant for c in "/?#%"):
            raise KeyError(identifiant)
        return self._requete(f"/api/v1/message/{identifiant}/raw")

    def vider(self) -> None:
        """Supprime tous les mails de la boîte de démo."""
        self._requete("/api/v1/messages", methode="DELETE")
