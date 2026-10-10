"""Fil des agents : chaque appel d'outil vu par la passerelle interne, avec son verdict.

Une entrée par décision de la passerelle sur un appel d'outil :

- `appel_outil` : l'appel tel qu'il se présente (autorisé, retenu pour l'analyste, ou refusé) ;
- `riposte` portant l'issue d'un appel retenu (`appel_libere`, `appel_annule`, `appel_refuse`,
  `couper`) : la suite donnée à cet appel.

La passerelle pose `details.verdict` et `details.raison`. Pour un événement plus ancien qui ne
les porte pas, le verdict se déduit des autres champs (retenu, violation_droits…). L'annonce
d'intention de l'agent (`maillon: intention`) n'est pas un appel : elle n'entre pas dans le fil.
"""

from __future__ import annotations

import html
import re

VERDICTS = ("autorise", "retenu", "refuse")

# Issue d'un appel retenu, portée par un événement `riposte`.
_ISSUES = {
    "appel_libere": ("autorise", "libéré par l’analyste"),
    "appel_annule": ("refuse", "annulé : l’analyste a coupé la session"),
    "appel_refuse": ("refuse", "refusé par la passerelle"),
    "couper": ("refuse", "annulé : l’analyste a coupé la session"),
}

_CTRL = re.compile(r"[\u0000-\u001f\u007f-\u009f]")


def _court(texte: object, limite: int = 140) -> str:
    """Texte court, sans caractère de contrôle, HTML échappé (sans toucher aux apostrophes)."""
    t = _CTRL.sub(" ", str(texte or ""))
    t = " ".join(t.split())
    if len(t) > limite:
        t = t[:limite].rstrip() + " […]"
    return html.escape(t, quote=False)


def _raison_deduite(details: dict, verdict: str) -> str:
    violation = details.get("violation_droits")
    scope = violation.get("scope_requis") if isinstance(violation, dict) else details.get("scope_requis")
    if details.get("droit_retire"):
        return f"droit {details['droit_retire']} retiré par l’analyste"
    if isinstance(violation, dict):
        return (f"droit {scope} absent du jeton" if verdict == "retenu"
                else f"droit {scope} absent du jeton, appel bloqué")
    if verdict == "retenu":
        canaris = (details.get("exfiltration") or {}).get("canaris") if isinstance(
            details.get("exfiltration"), dict) else None
        if canaris:
            return "paramètres porteurs du canari " + ", ".join(map(str, canaris))
        return "appel retenu pour l’analyste"
    if details.get("outil_mcp_suspect"):
        return "description d’outil MCP suspecte, appel journalisé"
    if scope:
        return f"droit {scope} dans le jeton" if details.get("scope_dans_jeton") else f"droit {scope}"
    return "aucun droit requis"


def entree(ev: dict, *, agent: str | None, incident_id: str | None) -> dict | None:
    """Entrée du fil pour un événement, ou None s'il ne décrit pas un appel d'outil."""
    if ev.get("source") != "interne":
        return None
    details = ev.get("details") or {}
    typ = ev.get("type")
    etape = "appel"
    if typ == "appel_outil":
        if details.get("maillon") == "intention" or not ev.get("outil"):
            return None
        verdict = details.get("verdict")
        if verdict not in VERDICTS:
            if isinstance(details.get("violation_droits"), dict):
                verdict = "retenu" if details.get("retenu") else "refuse"
            elif details.get("retenu"):
                verdict = "retenu"
            elif details.get("droit_retire"):
                verdict = "refuse"
            else:
                verdict = "autorise"
        raison = details.get("raison") or _raison_deduite(details, verdict)
    elif (typ == "riposte" and details.get("action") in _ISSUES
          and details.get("maillon") != "decision"):
        # Le maillon « décision » du mode protégé précède le maillon « résultat » : seul le
        # second dit ce qu'est devenu l'appel.
        etape = "issue"
        verdict_defaut, raison_defaut = _ISSUES[details["action"]]
        verdict = details.get("verdict") if details.get("verdict") in VERDICTS else verdict_defaut
        raison = details.get("raison") or raison_defaut
    else:
        return None

    violation = details.get("violation_droits")
    droit = (violation.get("scope_requis") if isinstance(violation, dict) else None) \
        or details.get("droit_retire") or details.get("scope_requis")
    return {
        "id": ev.get("id"),
        "heure": ev.get("horodatage"),
        "session_id": ev.get("session_id"),
        "agent": agent,
        "outil": ev.get("outil") or "réponse finale",
        "verdict": verdict,
        "raison": _court(raison),
        "droit": droit if isinstance(droit, str) else None,
        "etape": etape,
        "incident_id": incident_id,
    }
