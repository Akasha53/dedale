"""Routes des intégrations (SIEM, alertes, résumé du lundi) et leur branchement.

`brancher(app)` est la seule ligne ajoutée à main.py, après le relecteur : elle inclut les
routes, pose un observateur ASGI sur `POST /api/evenements` et sur les décisions, et suit ce
que le relecteur IA scelle (gestes au signal de fraude, demandes de validation métier). Après
chaque réponse 2xx, l'observateur demande à `notifications` d'appliquer la règle « qui reçoit
quoi » à l'incident de la session. La réponse au module ne l'attend jamais, et une erreur ici
ne remonte jamais au collecteur.

Les routes de lecture sont réservées à l'analyste (`auth.ANALYSTE`), sauf
`GET /api/validation/notifications`, réservée au validateur (`auth.VALIDATEUR`).
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from . import auth, notifications, resume_hebdo, sigma_regles, transfert_syslog
from .store import store

routeur = APIRouter()
_TAILLE_MAX = 256 * 1024
_DECISION = re.compile(r"^/api/incidents/([A-Za-z0-9_-]{1,40})/decision$")


@routeur.get("/api/resume-hebdo", dependencies=[auth.ANALYSTE])
async def resume_du_lundi(jours: int = Query(7, ge=1, le=31), format: str = "html"):
    """Mail du lundi, en aperçu : il n'est jamais envoyé. `format=json` rend les points."""
    points = resume_hebdo.generer(store, jours)
    if format == "json":
        return {**points, "ouverture": resume_hebdo.phrase_ouverture(points), "envoye": False}
    if format != "html":
        raise HTTPException(status_code=400, detail="format doit valoir 'html' ou 'json'")
    return HTMLResponse(resume_hebdo.rendre(points, resume_hebdo.lien_console()), headers={
        "Content-Security-Policy": resume_hebdo.CSP,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    })


@routeur.get("/api/integrations", dependencies=[auth.ANALYSTE])
async def etat_integrations():
    """Connecteurs (sans URL ni numéro en clair), règle « qui reçoit quoi », syslog, derniers envois."""
    return notifications.etat()


@routeur.get("/api/notifications", dependencies=[auth.ANALYSTE])
async def historique_notifications(limite: int = Query(50, ge=1, le=200)):
    """Derniers envois vus par le SOC : un envoi au validateur n'y montre que son canal et son statut."""
    with notifications._verrou:
        envois = [notifications.vue_soc(e) for e in list(notifications.historique)[:limite]]
    return {"notifications": envois, "syslog": list(transfert_syslog.historique)[:limite]}


@routeur.get("/api/validation/notifications", dependencies=[auth.VALIDATEUR])
async def notifications_validateur():
    """Ce que le validateur métier a reçu (webhook, SMS simulé), en entier, pour l'espace /validation."""
    return {"notifications": notifications.pour_validateur(),
            "note": "Le SMS n'est jamais envoyé : il est écrit dans le journal de démo."}


@routeur.get("/api/incidents/{iid}/notifications", dependencies=[auth.ANALYSTE])
async def notifications_incident(iid: str):
    """Qui serait prévenu pour ce dossier, par quel canal, avec quel texte ; ce qui est parti."""
    apercu = notifications.apercu_incident(iid)
    if apercu is None:
        raise HTTPException(status_code=404, detail=f"Incident inconnu : {iid}")
    return apercu


@routeur.get("/api/sigma/regles", dependencies=[auth.ANALYSTE])
async def catalogue_sigma(format: str = "yaml"):
    """Toutes les règles Sigma de Dédale, une par type d'incident, variantes comprises."""
    if format == "json":
        return {"regles": sigma_regles.catalogue()}
    if format != "yaml":
        raise HTTPException(status_code=400, detail="format doit valoir 'yaml' ou 'json'")
    return PlainTextResponse(sigma_regles.vers_yaml(sigma_regles.catalogue()), media_type="application/x-yaml")


class Observateur:
    """Middleware ASGI pur : laisse passer la requête, puis, la réponse partie en 2xx, signale la
    session (événement) ou l'incident (décision) au module des notifications."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        chemin = scope.get("path") or ""
        decision = _DECISION.match(chemin)
        if chemin != "/api/evenements" and decision is None:
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

        await self.app(scope, recevoir if decision is None else receive, envoyer)
        if not 200 <= statut.get("code", 0) < 300 or not notifications.actif():
            return
        try:
            if decision is not None:
                notifications.examiner(decision.group(1))
                return
            if taille > _TAILLE_MAX:
                return
            sid = json.loads(b"".join(morceaux)).get("session_id")
            if isinstance(sid, str) and sid:
                notifications.examiner_session(sid[:200])
        except Exception:  # les notifications ne font jamais échouer le collecteur
            pass


def _suivre_relecteur() -> None:
    """Après chaque relecture scellée (geste retenu, refusé…), la règle se rejoue sur l'incident."""
    from . import relecteur

    origine = relecteur.persister
    if getattr(origine, "suivi_par_integrations", False):
        return

    def persister(job: dict) -> None:
        origine(job)
        try:
            for enreg in job.get("evenements") or []:
                if isinstance(enreg, dict) and enreg.get("type") == "validation_demandee":
                    notifications.examiner_validation(enreg)
            for inc in job.get("incidents") or []:
                notifications.examiner(inc.id)
        except Exception:
            pass

    persister.suivi_par_integrations = True
    relecteur.persister = persister


def brancher(app: FastAPI) -> None:
    app.include_router(routeur)
    app.add_middleware(Observateur)
    _suivre_relecteur()
