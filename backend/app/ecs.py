"""Événements Dédale au format ECS 8.x (Elastic Common Schema).

Un document par événement de la session de l'incident. Les champs suivent ECS 8.11 :
`event.kind`, `event.category` et `event.type` prennent seulement les valeurs autorisées par
le schéma (listes `CATEGORIES`, `TYPES`, `KINDS`, `OUTCOMES`, contrôlées par les tests), puis
`source.*`, `destination.*`, `url.*`, `http.*`, `user_agent.*`, `user.*`, `rule.*`,
`threat.*`, `observer.*` et `labels.*`. Ce qui n'a pas d'équivalent ECS reste sous `dedale.*`.

- `event.action` garde le type d'événement Dédale (`avertissement`, `leurre_touche`,
  `appel_outil`…) : les règles de `sigma/` le lisent déjà.
- `event.kind` vaut `alert` pour l'événement qui porte le signal (piège touché, alerte passée
  outre, appel retenu, sortie de données), `event` sinon. Seul un document `alert` porte
  `threat.*` : la technique ATT&CK du type d'incident, ou AML.T0051 (MITRE ATLAS) quand
  l'événement est la consigne cachée qu'un agent a lue.
- `event.outcome` dit si le geste ou l'appel a abouti : `success` quand il est passé,
  `failure` quand Dédale ou la passerelle l'a arrêté, `unknown` sinon.
- `user.*` : un salarié n'apparaît que sous son pseudonyme (`Salarié 7751`, `S-` et 12
  caractères hexadécimaux) ; un agent IA sous son identifiant, `user.roles: ["agent_ia"]`.
  L'identifiant de session d'un salarié, qui peut porter son prénom, sort pseudonymisé.
- Un domaine ou une adresse n'entre dans `url.domain` ou `destination.domain` que s'il passe
  une expression stricte de nom d'hôte : le texte venu d'un leurre reste sous `dedale.details`,
  déjà neutralisé en amont (store, securite).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from . import sigma_regles

ECS_VERSION = "8.11.0"

# Valeurs autorisées par ECS 8.11 (référence « Event categorization fields »).
KINDS = {"alert", "asset", "enrichment", "event", "metric", "state", "pipeline_error", "signal"}
CATEGORIES = {
    "api", "authentication", "configuration", "database", "driver", "email", "file", "host",
    "iam", "intrusion_detection", "library", "malware", "network", "package", "process",
    "registry", "session", "threat", "vulnerability", "web",
}
TYPES = {
    "access", "admin", "allowed", "change", "connection", "creation", "deletion", "denied",
    "end", "error", "group", "indicator", "info", "installation", "protocol", "start", "user",
}
OUTCOMES = {"success", "failure", "unknown"}

# Gravité Dédale → event.severity et event.risk_score (échelle 0-100 d'Elastic Security).
SEVERITE = {"faible": 21, "moyenne": 47, "haute": 73, "critique": 99}

_NATURES_INJECTION = {
    "consigne_cachee", "canari_document", "canari_mail", "outil_mcp_piege", "canari_appel",
    "injection_chatbot", "memoire_empoisonnee",
}
_VERDICTS_ARRET = {"retenu", "refuse", "bloquer", "bloque", "retenue"}

_NOM_HOTE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$"
)
_URL = re.compile(r"^(https?)://([^/\s?#:]+)(?::\d{1,5})?(/[^\s?#]*)?", re.IGNORECASE)
_PREFIXES = ("[leurre, neutralisé]", "[preuve, neutralisée]")


# ---------------------------------------------------------------- Domaines et adresses
def _texte_brut(valeur) -> str:
    t = str(valeur or "").strip()
    for p in _PREFIXES:
        if t.startswith(p):
            t = t[len(p):].strip()
    # Liens et domaines désarmés par le backend : `hxxp://`, `exemple[.]com`.
    return t.replace("[.]", ".").replace("hxxps://", "https://").replace("hxxp://", "http://")


def hote(valeur) -> str | None:
    """Nom d'hôte tiré d'une URL, d'une adresse mail ou d'un nom seul, ou None."""
    t = _texte_brut(valeur).lower()
    if not t or " " in t:
        return None
    m = _URL.match(t)
    if m:
        t = m.group(2)
    elif "@" in t:
        t = t.rsplit("@", 1)[1]
    t = t.strip(".")
    return t if _NOM_HOTE.match(t) else None


def url_ecs(valeur) -> dict | None:
    """`url.*` d'une URL lue dans un champ de l'événement : schéma, domaine, chemin, jamais la
    requête (un `?u=camille` dirait qui a cliqué)."""
    t = _texte_brut(valeur)
    m = _URL.match(t)
    if not m:
        h = hote(t)
        return {"domain": h} if h else None
    domaine = m.group(2).lower()
    if not _NOM_HOTE.match(domaine):
        return None
    chemin = m.group(3) or "/"
    schema = m.group(1).lower()
    return {"original": f"{schema}://{domaine}{chemin}", "scheme": schema, "domain": domaine, "path": chemin}


def _registre(domaine: str) -> str:
    """Domaine enregistré approché (deux derniers labels) : `login.orbispay-verif.example`
    donne `orbispay-verif.example`. Sans liste des suffixes publics, approximation assumée."""
    parts = domaine.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domaine


# ---------------------------------------------------------------- Pseudonymes
def pseudo_session(session_id: str) -> str:
    return "S-" + hashlib.sha256(f"dedale:session:{session_id}".encode()).hexdigest()[:12]


def _utilisateur(incident: dict, ev: dict, est_humain: bool) -> dict | None:
    if est_humain:
        ident = incident.get("identite") or {}
        pseudo = ident.get("pseudonyme")
        if not pseudo:
            return None
        u = {"name": pseudo, "id": "S-" + hashlib.sha256(f"dedale:salarie:{pseudo}".encode()).hexdigest()[:12],
             "roles": ["salarie"]}
        if ident.get("service"):
            u["group"] = {"name": ident["service"]}
        return u
    agent = (ev.get("details") or {}).get("agent")
    if isinstance(agent, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", agent):
        return {"name": agent, "id": agent, "roles": ["agent_ia"]}
    return None


# ---------------------------------------------------------------- Catégorisation
def _arrete(details: dict) -> bool:
    v = str(details.get("verdict") or "").lower()
    return v in _VERDICTS_ARRET or bool(details.get("violation_droits")) or bool(details.get("hors_scope"))


def categoriser(ev: dict) -> tuple[str, list[str], list[str], str]:
    """(kind, category, type, outcome) ECS d'un événement Dédale."""
    t = ev.get("type")
    d = ev.get("details") or {}
    surface = ev.get("surface")
    if t == "requete":
        return "event", ["web"], ["access"], "unknown"
    if t == "leurre_touche":
        return "alert", ["intrusion_detection"], ["info"], "unknown"
    if t == "entree_agent":
        if surface == "mail":
            return "event", ["email"], ["info"], "unknown"
        if surface == "document":
            return "event", ["file"], ["access"], "unknown"
        return "event", ["web"], ["access"], "unknown"
    if t == "appel_outil":
        if _arrete(d) or isinstance(d.get("politique"), dict) or isinstance(d.get("anomalie"), dict):
            arret = _arrete(d)
            return "alert", ["api"], ["denied" if arret else "access"], "failure" if arret else "success"
        return "event", ["api"], ["access"], "success" if d.get("verdict") == "autorise" else "unknown"
    if t == "sortie_agent":
        arret = _arrete(d)
        alerte = arret or bool(d.get("exfiltration"))
        return ("alert" if alerte else "event"), ["network"], ["connection", "denied" if arret else "allowed"], (
            "failure" if arret else "unknown")
    if t == "avertissement":
        choix = d.get("choix")
        if choix == "continuer":
            # Le salarié passe outre : l'alerte du poste devient un incident.
            return "alert", ["intrusion_detection"], ["allowed"], "success"
        if choix == "annuler":
            return "event", ["intrusion_detection"], ["denied"], "failure"
        return "event", ["intrusion_detection"], ["info"], "unknown"
    if t == "signalement":
        return "event", ["email"], ["info"], "unknown"
    if t == "desarmement":
        return "event", ["intrusion_detection"], ["denied"], "success"
    if t == "riposte":
        q = d.get("quatre_yeux")
        if q == "accorde":
            return "event", ["intrusion_detection"], ["allowed"], "success"
        if q in ("refuse", "expire"):
            return "event", ["intrusion_detection"], ["denied"], "failure"
        return "event", ["process"], ["change"], "unknown"
    if t == "relecture":
        dec = d.get("decision")
        typ = {"accorde": "allowed", "refuse": "denied"}.get(dec, "info")
        return "event", ["intrusion_detection"], [typ], "unknown"
    if t == "console":
        return "event", ["configuration"], ["change"], "unknown"
    return "event", ["intrusion_detection"], ["info"], "unknown"


