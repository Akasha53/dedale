"""Routes du relecteur IA et branchement sur le collecteur.

`brancher(app, enfiler)` est la seule ligne ajoutée à main.py : elle inclut les routes, donne au
relecteur l'écrivain SQLite et WS, et pose un observateur ASGI sur `POST /api/evenements`. Après
une réponse 2xx, l'observateur lit le `session_id` du corps reçu et laisse le relecteur lancer ce
qui l'attend (geste à quatre yeux, pré-tri). La réponse au module ne l'attend jamais.
"""

from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, FastAPI, HTTPException

from . import relecteur

routeur = APIRouter()
_TAILLE_MAX = 256 * 1024


@routeur.get("/api/relecteur")
async def etat_relecteur():
    """Moteur configuré, moteur qui sera essayé, modèle, délai, suspension après une limite."""
    return relecteur.etat()


@routeur.get("/api/relecteur/file")
async def file_a_regarder():
    """Incidents ouverts où le relecteur doute, ou de priorité haute."""
    return relecteur.file_a_regarder()


@routeur.get("/api/relecteur/demandes/{demande_id}")
async def relecture_demande(demande_id: str):
    """Ce que le relecteur a décidé d'un geste à quatre yeux (`en_cours`, puis `tranchee`)."""
    d = relecteur.relecture_demande(demande_id[:80])
    if d is None:
        raise HTTPException(status_code=404, detail=f"Demande inconnue : {demande_id[:80]}")
    return d


@routeur.get("/api/incidents/{iid}/tri")
async def tri_incident(iid: str):
    """Pré-tri de l'incident : priorité, décision proposée, motif, confiance, qui a tranché."""
    d = relecteur.tri_incident(iid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    return d


class Observateur:
    """Middleware ASGI pur : recopie le corps de `POST /api/evenements` sans le retenir, puis,
    la réponse partie, signale la session au relecteur."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or scope.get("path") != "/api/evenements" or not relecteur.actif()):
            await self.app(scope, receive, send)
            return
        morceaux: list[bytes] = []
        taille = 0
        statut: dict = {}

        async def recevoir():
            nonlocal taille
            message = await receive()
            if message.get("type") == "http.request" and taille <= _TAILLE_MAX:
                corps = message.get("body", b"")
                taille += len(corps)
                morceaux.append(corps)
            return message

        async def envoyer(message):
            if message.get("type") == "http.response.start":
                statut["code"] = message.get("status", 0)
            await send(message)

        await self.app(scope, recevoir, envoyer)
        if not 200 <= statut.get("code", 0) < 300 or taille > _TAILLE_MAX:
            return
        try:
            sid = json.loads(b"".join(morceaux)).get("session_id")
        except (ValueError, AttributeError):
            return
        if isinstance(sid, str) and sid:
            try:
                relecteur.observer(sid)
            except Exception:  # le relecteur ne fait jamais échouer le collecteur
                pass


def brancher(app: FastAPI, enfiler: Callable[[dict], None]) -> None:
    relecteur.persister = enfiler
    app.include_router(routeur)
    app.add_middleware(Observateur)
