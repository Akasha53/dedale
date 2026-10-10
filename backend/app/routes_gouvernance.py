"""Routes de la gouvernance des agents : règles du SOC, inventaire, résistance.

Branchées sur l'app par `app.include_router(routeur)` dans main.py. Le Store est relu à
chaque appel dans `main` : un test qui remplace `main.store` est suivi ici aussi.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from . import auth, inventaire, politiques, resistance

routeur = APIRouter()


def _store():
    from . import main

    return main.store


def _aligner_droits() -> None:
    """Droits retirés par les règles de moindre privilège : Store aligné, sessions persistées."""
    from . import main

    st = main.store
    sessions = politiques.synchroniser(st)
    if sessions:
        main._enfiler({"sessions": sessions,
                       "diffusions": [("session", st._session_vue(x)) for x in sessions]})


class PhraseIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phrase: str = Field(default="", max_length=500)
    # Sans mode : le modèle lit la phrase, les motifs prennent le relais. « regles » : motifs seuls.
    mode: str | None = None


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
@routeur.post("/api/politiques/analyser", dependencies=[auth.ANALYSTE])
async def analyser_politique(corps: PhraseIn):
    """Phrase en français → règle proposée et reformulation à faire valider. N'active rien.
    `compris_par` dit qui a compris : « modèle » ou « motifs »."""
    if not corps.phrase.strip():
        raise HTTPException(status_code=400, detail="La phrase est vide.")
    if corps.mode not in (None, "regles", "modele"):
        raise HTTPException(status_code=400, detail="mode doit valoir 'regles' ou 'modele'")
    _aligner_droits()
    if corps.mode == "regles":
        return politiques.analyser(corps.phrase, _store())
    return await politiques.analyser_avec_modele(corps.phrase, _store())


@routeur.post("/api/politiques", status_code=201, dependencies=[auth.ANALYSTE])
async def activer_politique(corps: ActivationIn):
    """Active une règle relue par l'analyste : la règle proposée, ou la phrase réanalysée.
    Une règle de moindre privilège retire les droits tout de suite. `regle.remplace` (posé par
    l'agent des règles pour une modification) retire l'ancienne règle dans le même geste."""
    _aligner_droits()
    regle = corps.regle
    if regle is None:
        analyse = politiques.analyser(corps.phrase, _store())
        if not analyse["comprise"] or analyse["regle"] is None:
            raise HTTPException(status_code=400, detail=analyse["texte"])
        regle = analyse["regle"]
    remplace = regle.get("remplace") if isinstance(regle, dict) else None
    try:
        entree = politiques.registre.activer(regle, corps.phrase, corps.analyste, _store(),
                                             remplace=remplace if isinstance(remplace, str) else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _aligner_droits()
    return entree


@routeur.get("/api/politiques")
async def lister_politiques(toutes: bool = False):
    _aligner_droits()
    compte = politiques.declenchements(_store())
    regles = [{**r, **compte.get(r["id"], {"declenchements": 0, "dernier_declenchement": None})}
              for r in politiques.registre.lister(toutes=toutes)]
    moteur, _raison = politiques.moteur_modele()
    return {"politiques": regles, "mode_modele": politiques.modele_actif(),
            "lecteur": {"moteur": moteur or "motifs",
                        "modele": politiques._nom_modele() if moteur else None},
            "journal": politiques.registre.verifier(),
            "formes": politiques.FORMES, "exemple_moindre": politiques.EXEMPLE_MOINDRE}


@routeur.get("/api/politiques/agent")
async def suivi_agent_regles(apres: int | None = None):
    """Agent des règles en direct : la console lit `derniere` avant d'envoyer sa phrase, puis
    interroge `?apres=<derniere>` pendant que l'instance travaille (appels, puis fermeture)."""
    from . import agent_regles

    return agent_regles.suivi(apres)


@routeur.get("/api/politiques/journal")
async def journal_politiques():
    """Actes scellés : activations, retraits de règle, droits retirés puis rendus."""
    return {"actes": politiques.registre.journal(), "verification": politiques.registre.verifier()}


@routeur.delete("/api/politiques/{rid}", dependencies=[auth.ANALYSTE])
async def retirer_politique(rid: str, analyste: str = "inconnu"):
    """Retire une règle. Pour une règle de moindre privilège, rend les droits aux agents."""
    r = politiques.registre.retirer(rid, analyste)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Règle active inconnue : {rid}")
    _aligner_droits()
    return {"retiree": r["id"], "politique": r}


@routeur.post("/api/politiques/evaluer", dependencies=[auth.PASSERELLE])
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


@routeur.post("/api/resistance/campagnes", status_code=201, dependencies=[auth.PASSERELLE])
async def recevoir_campagne(corps: dict[str, Any]):
    try:
        return resistance.registre.enregistrer(corps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@routeur.get("/api/resistance/campagnes")
async def lister_campagnes(limite: int = Query(20, ge=1, le=200)):
    return {"campagnes": resistance.registre.lister()[-limite:][::-1],
            "etiquette": resistance.ETIQUETTE}
