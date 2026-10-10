"""Routes de la gouvernance des agents : règles du SOC, inventaire, résistance.

Branchées sur l'app par `app.include_router(routeur)` dans main.py. Le Store est relu à
chaque appel dans `main` : un test qui remplace `main.store` est suivi ici aussi.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from . import inventaire, politiques, resistance

routeur = APIRouter()


def _store():
    from . import main

    return main.store


class PhraseIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phrase: str = Field(default="", max_length=500)
    mode: str = "regles"


class ActivationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phrase: str = Field(default="", max_length=500)
    regle: dict[str, Any] | None = None
    analyste: str = "inconnu"


class EvaluationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str | None = None
    session_id: str | None = None
    outil: str | None = None
    scope: str | None = None
    parametres: dict[str, Any] = Field(default_factory=dict)
    horodatage: str | None = None


# ------------------------------------------------------------------ règles du SOC
@routeur.post("/api/politiques/analyser")
async def analyser_politique(corps: PhraseIn):
    """Phrase en français → règle proposée et reformulation à faire valider. N'active rien."""
    if not corps.phrase.strip():
        raise HTTPException(status_code=400, detail="La phrase est vide.")
    if corps.mode not in ("regles", "modele"):
        raise HTTPException(status_code=400, detail="mode doit valoir 'regles' ou 'modele'")
    if corps.mode == "modele":
        return await politiques.analyser_avec_modele(corps.phrase)
    return politiques.analyser(corps.phrase)


@routeur.post("/api/politiques", status_code=201)
async def activer_politique(corps: ActivationIn):
    """Active une règle relue par l'analyste : la règle proposée, ou la phrase réanalysée."""
    regle = corps.regle
    if regle is None:
        analyse = politiques.analyser(corps.phrase)
        if not analyse["comprise"]:
            raise HTTPException(status_code=400, detail=analyse["texte"])
        regle = analyse["regle"]
    try:
        return politiques.registre.activer(regle, corps.phrase, corps.analyste)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@routeur.get("/api/politiques")
async def lister_politiques(toutes: bool = False):
    compte = politiques.declenchements(_store())
    regles = [{**r, **compte.get(r["id"], {"declenchements": 0, "dernier_declenchement": None})}
              for r in politiques.registre.lister(toutes=toutes)]
    return {"politiques": regles, "mode_modele": politiques.modele_actif(),
            "formes": politiques.FORMES}


@routeur.delete("/api/politiques/{rid}")
async def retirer_politique(rid: str, analyste: str = "inconnu"):
    r = politiques.registre.retirer(rid, analyste)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Règle active inconnue : {rid}")
    return {"retiree": r["id"], "politique": r}


@routeur.post("/api/politiques/evaluer")
async def evaluer_politiques(corps: EvaluationIn):
    """Appelé par la passerelle avant un appel d'outil : quelle règle active s'applique ?"""
    ctx = corps.model_dump()
    if not ctx.get("agent") and ctx.get("session_id"):
        sess = _store().sessions.get(ctx["session_id"])
        ctx["agent"] = sess.agent if sess is not None else None
    return politiques.evaluer(ctx)


# ------------------------------------------------------------------ inventaire
@routeur.get("/api/agents/{agent_id}")
async def agent_detail(agent_id: str):
    f = inventaire.fiche(_store(), agent_id)
    if f is None:
        raise HTTPException(status_code=404, detail=f"Agent inconnu : {agent_id}")
    return f


# ------------------------------------------------------------------ résistance
@routeur.get("/api/agents/{agent_id}/resistance")
async def agent_resistance(agent_id: str):
    connu = (agent_id in inventaire.PAR_ID or resistance.agent_mesure(agent_id)
             or inventaire.fiche(_store(), agent_id) is not None)
    if not connu:
        raise HTTPException(status_code=404, detail=f"Agent inconnu : {agent_id}")
    return resistance.pour_agent(agent_id)


@routeur.post("/api/resistance/campagnes", status_code=201)
async def recevoir_campagne(corps: dict[str, Any]):
    try:
        return resistance.registre.enregistrer(corps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@routeur.get("/api/resistance/campagnes")
async def lister_campagnes(limite: int = Query(20, ge=1, le=200)):
    return {"campagnes": resistance.registre.lister()[-limite:][::-1],
            "etiquette": resistance.ETIQUETTE}
