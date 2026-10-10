"""Espace de validation métier : le responsable du salarié ou la finance confirme un geste retenu.

Ce n'est pas à l'équipe sécurité de valider chaque virement. Un geste critique que le relecteur
retient sans signal de fraude (bénéficiaire jamais payé, RIB qui change, montant hors des
usages, export massif) attend la confirmation de quelqu'un qui connaît l'affaire et a le droit
de la voir : le responsable du salarié ou la finance, identité `validateur` (`auth.VALIDATEUR`).
La SOC n'en reçoit rien : pas d'incident, et les actes `validation_demandee` et
`validation_decidee` lui arrivent réduits à leur sens (`besoin_d_en_connaitre.py`).

Le relecteur écrit la demande (`relecteur.verifier_geste`, événement `validation_demandee`) et
scelle la décision (`relecteur.valider_metier`, événement `validation_decidee` et entrée de sa
mémoire). Ce module en tire l'espace `/validation` :

- `GET /api/validation/file` : `{"gestes": [fiche…], "traites": [fiche…], "total": n}` ;
- `GET /api/validation/gestes/{id}` : la fiche d'un geste, `id` étant son `demande_id` ;
- `POST /api/validation/gestes/{id}/decision` `{"decision": "accorder" | "refuser", "motif",
  "validateur", "qualite": "responsable" | "finance"}`.

Toutes ces routes n'admettent que le validateur : l'analyste y reçoit 403, comme le validateur
sur la console du SOC. La fiche montre ce qu'il faut pour décider, et rien de la sécurité :
montant exact, bénéficiaire, IBAN réduit à ses quatre derniers chiffres, salarié qui demande,
motif de la retenue en français courant. Ni URL, ni score, ni signal technique, ni agent.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import auth, besoin_d_en_connaitre, identites
from .store import store
from .ws import diffuseur

_journal = logging.getLogger(__name__)

routeur = APIRouter()
QUALITES = {"responsable": "responsable", "finance": "finance"}
TITRES = {"virement": "Virement", "export_clients": "Export de fiches clients"}
MOTIF_MIN = 4
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


class DecisionMetierIn(BaseModel):
    decision: Literal["accorder", "refuser"]
    motif: str = Field(default="", max_length=300)
    validateur: str = Field(default="", max_length=60)
    qualite: Literal["responsable", "finance"] = "responsable"


# ------------------------------------------------------------------ lecture des demandes
def _actes() -> tuple[list[dict], dict[str, dict]]:
    """Demandes et décisions écrites par le relecteur. Sous verrou."""
    demandes, decisions = [], {}
    for e in store.evenements.values():
        if e.get("user_agent") != "dedale-relecteur" or e.get("surface") != "soc":
            continue
        if e.get("type") == "validation_demandee":
            demandes.append(e)
        elif e.get("type") == "validation_decidee":
            decisions[(e.get("details") or {}).get("demande_id")] = e
    return demandes, decisions


def _iban(beneficiaire: dict) -> str | None:
    """« •••• •••• •••• •••• 6655 » : seulement les quatre derniers chiffres du RIB demandé."""
    fin = re.sub(r"\D", "", str(beneficiaire.get("rib_demande") or ""))[-4:]
    return f"•••• •••• •••• •••• {fin}" if len(fin) == 4 else None


def _fiche(demande: dict, decision: dict | None) -> dict:
    d = demande.get("details") or {}
    faits = d.get("faits_memoire") or {}
    b = faits.get("beneficiaire") if isinstance(faits.get("beneficiaire"), dict) else {}
    geste = d.get("geste")
    sess = store.sessions.get(demande.get("session_id"))
    evs = [store.evenements[i] for i in sess.evenement_ids if i in store.evenements] if sess else []
    p = identites.personne(demande.get("session_id") or "", evs)
    raisons = [s.get("raison") for s in d.get("signaux") or [] if isinstance(s, dict) and s.get("raison")]
    fiche: dict[str, Any] = {
        "id": d.get("demande_id"),
        "geste": geste or "autre",
        "titre": TITRES.get(geste or "", "Geste sensible"),
        "montant_eur": d.get("montant_eur"),
        "lecture_du_montant": faits.get("lecture_du_montant"),
        "volume": d.get("volume") if geste == "export_clients" else None,
        "destination": ((faits.get("destination") or {}).get("domaine")
                        if geste == "export_clients" and isinstance(faits.get("destination"), dict) else None),
        "beneficiaire": None,
        "iban": None,
        "rib": None,
        "demande": d.get("texte"),
        "demandeur": {"nom": p["nom"] if p else None, "service": p["service"] if p else None},
        "motif": " ".join(raisons) or d.get("motif_salarie"),
        "raisons": raisons,
        "demande_le": demande.get("horodatage"),
        "statut": "en_attente",
        "decision": None,
    }
    if geste == "virement":
        fiche["beneficiaire"] = {"nom": d.get("beneficiaire") or b.get("nom"),
                                 "connu": bool(d.get("beneficiaire_connu")),
                                 "nature": b.get("nature"), "objet": b.get("objet"),
                                 "montant_habituel_eur": b.get("montant_habituel_eur")}
        fiche["iban"] = _iban(b)
        fiche["rib"] = d.get("rib") if d.get("rib") in ("habituel", "nouveau") else "non_precise"
    if decision is not None:
        dd = decision.get("details") or {}
        fiche["statut"] = "accorde" if dd.get("verdict") == "accorde" else "refuse"
        fiche["decision"] = {"decision": fiche["statut"], "validateur": dd.get("validateur"),
                             "motif": dd.get("motif"), "horodatage": decision.get("horodatage")}
    return fiche


def file_metier() -> dict:
    with store.lock:
        demandes, decisions = _actes()
        fiches = [_fiche(e, decisions.get((e.get("details") or {}).get("demande_id"))) for e in demandes]
    attente = sorted((f for f in fiches if f["statut"] == "en_attente"),
                     key=lambda f: f["demande_le"] or "", reverse=True)
    traites = sorted((f for f in fiches if f["statut"] != "en_attente"),
                     key=lambda f: (f["decision"] or {}).get("horodatage") or "", reverse=True)[:20]
    return {"gestes": attente, "traites": traites, "total": len(attente)}


def _trouver(did: str) -> dict | None:
    with store.lock:
        demandes, decisions = _actes()
        e = next((x for x in demandes if (x.get("details") or {}).get("demande_id") == did), None)
        return _fiche(e, decisions.get(did)) if e else None


# ------------------------------------------------------------------ routes
@routeur.get("/api/validation/file", dependencies=[auth.VALIDATEUR])
async def file_validation():
    """Gestes retenus qui attendent le responsable du salarié ou la finance."""
    return file_metier()


@routeur.get("/api/validation/gestes/{did}", dependencies=[auth.VALIDATEUR])
async def fiche_validation(did: str):
    fiche = _trouver(did) if _ID.match(did) else None
    if fiche is None:
        raise HTTPException(status_code=404, detail="Geste inconnu.")
    return fiche


@routeur.post("/api/validation/gestes/{did}/decision", dependencies=[auth.VALIDATEUR])
async def decider_validation(did: str, corps: DecisionMetierIn):
    """Accorder ou refuser un geste retenu. La décision est scellée et nourrit la mémoire du
    relecteur ; la SOC n'en voit que le sens."""
    from . import relecteur

    motif = " ".join((corps.motif or "").split())
    nom = " ".join((corps.validateur or "").split())
    if len(motif) < MOTIF_MIN:
        raise HTTPException(status_code=400, detail="Un motif est obligatoire : quelques mots suffisent.")
    if len(nom) < 2:
        raise HTTPException(status_code=400, detail="Indiquez votre nom : il signe la décision.")
    fiche = _trouver(did) if _ID.match(did) else None
    if fiche is None:
        raise HTTPException(status_code=404, detail="Geste inconnu.")
    if fiche["statut"] != "en_attente":
        raise HTTPException(status_code=409, detail="Ce geste a déjà été tranché.")
    verdict = "accorde" if corps.decision == "accorder" else "refuse"
    signataire = f"{nom[:28]} ({QUALITES[corps.qualite]})"
    try:
        r = relecteur.valider_metier(did, verdict, signataire, motif)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if r is None:
        raise HTTPException(status_code=409, detail="Ce geste a déjà été tranché.")
    return _trouver(did) or {"id": did, "statut": verdict}


def brancher(app: FastAPI, enfiler: Callable[[dict], None]) -> None:
    """Seule ligne ajoutée à main.py : routes de l'espace métier, vue minimisée du SOC (middleware
    HTTP et filtre du flux /ws), écrivain SQLite pour les consultations scellées."""
    besoin_d_en_connaitre.persister = enfiler
    app.include_router(routeur)
    app.add_middleware(besoin_d_en_connaitre.Minimiseur)
    diffuseur.filtre = besoin_d_en_connaitre.filtre_ws
