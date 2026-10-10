"""Boîte noire : reconstruction de la chaîne d'un incident.

À partir des événements d'une session (ou d'un canari touché), on recompose l'enchaînement
  document/mail piégé -> consigne lue -> action -> tentative de sortie de données.
Chaque étape porte un résumé NEUTRALISÉ : le texte piégé n'est jamais réinjecté tel quel.
"""

from __future__ import annotations

from typing import Any

from . import securite

# Ordre canonique des étapes de la boîte noire.
ORDRE_ETAPES = ["appat", "consigne_lue", "action", "tentative_sortie", "riposte"]

_LIBELLES = {
    "appat": "Document/mail piégé rencontré",
    "consigne_lue": "Consigne cachée lue",
    "action": "Action sur une route ou un outil découvert",
    "tentative_sortie": "Tentative de sortie de données",
    "riposte": "Riposte appliquée",
}

# Correspondance étape interne -> phase lue par la console.
_PHASE = {
    "appat": "entree",
    "consigne_lue": "consigne",
    "action": "outil",
    "tentative_sortie": "sortie",
    "riposte": "riposte",
}


def _cadre_technique(ident: str) -> str:
    return "ATLAS" if ident.upper().startswith(("AML", "ATLAS")) else "ATT&CK"


def _techniques(leurre) -> list[dict]:
    if leurre is None:
        return []
    return [{"id": t, "nom": t, "cadre": _cadre_technique(t)} for t in getattr(leurre, "techniques", [])]


def _risques(leurre) -> list[dict]:
    if leurre is None:
        return []
    return [{"id": r, "nom": r} for r in getattr(leurre, "risques", [])]


def gravite(chaine: list[dict], source: str) -> str:
    phases = {e.get("etape") for e in chaine}
    if "tentative_sortie" in phases:
        return "critique"
    if "consigne_lue" in phases or source == "interne":
        return "haute"
    if "action" in phases:
        return "moyenne"
    return "faible"


def resume(chaine: list[dict], classement: str, source: str) -> str:
    exfil = any(e.get("etape") == "tentative_sortie" for e in chaine)
    return (
        f"Session classée {classement} sur la surface {source}. "
        f"Chaîne de {len(chaine)} étape(s). "
        f"Tentative d'exfiltration : {'oui' if exfil else 'non constatée'}."
    )

# Champs de details susceptibles de contenir du texte piégé (à neutraliser avant exposition).
_CHAMPS_PIEGES = ("consigne", "consigne_lue", "contenu", "extrait", "objectif", "charge_utile", "payload", "consigne_outil")


def _etape_pour(ev: dict, leurres: dict[str, Any]) -> str | None:
    """Classe un événement dans une étape de la chaîne, ou None s'il n'en est pas."""
    nature = None
    if ev.get("leurre_id") and ev["leurre_id"] in leurres:
        nature = leurres[ev["leurre_id"]].nature
    typ = ev.get("type")
    surface = ev.get("surface")
    details = ev.get("details") or {}

    if typ == "riposte":
        return "riposte"
    if typ == "sortie_agent" or details.get("exfiltration"):
        return "tentative_sortie"
    # Outil MCP piégé : la consigne vit dans la DESCRIPTION de l'outil. Qu'elle soit portée par
    # le canari touché (nature outil_mcp_piege) ou par l'appel qui découvre l'outil, c'est l'étape
    # « consigne lue ».
    if nature == "outil_mcp_piege" or details.get("outil_mcp_suspect"):
        return "consigne_lue"
    # Tentative d'action hors du périmètre de droits : une action refusée (moindre privilège).
    if details.get("violation_droits"):
        return "action"
    # La consigne lue prime : un leurre peut être l'appât ET porter l'instruction cachée.
    if nature == "consigne_cachee" or details.get("consigne") or details.get("consigne_lue"):
        return "consigne_lue"
    if typ == "leurre_touche" and nature in ("canari_document", "canari_mail", "faux_secret"):
        return "appat"
    if surface in ("doc", "document", "mail") or typ == "entree_agent":
        return "appat"
    if typ in ("appel_outil",) or (typ == "requete" and (details.get("decouvert_dans_doc") or nature == "fausse_route")):
        return "action"
    return None


def construire_chaine(evenements: list[dict], leurres: dict[str, Any]) -> list[dict]:
    """Chaîne de la boîte noire. Chaque étape porte les champs internes (etape, resume) ET les
    champs lus par la console (ordre, phase, titre, detail, techniques, risques)."""
    etapes: list[dict] = []
    for ev in sorted(evenements, key=lambda e: (e.get("horodatage") or "", e.get("id", 0))):
        etape = _etape_pour(ev, leurres)
        if etape is None:
            continue
        details = ev.get("details") or {}
        leurre = leurres.get(ev.get("leurre_id")) if ev.get("leurre_id") else None
        violation = details.get("violation_droits") if isinstance(details.get("violation_droits"), dict) else None
        texte_source = next((details[c] for c in _CHAMPS_PIEGES if details.get(c)), None)
        if violation is not None:
            # Action hors périmètre : on décrit le droit manquant, jamais de texte piégé.
            detail = (
                f"action hors périmètre : {violation.get('outil')} exige le droit "
                f"{violation.get('scope_requis')}, absent du jeton de tâche"
            )
        elif details.get("outil_mcp_suspect"):
            detail = (
                f"outil MCP {ev.get('outil')} (serveur {details.get('serveur_mcp')}) : "
                "description porteuse d'une consigne cachée (tool poisoning)"
            )
        elif texte_source is None:
            morceaux = [ev.get("type")]
            if ev.get("methode") or ev.get("chemin"):
                morceaux.append(f"{ev.get('methode') or ''} {ev.get('chemin') or ''}".strip())
            if ev.get("outil"):
                morceaux.append(f"outil={ev.get('outil')}")
            if ev.get("leurre_id"):
                morceaux.append(f"leurre={ev.get('leurre_id')}")
            detail = " · ".join(m for m in morceaux if m)
        else:
            detail = securite.extrait(texte_source)
        leurre_id = ev.get("leurre_id")
        canari_id = leurre_id if (leurre_id and str(leurre_id).startswith("C-")) else None
        etapes.append(
            {
                "etape": etape,
                "phase": _PHASE.get(etape, etape),
                "libelle": _LIBELLES[etape],
                "titre": _LIBELLES[etape],
                "horodatage": ev.get("horodatage"),
                "evenement_id": ev.get("id"),
                "resume": detail,
                "detail": detail,
                "leurre_id": leurre_id,
                "canari_id": canari_id,
                "techniques": _techniques(leurre),
                "risques": _risques(leurre),
            }
        )
    etapes.sort(key=lambda s: (ORDRE_ETAPES.index(s["etape"]) if s["etape"] in ORDRE_ETAPES else 99, s["horodatage"] or ""))
    for i, e in enumerate(etapes):
        e["ordre"] = i
    return etapes


def chaine_complete(etapes: list[dict]) -> bool:
    """Vrai si la chaîne couvre l'appât jusqu'à la tentative de sortie."""
    vues = {e["etape"] for e in etapes}
    return "appat" in vues and "tentative_sortie" in vues
