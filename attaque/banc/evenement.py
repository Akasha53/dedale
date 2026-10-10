"""Schéma d'événement (contrat Dédale) et étiquettes de vérité terrain.

Un événement suit exactement le corps JSON de `POST /api/evenements` décrit dans
CONTRATS.md. La vérité terrain voyage par deux canaux redondants :

- le préfixe du `session_id` : ``banc-<verite>-NNNN`` ;
- ``details.verite_terrain`` : l'une des valeurs de ``VERITES``.

Le backend groupe ses mesures sur cette vérité (voir la note au bas de
CONTRATS.md). Les deux canaux disent la même chose ; le préfixe suffit même si
``details`` n'est pas propagé par la surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Les quatre vérités terrain produites par le banc.
HUMAIN = "humain"
SCRIPT = "script"
AGENT_IA = "agent_ia"
AGENT_INTERNE = "agent_interne"
VERITES = (HUMAIN, SCRIPT, AGENT_IA, AGENT_INTERNE)

# Classement attendu côté backend pour chaque vérité. Sert à la vérification de
# cohérence : une session « humain » classée agent_ia est un faux positif.
CLASSEMENT_ATTENDU = {
    HUMAIN: "humain",
    SCRIPT: "script",
    AGENT_IA: "agent_ia",
    AGENT_INTERNE: "agent_ia",  # l'agent interne détourné est bien un agent IA
}

# Préfixe de session court et lisible (l'agent interne garde « interne »).
_PREFIXE = {
    HUMAIN: "banc-humain",
    SCRIPT: "banc-script",
    AGENT_IA: "banc-agentia",
    AGENT_INTERNE: "banc-interne",
}


def nom_session(verite: str, numero: int) -> str:
    """Identifiant de session stable et étiqueté, ex. ``banc-humain-0001``."""
    if verite not in VERITES:
        raise ValueError(f"vérité terrain inconnue : {verite!r}")
    return f"{_PREFIXE[verite]}-{numero:04d}"


def verite_depuis_session(session_id: str) -> str | None:
    """Retrouve la vérité terrain à partir du préfixe de session."""
    for verite, prefixe in _PREFIXE.items():
        if session_id.startswith(prefixe + "-"):
            return verite
    return None


def horodatage(moment: datetime | None = None) -> str:
    """ISO 8601 avec fuseau local, ex. ``2026-10-10T14:03:22.481+02:00``."""
    instant = moment or datetime.now().astimezone()
    if instant.tzinfo is None:
        instant = instant.astimezone()
    return instant.isoformat(timespec="milliseconds")


def evenement(
    *,
    source: str,
    surface: str,
    type: str,
    session_id: str,
    verite_terrain: str,
    leurre_id: str | None = None,
    ip: str | None = "127.0.0.1",
    user_agent: str | None = None,
    methode: str | None = None,
    chemin: str | None = None,
    outil: str | None = None,
    details: dict[str, Any] | None = None,
    moment: datetime | None = None,
) -> dict[str, Any]:
    """Construit un événement conforme au contrat, étiqueté de sa vérité terrain.

    ``verite_terrain`` est recopiée dans ``details`` et doit correspondre au
    préfixe de ``session_id`` : on le vérifie pour éviter un étiquetage incohérent
    (une erreur de banc fausserait les mesures du backend sans alerte).
    """
    if verite_terrain not in VERITES:
        raise ValueError(f"vérité terrain inconnue : {verite_terrain!r}")
    attendu = verite_depuis_session(session_id)
    if attendu is not None and attendu != verite_terrain:
        raise ValueError(
            f"session {session_id!r} étiquetée {verite_terrain!r} alors que son "
            f"préfixe dit {attendu!r}"
        )
    corps = dict(details or {})
    corps["verite_terrain"] = verite_terrain
    corps["classement_attendu"] = CLASSEMENT_ATTENDU[verite_terrain]
    return {
        "horodatage": horodatage(moment),
        "source": source,
        "surface": surface,
        "type": type,
        "session_id": session_id,
        "leurre_id": leurre_id,
        "ip": ip,
        "user_agent": user_agent,
        "methode": methode,
        "chemin": chemin,
        "outil": outil,
        "details": corps,
    }
