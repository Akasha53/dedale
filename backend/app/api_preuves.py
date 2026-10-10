"""Routes de preuve : vérification du journal scellé.

Monté par main.py (`app.include_router`). La vérification lit la base SQLite en lecture
seule, après avoir laissé l'écrivain vider sa file : elle juge ce qui est écrit, pas l'état
en mémoire.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from . import config, journal_scelle
from .store import store

routeur = APIRouter()


def _verifier(iid: str) -> dict | None:
    chemin = Path(config.CHEMIN_DB)
    if not chemin.is_file():
        return None
    conn = journal_scelle.ouvrir_lecture(chemin)
    try:
        return journal_scelle.verifier_incident(conn, iid)
    finally:
        conn.close()


async def verification(request: Request, iid: str) -> dict:
    vider = getattr(request.app.state, "vider_file", None)
    if vider is not None:
        await vider()
    res = await asyncio.to_thread(_verifier, iid)
    if res is None:
        return {
            "incident_id": iid, "statut": "non_persiste", "verdict": "pas encore écrit dans le journal",
            "etape_alteree": None, "element_altere": None, "raison": None, "sceau": None,
            "algorithme": journal_scelle.ALGORITHME,
            "verifie_a": datetime.now(timezone.utc).isoformat(),
        }
    return res


@routeur.get("/api/incidents/{iid}/verification")
async def incident_verification(iid: str, request: Request):
    """Recalcule la chaîne de l'incident depuis la base : `intacte` ou `altérée à l'étape N`."""
    if iid not in store.incidents:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    return await verification(request, iid)