# ---------------------------------------------------------------- Menace
def _threat_attack(type_inc: str, geste: str | None) -> dict | None:
    techniques = sigma_regles.techniques_incident(type_inc, geste)
    if not techniques:
        return None
    return {
        "framework": "MITRE ATT&CK",
        "technique": {
            "id": [t["id"] for t in techniques],
            "name": [t["nom"] for t in techniques],
            "reference": [t["reference"] for t in techniques],
        },
        "tactic": {
            "id": list(dict.fromkeys(t["tactique_id"] for t in techniques)),
            "name": list(dict.fromkeys(t["tactique"] for t in techniques)),
            "reference": list(dict.fromkeys(
                f"https://attack.mitre.org/tactics/{t['tactique_id']}/" for t in techniques)),
        },
    }


_THREAT_INJECTION = {
    "framework": "MITRE ATLAS",
    "technique": {"id": ["AML.T0051"], "name": ["LLM Prompt Injection"],
                  "reference": ["https://atlas.mitre.org/techniques/AML.T0051"]},
    "tactic": {"id": ["AML.TA0005"], "name": ["Execution"],
               "reference": ["https://atlas.mitre.org/tactics/AML.TA0005"]},
}


# ---------------------------------------------------------------- Un document
def _labels(ev: dict) -> dict:
    d = ev.get("details") or {}
    labels = {}
    for cle in ("categorie", "choix", "contexte", "geste", "quatre_yeux", "verdict", "origine"):
        v = d.get(cle)
        if isinstance(v, str) and re.fullmatch(r"[\w .:'-]{1,60}", v):
            labels[cle] = v
    if ev.get("outil") and re.fullmatch(r"[\w.:-]{1,80}", str(ev["outil"])):
        labels["outil"] = ev["outil"]
    if isinstance(d.get("scope_requis"), str) and re.fullmatch(r"[\w.:-]{1,80}", d["scope_requis"]):
        labels["droit_requis"] = d["scope_requis"]
    violation = d.get("violation_droits")
    if isinstance(violation, dict) or d.get("hors_scope"):
        labels["hors_perimetre"] = "oui"
        if isinstance(violation, dict) and isinstance(violation.get("scope_requis"), str):
            labels["droit_requis"] = violation["scope_requis"][:80]
    if isinstance(d.get("provenance_invalide"), dict):
        labels["provenance"] = "non_authentifiee"
    anomalie = d.get("anomalie")
    if isinstance(anomalie, dict) and isinstance(anomalie.get("code"), str):
        labels["anomalie"] = anomalie["code"][:60]
    if d.get("exfiltration") is True:
        labels["exfiltration"] = "oui"
    return labels


