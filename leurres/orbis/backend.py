"""Pont vers le backend collecteur : envoi d'evenements, recuperation des consignes,
enregistrement des leurres au demarrage.

Regle d'or : si le backend ne repond pas, la surface continue normalement.
Toute erreur reseau est avalee et rend une consigne « aucune ».
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any

import httpx

from . import config

CONSIGNE_PAR_DEFAUT: dict[str, Any] = {
    "session": {"id": None, "classement": "inconnu", "score": 0.0, "etat": "active"},
    "consigne": "aucune",
}


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


def _horodatage() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _evenement(**champs: Any) -> dict[str, Any]:
    """Construit un evenement conforme au schema de CONTRATS.md."""
    base: dict[str, Any] = {
        "horodatage": _horodatage(),
        "source": "externe",
        "surface": "site",
        "type": "requete",
        "session_id": None,
        "leurre_id": None,
        "ip": "127.0.0.1",
        "user_agent": None,
        "methode": None,
        "chemin": None,
        "outil": None,
        "details": {},
    }
    base.update(champs)
    return base


async def envoyer_evenement(**champs: Any) -> dict[str, Any]:
    """Poste un evenement et renvoie {session, consigne}. Jamais d'exception."""
    corps = _evenement(**champs)
    try:
        async with httpx.AsyncClient(timeout=config.TIMEOUT_BACKEND) as client:
            reponse = await client.post(f"{config.BACKEND}/api/evenements", json=corps,
                                        headers=entete_jeton("passerelle"))
            if reponse.status_code == 200:
                data = reponse.json()
                # On tolere un backend qui ne renvoie pas tout.
                return {
                    "session": data.get("session", CONSIGNE_PAR_DEFAUT["session"]),
                    "consigne": data.get("consigne", "aucune") or "aucune",
                }
    except Exception:
        pass
    return dict(CONSIGNE_PAR_DEFAUT)


async def enregistrer_leurres(leurres: list[dict[str, Any]]) -> bool:
    """Enregistre l'inventaire des leurres. Renvoie True si le backend a accepte."""
    try:
        async with httpx.AsyncClient(timeout=max(config.TIMEOUT_BACKEND, 2.0)) as client:
            reponse = await client.post(f"{config.BACKEND}/api/leurres", json=leurres,
                                        headers=entete_jeton("passerelle"))
            return reponse.status_code in (200, 201)
    except Exception:
        return False
