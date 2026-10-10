"""Pont vers le backend collecteur : envoi d'evenements, recuperation des consignes,
enregistrement des leurres au demarrage.

Regle d'or : si le backend ne repond pas, la surface continue normalement.
Toute erreur reseau est avalee et rend une consigne « aucune ».
"""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from . import config

CONSIGNE_PAR_DEFAUT: dict[str, Any] = {
    "session": {"id": None, "classement": "inconnu", "score": 0.0, "etat": "active"},
    "consigne": "aucune",
}


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
            reponse = await client.post(f"{config.BACKEND}/api/evenements", json=corps)
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
            reponse = await client.post(f"{config.BACKEND}/api/leurres", json=leurres)
            return reponse.status_code in (200, 201)
    except Exception:
        return False
