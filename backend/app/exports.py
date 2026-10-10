"""Export d'un incident vers un SIEM : ECS JSON (Elastic) et correspondance Sigma.

ECS (Elastic Common Schema) est le format de champs normalisé d'Elastic ; chaque événement
devient un document ECS. La correspondance Sigma est une règle prête à convertir (sigma-cli)
vers Elastic/Wazuh, calquée sur l'incident réel.

Tout texte d'origine piégée est déjà neutralisé en amont (store/securite).
"""

from __future__ import annotations

import uuid

import yaml

# event.type/category ECS selon le type d'événement Dédale.
_ECS_TYPE = {
    "requete": ("web", ["access"]),
    "appel_outil": ("process", ["start"]),
    "entree_agent": ("web", ["access"]),
    "sortie_agent": ("network", ["connection"]),
    "leurre_touche": ("intrusion_detection", ["info"]),
    "riposte": ("process", ["change"]),
}


def _ecs_un(ev: dict) -> dict:
    cat, types = _ECS_TYPE.get(ev.get("type"), ("web", ["info"]))
    doc = {
        "@timestamp": ev.get("horodatage"),
        "event": {
            "kind": "event",
            "category": [cat],
            "type": types,
            "action": ev.get("type"),
            "module": "dedale",
            "dataset": f"dedale.{ev.get('source')}",
        },
        "dedale": {
            "session_id": ev.get("session_id"),
            "surface": ev.get("surface"),
            "leurre_id": ev.get("leurre_id"),
            "leurre_nature": ev.get("leurre_nature"),
            "outil": ev.get("outil"),
            "details": ev.get("details"),
        },
    }
    if ev.get("ip"):
        doc["source"] = {"ip": ev["ip"]}
    if ev.get("user_agent"):
        doc["user_agent"] = {"original": ev["user_agent"]}
    if ev.get("methode") or ev.get("chemin"):
        doc["url"] = {"path": ev.get("chemin")}
        doc["http"] = {"request": {"method": ev.get("methode")}}
    return doc


def vers_ecs(incident: dict, evenements: list[dict]) -> dict:
    sess = incident.get("session") or {}
    docs = [_ecs_un(e) for e in evenements]
    # Annotation threat sur chaque document (ATLAS/OWASP Agentic).
    for d in docs:
        d["threat"] = {
            "framework": "MITRE ATLAS / OWASP Agentic",
            "tactic": {"name": "LLM prompt injection"},
        }
    return {
        "incident": {
            "id": incident.get("id"),
            "type": incident.get("type"),
            "classement": sess.get("classement"),
            "statut": incident.get("statut"),
        },
        "ecs_version": "8.11",
        "documents": docs,
        "n_documents": len(docs),
    }


def vers_sigma(incident: dict) -> str:
    """Règle Sigma calquée sur l'incident : session + leurres touchés + étapes."""
    sess = incident.get("session") or {}
    leurres = incident.get("leurres_touches", [])
    etapes = [e.get("etape") for e in incident.get("chaine", [])]
    sel: dict = {"dedale.session_id": sess.get("id")}
    if leurres:
        sel["dedale.leurre_id"] = leurres
    regle = {
        "title": f"Dédale — incident {incident.get('id')} ({incident.get('type')})",
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"dedale/{incident.get('id')}")),
        "status": "experimental",
        "description": (
            "Incident Dédale reconstruit : agent IA détourné/attaquant. "
            f"Chaîne observée : {' -> '.join(etapes) if etapes else 'n/d'}."
        ),
        "references": [
            "https://atlas.mitre.org/",
            "https://genai.owasp.org/ (OWASP Agentic Security ASI01-ASI10)",
        ],
        "logsource": {"product": "dedale", "service": incident.get("type")},
        "detection": {
            "selection": sel,
            "condition": "selection",
        },
        "fields": ["dedale.session_id", "dedale.leurre_id", "dedale.surface", "event.action"],
        "falsepositives": ["Session de test du banc d'attaque avec verite_terrain != agent_ia"],
        "level": "high",
        "tags": ["attack.initial_access", "attack.t1566", "owasp.asi01"],
    }
    return yaml.safe_dump(regle, allow_unicode=True, sort_keys=False)
