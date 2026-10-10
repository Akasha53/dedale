"""Routes de l'ancrage sur Avalanche (voie d'exploration) et boucle de fond qui prépare les racines.

`brancher(app)` est la seule ligne ajoutée à main.py : elle inclut les routes et glisse la
boucle d'ancrage dans le cycle de vie existant, après l'ouverture de la base et avant sa
fermeture. La boucle se réveille toutes les deux secondes et ne fait rien la plupart du temps :
un lot se prépare quand un incident vient d'être clos, et toutes les dix minutes s'il y a du
nouveau. Par défaut (`DEDALE_ANCRAGE=file`), elle reste locale et silencieuse : aucun appel
réseau, aucune erreur dans les journaux.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path

from fastapi import APIRouter, FastAPI

from . import ancrage, config, journal_scelle

routeur = APIRouter()
_journal = logging.getLogger(__name__)


def _lire(verifier: bool) -> dict:
    chemin = Path(config.CHEMIN_DB)
    if not chemin.is_file():
        return {**ancrage.etat(None), "verification": None}
    conn = journal_scelle.ouvrir_lecture(chemin)
    try:
        sortie = ancrage.etat(conn)
        sortie["verification"] = ancrage.verifier_base(conn, ancrage.client_rpc()) if verifier else None
        return sortie
    finally:
        conn.close()


@routeur.get("/api/ancrage")
async def etat_ancrage(verifier: bool = False):
    """Adresse d'ancrage, file des lots, dernière ancre, empreintes des clés de signature.
    `?verifier=true` recalcule tout le journal et relit les ancres sur la chaîne."""
    return await asyncio.to_thread(_lire, verifier)


@routeur.post("/api/ancrage/ancrer")
async def ancrer_maintenant():
    """Demande un lot tout de suite (sinon : à la clôture d'un incident, ou toutes les dix
    minutes). Sans effet si l'ancrage est coupé ; deux lots restent espacés de 20 s."""
    if ancrage.mode() == "off":
        return {"demande": False, "raison": "ancrage coupé (DEDALE_ANCRAGE=off)"}
    ancrage.demander_lot()
    return {"demande": True}


async def _boucle(app: FastAPI) -> None:
    dernier_periodique = time.monotonic()
    while True:
        await asyncio.sleep(ancrage.TICK)
        if ancrage.mode() == "off":
            continue
        motif = ancrage.motif_a_traiter(dernier_periodique)
        if motif is None:
            continue
        if motif == "periodique":
            dernier_periodique = time.monotonic()
        vider = getattr(app.state, "vider_file", None)
        if vider is not None:
            await vider()  # le lot ne porte que ce que l'écrivain a déjà posé en base
        try:
            await asyncio.to_thread(ancrage.cycle, motif=motif)
        except Exception:  # l'ancrage attend en silence, il ne fait jamais tomber le backend
            _journal.debug("Ancrage reporté au prochain cycle", exc_info=True)


def brancher(app: FastAPI) -> None:
    app.include_router(routeur)
    origine = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def cycle_de_vie(app_: FastAPI):
        async with origine(app_) as etat:
            tache = asyncio.create_task(_boucle(app_))
            try:
                yield etat
            finally:
                tache.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await tache

    app.router.lifespan_context = cycle_de_vie
