"""Agents IA configurés sur les postes des salariés, envoyés par l'app Mac (`app-mac/`).

L'app lit les fichiers de configuration MCP des assistants connus (Claude Desktop, Cursor,
VS Code, Windsurf…) et envoie, pour chaque serveur, son nom, ses types (fichiers, shell,
mail, navigateur, réseau) et ses droits risqués (shell, mail, tout le disque). Jamais les
jetons, les clés, les variables d'environnement ni les arguments.

Le backend ne garde que ces champs, bornés et échappés : une clé en trop est ignorée, un nom
à l'allure de secret est masqué. Chaque envoi remplace l'inventaire précédent du même poste.
Les inventaires vivent dans un fichier JSON à côté de la base SQLite, écrit de façon atomique,
et apparaissent dans `GET /api/agents` (champ `inventaire`, `contexte: "poste"`).
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from . import config, inventaire

routeur = APIRouter()

TYPES = ("fichiers", "shell", "mail", "navigateur", "reseau", "autre")
DROITS = ("shell", "mail", "disque_entier")
TRANSPORTS = ("local", "distant")
SOURCES = ("demo", "reel")
MAX_AGENTS = 200

_POSTE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_CLIENT_ID = re.compile(r"^[a-z0-9_]{1,40}$")

LIBELLES_DROITS = {
    "shell": "Lancer des commandes sur le poste (shell)",
    "mail": "Lire ou envoyer des mails",
    "disque_entier": "Lire tout le disque",
}
LIBELLES_TYPES = {
    "fichiers": "fichiers", "shell": "shell", "mail": "mail", "navigateur": "navigateur",
    "reseau": "réseau", "autre": "autre",
}
# Points de risque par droit, sur la même échelle que l'inventaire d'Orbis (moyen ≥ 4, élevé ≥ 8).
POINTS = {"shell": 4, "disque_entier": 4, "mail": 3}

# Garde-fou côté backend, en plus du filtre de l'app : un nom à l'allure de jeton est masqué.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_|xox[abprs]-|AKIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{20,}|glpat-|eyJ[A-Za-z0-9_-]{8,}\.|-----BEGIN|bearer\s|"
    r"(token|secret|passw|api[_-]?key|jeton)\s*[=:])",
    re.IGNORECASE,
)


def _court(texte: object, limite: int) -> str:
    t = re.sub(r"[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]", " ", str(texte or ""))
    t = " ".join(t.split())
    if len(t) > limite:
        t = t[: limite - 1].rstrip() + "…"
    return html.escape(t, quote=False)


def _aleatoire(t: str) -> bool:
    """Longue chaîne sans espace qui mêle lettres et chiffres variés : l'allure d'une clé."""
    if len(t) < 24 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", t):
        return False
    if not (re.search(r"\d", t) and re.search(r"[A-Za-z]", t)):
        return False
    return len(set(t)) >= 14


def nom_sur(brut: object) -> str:
    t = _court(brut, 64)
    if not t:
        return "(sans nom)"
    if _SECRET.search(t) or _aleatoire(t):
        return "nom masqué"
    return t


def chemin_fichier() -> Path:
    db = Path(config.CHEMIN_DB)
    return db.with_name(db.stem + "-agents-poste.json")


def _agent_propre(a: Any) -> dict:
    if not isinstance(a, dict):
        raise ValueError("Chaque agent est un objet.")
    types = [t for t in dict.fromkeys(a.get("types") or []) if t in TYPES] or ["autre"]
    droits = [d for d in dict.fromkeys(a.get("droits_risques") or []) if d in DROITS]
    client_id = str(a.get("client_id") or "")
    return {
        "client": _court(a.get("client"), 40) or "client inconnu",
        "client_id": client_id if _CLIENT_ID.match(client_id) else "inconnu",
        "serveur": nom_sur(a.get("serveur")),
        "types": types,
        "droits_risques": droits,
        "transport": a.get("transport") if a.get("transport") in TRANSPORTS else "local",
    }


class Registre:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._chemin: Path | None = None
        self.postes: dict[str, dict] = {}

    def _assurer(self) -> None:
        chemin = chemin_fichier()
        if chemin == self._chemin:
            return
        self._chemin, self.postes = chemin, {}
        if chemin.is_file():
            try:
                self.postes = dict(json.loads(chemin.read_text(encoding="utf-8")).get("postes", {}))
            except (ValueError, OSError):
                self.postes = {}

    def _ecrire(self) -> None:
        self._chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._chemin.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"postes": self.postes}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self._chemin)

    def vider(self) -> None:
        with self.lock:
            self._chemin, self.postes = None, {}

    def enregistrer(self, corps: dict) -> dict:
        """Valide et range l'inventaire d'un poste. Lève ValueError."""
        if not isinstance(corps, dict):
            raise ValueError("Corps JSON attendu.")
        poste = str(corps.get("poste") or "")
        if not _POSTE.match(poste):
            raise ValueError("Identifiant de poste invalide (1 à 64 caractères : lettres, chiffres, _ . : -).")
        if corps.get("contexte", "poste") != "poste":
            raise ValueError("contexte doit valoir « poste ».")
        agents = corps.get("agents")
        if not isinstance(agents, list) or len(agents) > MAX_AGENTS:
            raise ValueError(f"agents doit être une liste de {MAX_AGENTS} éléments au plus.")
        propres = [_agent_propre(a) for a in agents]
        source = corps.get("source_config") if corps.get("source_config") in SOURCES else "demo"
        horo = corps.get("horodatage")
        try:
            horo = datetime.fromisoformat(str(horo).replace("Z", "+00:00")).isoformat() if horo else None
        except ValueError:
            horo = None
        recu = datetime.now(timezone.utc).isoformat()
        clients = [_court(c, 40) for c in (corps.get("clients") or []) if isinstance(c, str)][:20]
        entree = {
            "poste": poste,
            "source_config": source,
            "horodatage": horo or recu,
            "recu_a": recu,
            "clients": clients,
            "agents": propres,
        }
        with self.lock:
            self._assurer()
            self.postes[poste] = entree
            self._ecrire()
        return resume(entree)

    def lister(self) -> list[dict]:
        with self.lock:
            self._assurer()
            return [resume(p) for p in sorted(self.postes.values(), key=lambda p: p["recu_a"], reverse=True)]


registre = Registre()


def resume(p: dict) -> dict:
    risques = [a for a in p["agents"] if a["droits_risques"]]
    return {
        **p,
        "total": len(p["agents"]),
        "risques": len(risques),
        "phrase": (f"{len(p['agents'])} serveur{'s' if len(p['agents']) > 1 else ''} MCP sur ce poste, "
                   f"dont {len(risques)} avec des droits risqués."),
    }


def _risque(a: dict) -> dict:
    raisons = [{"code": f"droit_{d}", "points": POINTS[d], "texte": LIBELLES_DROITS[d] + ".", "references": [d]}
               for d in a["droits_risques"]]
    if a["transport"] == "distant":
        raisons.append({"code": "serveur_distant", "points": 1,
                        "texte": "Serveur distant : les données passent par un service extérieur.",
                        "references": []})
    score = sum(r["points"] for r in raisons)
    niveau = ("eleve" if score >= inventaire.SEUIL_ELEVE else "moyen" if score >= inventaire.SEUIL_MOYEN
              else "faible")
    mots = {"eleve": "élevé", "moyen": "moyen", "faible": "faible"}
    explication = (f"Risque {mots[niveau]} ({score} points). " + " ".join(r["texte"] for r in raisons)
                   if raisons else "Risque faible : aucun droit risqué.")
    return {"niveau": niveau, "score": score,
            "seuils": {"moyen": inventaire.SEUIL_MOYEN, "eleve": inventaire.SEUIL_ELEVE},
            "raisons": raisons, "explication": explication}


def fiches_inventaire() -> list[dict]:
    """Les serveurs des postes, au format des fiches de `GET /api/agents` (champ `inventaire`)."""
    sortie = []
    for p in registre.lister():
        for a in p["agents"]:
            ident = f"poste:{p['poste']}:{a['client_id']}:{a['serveur']}"
            droits = [{"code": d, "libelle": LIBELLES_DROITS[d]} for d in a["droits_risques"]]
            types = ", ".join(LIBELLES_TYPES[t] for t in a["types"])
            sortie.append({
                "id": ident,
                "contexte": "poste",
                "poste": p["poste"],
                "source_config": p["source_config"],
                "client": a["client"],
                "serveur": a["serveur"],
                "types": a["types"],
                "droits_risques": a["droits_risques"],
                "transport": a["transport"],
                "nom": f"{a['serveur']} ({a['client']})",
                "libelle": f"le serveur {a['serveur']} de {a['client']}",
                "role": f"Serveur MCP configuré dans {a['client']} sur le poste {p['poste']} : {types}.",
                "service": None,
                "declare": False,
                "outils": [],
                "droits": {"accordes": droits, "utilises": [], "necessaires": [], "surplus": [],
                           "inutilises": [], "retires": []},
                "derniere_activite": p["horodatage"],
                "sessions": 0,
                "appels": 0,
                "habitude": None,
                "resistance": None,
                "incidents": {"total": 0, "ouverts": 0, "recents_24h": 0, "ids": []},
                "risque": _risque(a),
            })
    return sortie


@routeur.post("/api/agents/poste", status_code=201)
async def recevoir_inventaire(corps: dict[str, Any]):
    try:
        return registre.enregistrer(corps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@routeur.get("/api/agents/poste")
async def lister_inventaires():
    return {"postes": registre.lister()}
