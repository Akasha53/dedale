"""Règles écrites par le SOC, appliquées par la passerelle avant chaque appel d'outil.

L'analyste écrit ses règles en français dans la console ; le backend les traduit et les
garde (`backend/app/politiques.py`). Avant un appel, la passerelle demande au backend
`POST /api/politiques/evaluer` si une règle active s'applique, puis :

- `bloquer` : l'appel ne s'exécute pas ; l'agent reçoit un refus et continue ;
- `retenir` : l'appel attend une décision de l'analyste prise après la retenue
  (`reprendre` le libère, `couper` arrête l'agent, rien dans le délai le refuse) ;
- `alerter` : l'appel passe, un événement `regle` ouvre une alerte dans la console.

Chaque déclenchement part au backend avec `details.politique` : il devient un maillon
« règle n°… » de la boîte noire. Si le backend ne répond pas, aucune règle ne s'applique et
l'appel suit son cours, comme pour tout le reste de la passerelle.
`DEDALE_POLITIQUES=off` coupe cette vérification.
"""

from __future__ import annotations

import os

from .boite_noire import _poster
from .enregistreur import maintenant_iso, masquer

CHEMIN = "/api/politiques/evaluer"


def actif() -> bool:
    return os.environ.get("DEDALE_POLITIQUES", "on").lower() != "off"


def demander(base: str, corps: dict) -> dict | None:
    """Question au backend. None s'il est muet ou ne connaît pas la route."""
    return _poster(base, CHEMIN, corps, timeout=1.0)


def appliquer(passerelle, nom: str, params: dict, scope: str | None):
    """None : l'appel continue. Sinon, le refus à rendre à l'agent.
    Lève AgentCoupe si l'analyste coupe l'agent pendant une retenue."""
    from .passerelle import AUTORISE, REFUSE, RETENU, AgentCoupe

    base = getattr(passerelle.boite, "base", None)
    if not actif() or not base:
        return None
    rep = demander(base, {
        "agent": passerelle.agent, "session_id": passerelle.session_id, "outil": nom,
        "scope": scope, "parametres": masquer(params, passerelle.jetons),
        "horodatage": maintenant_iso(),
    })
    if not isinstance(rep, dict) or rep.get("verdict") not in ("bloquer", "retenir", "alerter"):
        return None
    regle = rep.get("regle") if isinstance(rep.get("regle"), dict) else {}
    pol = {k: regle.get(k) for k in ("id", "numero", "effet", "texte", "enonce", "constat")}
    numero = f"règle n°{regle.get('numero')}"
    sid = passerelle.session_id
    # `scope_vise` et non `scope_requis` : un appel arrêté ne compte pas comme droit utilisé.
    base_details = {"parametres": params, "politique": pol, "scope_vise": scope}

    if rep["verdict"] == "alerter":
        passerelle._tracer("regle", {"outil": nom, "politique": pol.get("id"), "effet": "alerter"})
        passerelle._emettre("regle", "outil", sid, outil=nom, details={
            **base_details, "verdict": AUTORISE, "raison": f"{numero} : alerte, appel autorisé"})
        return None

    if rep["verdict"] == "bloquer":
        raison = f"{numero} du SOC : appel bloqué"
        passerelle.appels_refuses.append({"outil": nom, "raison": raison})
        passerelle._tracer("appel_outil", {"outil": nom, "refuse": True, "politique": pol.get("id")})
        passerelle._emettre("appel_outil", "outil", sid, outil=nom, details={
            **base_details, "verdict": REFUSE, "raison": raison})
        return {"erreur": "appel refusé par une règle du SOC", "outil": nom, "raison": raison,
                "regle": pol.get("numero")}

    # retenir : seule une décision prise après la retenue compte.
    passerelle._decisions_avant = passerelle._compter_decisions()
    passerelle.etat = "suspendue"
    passerelle._tracer("appel_outil", {"outil": nom, "retenu": True, "politique": pol.get("id")})
    passerelle._emettre("appel_outil", "outil", sid, outil=nom, details={
        **base_details, "verdict": RETENU, "raison": f"{numero} du SOC : en attente de l’analyste"})
    decision = passerelle._attendre_decision_fraiche()
    if decision == "couper":
        passerelle.jeton_revoque = True
        passerelle.etat = "coupee"
        if passerelle.jeton_tache is not None:
            passerelle.jeton_tache.revoquer()
        passerelle._tracer("riposte", {"action": "couper", "jeton_revoque": True})
        passerelle._emettre("riposte", "outil", sid, outil=nom, details={
            "action": "couper", "jeton_revoque": True, "verdict": REFUSE,
            "raison": "annulé : l’analyste a coupé la session"})
        raise AgentCoupe("session coupée par l'analyste")
    if decision == "reprendre":
        passerelle.etat = "active"
        passerelle._tracer("riposte", {"action": "reprendre", "politique": pol.get("id")})
        passerelle._emettre("riposte", "outil", sid, outil=nom, details={
            "action": "appel_libere", "verdict": AUTORISE, "raison": "libéré par l’analyste"})
        return None
    raison = f"{numero} du SOC : aucune décision dans le délai"
    passerelle.appels_refuses.append({"outil": nom, "raison": raison})
    passerelle._tracer("riposte", {"action": "bloquer", "raison": "pas de décision"})
    passerelle._emettre("riposte", "outil", sid, outil=nom, details={
        "action": "appel_refuse", "verdict": REFUSE, "raison": "aucune décision dans le délai, jeton intact"})
    return {"erreur": "appel refusé par une règle du SOC", "outil": nom, "raison": raison,
            "regle": pol.get("numero")}
