"""Routes du relecteur IA et branchement sur le collecteur.

`brancher(app, enfiler)` est la seule ligne ajoutée à main.py : elle inclut les routes, donne au
relecteur l'écrivain SQLite et WS, et pose un observateur ASGI sur `POST /api/evenements`. Après
une réponse 2xx, l'observateur lit le `session_id` du corps reçu et laisse le relecteur lancer ce
qui l'attend (geste à quatre yeux, pré-tri). La réponse au module ne l'attend jamais.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from fastapi import APIRouter, Body, FastAPI, HTTPException

from . import auth, memoire_relecteur, relecteur, synthese

routeur = APIRouter()
_TAILLE_MAX = 256 * 1024
_DECISION = re.compile(r"^/api/incidents/([A-Za-z0-9_-]{1,40})/decision$")


@routeur.get("/api/relecteur")
async def etat_relecteur():
    """Moteur configuré, moteur qui sera essayé, modèle, délai, suspension après une limite."""
    return relecteur.etat()


@routeur.get("/api/relecteur/file")
async def file_a_regarder():
    """Incidents ouverts où le relecteur doute, ou de priorité haute."""
    return relecteur.file_a_regarder()


@routeur.get("/api/relecteur/demandes/{demande_id}", dependencies=[auth.VERDICT_POSTE])
async def relecture_demande(demande_id: str):
    """Ce que le relecteur a décidé d'un geste à quatre yeux (`en_cours`, puis `tranchee`)."""
    d = relecteur.relecture_demande(demande_id[:80])
    if d is None:
        raise HTTPException(status_code=404, detail=f"Demande inconnue : {demande_id[:80]}")
    return d


@routeur.post("/api/relecteur/verifier", dependencies=[auth.ECRIVAINS])
async def verifier(corps: dict = Body(...)):
    """Geste critique du poste : `passe` (aucun signal, aucune pop-up), `accorde`, `retenu` (à faire
    confirmer par le responsable) ou `refuse` (signal de fraude, la SOC est prévenue)."""
    propre = {k: (str(v)[:2000] if isinstance(v, str) else v) for k, v in (corps or {}).items()
              if k in relecteur.CHAMPS_GESTE + ("demande_id", "session_id") and isinstance(v, (str, int, float))}
    return await relecteur.verifier_geste(propre)


@routeur.get("/api/validation/relecteur", dependencies=[auth.VALIDATEUR])
async def validations(toutes: bool = False):
    """Gestes retenus à faire confirmer par le responsable ou la finance. Pas pour la SOC."""
    liste = relecteur.demandes_de_validation(toutes)
    return {"validations": liste, "total": len(liste)}


@routeur.post("/api/validation/relecteur/{demande_id}", dependencies=[auth.VALIDATEUR])
async def valider(demande_id: str, corps: dict = Body(...)):
    """Le validateur métier accorde ou refuse ; sa décision entre dans la mémoire du relecteur."""
    try:
        r = relecteur.valider_metier(demande_id[:80], str((corps or {}).get("verdict", "")),
                                     str((corps or {}).get("validateur") or "validateur"),
                                     str((corps or {}).get("motif") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if r is None:
        raise HTTPException(status_code=404, detail="Demande inconnue ou déjà tranchée.")
    return r


@routeur.get("/api/relecteur/memoire")
async def memoire():
    """Décisions passées confirmées ou renversées par un analyste (le geste, jamais la personne)."""
    with relecteur.store.lock:
        entrees = memoire_relecteur.entrees()
    return {"entrees": entrees, "total": len(entrees)}


@routeur.get("/api/incidents/{iid}/tri")
async def tri_incident(iid: str):
    """Pré-tri de l'incident : priorité, décision proposée, motif, confiance, qui a tranché."""
    d = relecteur.tri_incident(iid)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    d["certitude"] = _certitude(iid)
    return d


def _certitude(iid: str) -> dict | None:
    """Certitude de l'incident, prise à la synthèse : la console l'affiche à l'identique dans le
    résumé et dans le pré-tri. `confiance` reste l'avis propre du relecteur (son doute)."""
    detail = relecteur.store.incident_detail(iid)
    if detail is None:
        return None
    sess = relecteur.store.session_detail(detail["session_id"]) or {}
    try:
        return synthese.certitude(detail, sess.get("evenements", []))
    except Exception:  # le pré-tri reste lisible sans certitude
        return None


class Observateur:
    """Middleware ASGI pur : recopie le corps de `POST /api/evenements` sans le retenir, puis,
    la réponse partie, signale la session au relecteur. Après `POST /api/incidents/{id}/decision`,
    note dans la mémoire du relecteur la décision d'un analyste qui confirme ou renverse."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        decision = _DECISION.match(scope.get("path") or "") if scope.get("method") == "POST" else None
        if decision and scope.get("type") == "http":
            statut_d: dict = {}

            async def envoyer_d(message):
                if message.get("type") == "http.response.start":
                    statut_d["code"] = message.get("status", 0)
                await send(message)

            await self.app(scope, receive, envoyer_d)
            if 200 <= statut_d.get("code", 0) < 300:
                try:
                    job = memoire_relecteur.apres_decision(decision.group(1), relecteur.faits_geste)
                    if job:
                        relecteur.persister(job)
                except Exception:  # la mémoire ne fait jamais échouer une décision
                    pass
            return
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
