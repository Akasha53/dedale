"""Console API de Dédale — FastAPI, port 8700.

Chemin chaud (POST /api/evenements) : classement synchrone en mémoire (quelques µs), puis
mise en file de la persistance SQLite et de la diffusion WS. La réponse part en < 50 ms et ne
fait jamais échouer la surface appelante.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from copy import deepcopy

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, db, exports, nis2
from .models import DecisionIn, EvenementIn, LeurreIn
from .store import store
from .ws import diffuseur

# La file est créée dans le cycle de vie, liée à la boucle qui tourne (robuste aux tests qui
# ouvrent plusieurs boucles). _etat porte la file courante pour les handlers.
_etat: dict = {"file": None, "erreur_ecriture": None}
_tache_ecrivain: asyncio.Task | None = None
_journal = logging.getLogger(__name__)


async def _ecrivain(file: asyncio.Queue, conn) -> None:
    """Unique écrivain SQLite + diffusion WS. Isole la persistance du chemin de réponse."""
    try:
        while True:
            job = await file.get()
            try:
                if job is None:
                    break
                for ev in job.get("evenements", []):
                    db.ecrire_evenement(conn, ev)
                for s in job.get("sessions", []):
                    db.ecrire_session(conn, s)
                for l in job.get("leurres", []):
                    db.ecrire_leurre(conn, l)
                for i in job.get("incidents", []):
                    db.ecrire_incident(conn, i)
                for d in job.get("decisions", []):
                    db.ecrire_decision(conn, d)
                conn.commit()
                for type_, donnees in job.get("diffusions", []):
                    await diffuseur.diffuser(type_, donnees)
            except Exception as exc:
                # La surface appelante ne tombe pas, mais le défaut reste visible au SOC.
                conn.rollback()
                _etat["erreur_ecriture"] = str(exc)
                _journal.exception("Échec de persistance Dédale")
            finally:
                file.task_done()
    finally:
        conn.close()


@contextlib.asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    global _tache_ecrivain
    # La lecture est obligatoire : une base illisible ne doit jamais lancer un SOC vide.
    conn = db.ouvrir()
    try:
        store.restaurer(db.lire(conn))
    except Exception:
        conn.close()
        raise
    if store.journaux_incomplets:
        _journal.warning(
            "Reprise d'une base ancienne avec %d journaux de session incomplets",
            len(store.journaux_incomplets),
        )
    file: asyncio.Queue = asyncio.Queue()
    _etat["file"] = file
    _etat["erreur_ecriture"] = None
    _tache_ecrivain = asyncio.create_task(_ecrivain(file, conn))
    try:
        yield
    finally:
        await file.put(None)
        if _tache_ecrivain is not None:
            # Vide toute la file avant de fermer la connexion sur arrêt normal.
            await _tache_ecrivain
        _etat["file"] = None


app = FastAPI(title="Dédale — Console API", version=__version__, lifespan=cycle_de_vie)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _enfiler(job: dict) -> None:
    file = _etat.get("file")
    if file is None:  # service non démarré : la persistance est optionnelle, on ne bloque pas.
        return
    try:
        # Les dataclasses sont mutables ; figer chaque transaction à l'instant de l'appel.
        file.put_nowait(deepcopy(job))
    except asyncio.QueueFull:  # pragma: no cover - file non bornée
        pass


# ---------------------------------------------------------------- Collecteur
@app.post("/api/evenements")
async def recevoir_evenement(ev: EvenementIn):
    res = store.ingerer(ev)
    leurre = store.leurres.get(res["evenement"]["leurre_id"])
    job = {
        "evenements": [res["evenement"]],
        "sessions": [res["session"]],
        "leurres": [leurre] if leurre is not None and ev.type == "leurre_touche" else [],
        "incidents": [res["incident"]] if res["incident"] is not None else [],
        "diffusions": res["diffusions"],
    }
    _enfiler(job)
    return res["reponse"]


@app.post("/api/leurres")
async def enregistrer_leurres(leurres: list[LeurreIn]):
    objets = store.enregistrer_leurres(leurres)
    _enfiler({"leurres": objets})
    return {"enregistres": len(objets), "ids": [l.id for l in objets]}


@app.get("/api/leurres")
async def lister_leurres():
    return {"leurres": store.inventaire_leurres()}


# ---------------------------------------------------------------- Sessions
@app.get("/api/sessions")
async def lister_sessions():
    return {"sessions": store.liste_sessions()}


@app.get("/api/sessions/{sid}")
async def session_detail(sid: str):
    d = store.session_detail(sid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Session inconnue : {sid}")
    return d


# ---------------------------------------------------------------- Incidents
@app.get("/api/incidents")
async def lister_incidents():
    return {"incidents": store.liste_incidents()}


# ---------------------------------------------------------------- Agents internes (V2)
@app.get("/api/agents")
async def lister_agents():
    """Droits des agents internes : accordés vs utilisés vs nécessaires (moindre privilège)."""
    return {"agents": store.liste_agents()}


@app.get("/api/incidents/{iid}")
async def incident_detail(iid: str):
    d = store.incident_detail(iid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    return d


@app.post("/api/incidents/{iid}/decision")
async def decider(iid: str, decision: DecisionIn):
    try:
        res = store.decider(iid, decision.action, decision.analyste)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if res is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    # La décision et ses deux états associés forment une seule transaction SQLite.
    inc = store.incidents.get(iid)
    sess = store.sessions.get(inc.session_id) if inc else None
    _enfiler({
        "decisions": [res["journal"]],
        "incidents": [inc] if inc else [],
        "sessions": [sess] if sess else [],
        "diffusions": res["diffusions"],
    })
    return res["incident"]


@app.get("/api/incidents/{iid}/nis2")
async def incident_nis2(iid: str):
    d = store.incident_detail(iid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    brouillon = await nis2.generer(d)
    return {"incident_id": iid, **brouillon}


@app.get("/api/incidents/{iid}/export")
async def incident_export(iid: str, format: str = "ecs"):
    d = store.incident_detail(iid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    fmt = format.lower()
    if fmt == "ecs":
        sess = store.session_detail(d["session_id"]) or {}
        return exports.vers_ecs(d, sess.get("evenements", []))
    if fmt == "sigma":
        return PlainTextResponse(exports.vers_sigma(d), media_type="application/x-yaml")
    raise HTTPException(status_code=400, detail="format doit valoir 'ecs' ou 'sigma'")


# ---------------------------------------------------------------- Mesures
@app.get("/api/mesures")
async def mesures():
    from . import mesures as m
    return m.calculer(store)


@app.get("/api/sante")
async def sante():
    if _etat["erreur_ecriture"] is not None:
        return JSONResponse(status_code=503, content={
            "service": "dedale-backend", "version": __version__,
            "statut": "degrade", "erreur": "persistance SQLite indisponible",
        })
    statut = "degrade" if store.journaux_incomplets else "ok"
    return {
        "service": "dedale-backend", "version": __version__, "statut": statut,
        "journaux_anciens_incomplets": len(store.journaux_incomplets),
    }


# ---------------------------------------------------------------- Temps réel
@app.websocket("/ws")
async def flux(ws: WebSocket):
    await diffuseur.connecter(ws)
    try:
        while True:
            # On ne lit rien d'utile du client ; la boucle garde la connexion ouverte.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await diffuseur.deconnecter(ws)


@app.exception_handler(Exception)
async def erreur_generale(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(status_code=500, content={"erreur": "erreur interne", "detail": str(exc)})


# ---------------------------------------------------------------- Console web
# Une fois la console construite (console/dist), le backend la sert sur 8700.
_DIST = config.RACINE / "console" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="console")
else:
    @app.get("/")
    async def racine():
        return {
            "service": "Dédale — Console API",
            "version": __version__,
            "note": "Console web non construite (console/dist absent). API sous /api, flux sous /ws.",
        }