def _destination(ev: dict) -> tuple[dict | None, dict | None]:
    """(url, destination) ECS tirés des champs connus de l'événement."""
    d = ev.get("details") or {}
    url = None
    for cle in ("lien", "url", "lien_reel"):
        if d.get(cle):
            url = url_ecs(d[cle])
            if url:
                break
    dest_domaine = None
    for cle in ("cible", "destinataire", "destination", "domaine"):
        v = d.get(cle)
        if isinstance(v, dict):
            v = v.get("domaine") or v.get("adresse")
        h = hote(v) if v else None
        if h:
            dest_domaine = h
            break
    if url is None and dest_domaine and d.get("contexte") == "navigation":
        # Extension et app Mac : `cible` est le nom d'hôte du site ouvert.
        url = {"domain": dest_domaine}
    if url and "domain" in url:
        url["registered_domain"] = _registre(url["domain"])
    destination = None
    if dest_domaine:
        destination = {"domain": dest_domaine, "registered_domain": _registre(dest_domaine)}
    elif url and url.get("domain"):
        destination = {"domain": url["domain"], "registered_domain": url["registered_domain"]}
    return url, destination


def document(ev: dict, incident: dict, injection_ids: set) -> dict:
    """Document ECS d'un événement de la session de l'incident."""
    type_inc = incident.get("type") or ""
    est_humain = type_inc.startswith("humain_") or incident.get("source") in ("humain", "physique")
    d = ev.get("details") or {}
    kind, categorie, types, outcome = categoriser(ev)
    sid = ev.get("session_id") or ""
    doc: dict = {
        "@timestamp": ev.get("horodatage"),
        "ecs": {"version": ECS_VERSION},
        "event": {
            "id": str(ev.get("id")),
            "kind": kind,
            "category": categorie,
            "type": types,
            "action": ev.get("type"),
            "outcome": outcome,
            "module": "dedale",
            "dataset": f"dedale.{ev.get('source')}",
            "provider": f"dedale-{ev.get('surface') or 'inconnu'}",
        },
        "observer": {"vendor": "sAIfe", "product": "sAIfe", "type": "ids"},
        "dedale": {
            "session_id": pseudo_session(sid) if est_humain else sid,
            "surface": ev.get("surface"),
            "leurre_id": ev.get("leurre_id"),
            "leurre_nature": ev.get("leurre_nature"),
            "outil": ev.get("outil"),
            "details": d,
            "incident": {"id": incident.get("id"), "type": type_inc},
        },
    }
    if ev.get("recu_a"):
        doc["event"]["created"] = ev["recu_a"]
    if kind == "alert":
        gravite = incident.get("gravite") or "moyenne"
        doc["event"]["severity"] = SEVERITE.get(gravite, 47)
        doc["event"]["risk_score"] = float(SEVERITE.get(gravite, 47))
        if incident.get("titre"):
            doc["event"]["reason"] = str(incident["titre"])[:300]
    if ev.get("ip"):
        doc["source"] = {"ip": ev["ip"]}
    if ev.get("user_agent"):
        doc["user_agent"] = {"original": str(ev["user_agent"])[:300]}
    if ev.get("methode"):
        doc["http"] = {"request": {"method": str(ev["methode"]).upper()}}
    url, destination = _destination(ev)
    if ev.get("chemin"):
        url = dict(url or {})
        url.setdefault("path", str(ev["chemin"]).split("?", 1)[0][:500])
    if url:
        doc["url"] = url
    if destination:
        doc["destination"] = destination
    user = _utilisateur(incident, ev, est_humain)
    if user:
        doc["user"] = user
    if ev.get("leurre_id"):
        doc["rule"] = {"id": ev["leurre_id"], "name": ev.get("leurre_nature") or "leurre",
                       "ruleset": "dedale-leurres", "category": "piège"}
    pol = d.get("politique")
    if isinstance(pol, dict):
        doc["rule"] = {"id": str(pol.get("id") or "")[:40] or "regle-soc",
                       "name": f"Règle n°{pol.get('numero')} du SOC" if pol.get("numero") else "Règle du SOC",
                       "ruleset": "dedale-regles-soc",
                       "description": str(pol.get("texte") or pol.get("enonce") or "")[:300]}
    labels = _labels(ev)
    if labels:
        doc["labels"] = labels
    if kind == "alert":
        if ev.get("id") in injection_ids and not est_humain and ev.get("leurre_nature") in _NATURES_INJECTION | {None}:
            doc["threat"] = _THREAT_INJECTION
        else:
            menace = _threat_attack(type_inc, d.get("geste") if isinstance(d.get("geste"), str) else None)
            if menace:
                doc["threat"] = menace
    doc["tags"] = ["dedale", "geste_humain" if est_humain else "agent_ia"]
    doc["dedale"]["contexte"] = "geste_humain" if est_humain else "agent_ia"
    doc["dedale"]["incident_type"] = type_inc
    return doc


def vers_ecs(incident: dict, evenements: list[dict]) -> dict:
    """Enveloppe d'export : l'incident, la version ECS et un document par événement."""
    sess = incident.get("session") or {}
    injection_ids = {
        e.get("evenement_id") for e in incident.get("chaine", [])
        if e.get("etape") == "consigne_lue"
    }
    docs = [document(e, incident, injection_ids) for e in evenements]
    return {
        "incident": {
            "id": incident.get("id"),
            "type": incident.get("type"),
            "classement": sess.get("classement") or incident.get("classement"),
            "statut": incident.get("statut"),
            "gravite": incident.get("gravite"),
        },
        "ecs_version": ECS_VERSION,
        "documents": docs,
        "n_documents": len(docs),
    }


def horodatage_ms(iso: str | None) -> int | None:
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None
