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

from . import auth, config, inventaire

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
    "mail": "Lire et envoyer des mails",
    "disque_entier": "Lire tout le disque",
}
LIBELLES_TYPES = {
    "fichiers": "fichiers", "shell": "shell", "mail": "mail", "navigateur": "navigateur",
    "reseau": "réseau", "autre": "autre",
}
# Points de risque par droit, sur la même échelle que l'inventaire d'Orbis (moyen ≥ 4, élevé ≥ 8).
# Points de risque par facteur, sur l'échelle de l'inventaire d'Orbis (moyen ≥ 4, élevé ≥ 8) :
# chacun suffit à passer « moyen », deux ensemble ou plus mènent à « élevé ». Le shell compte
# double : il lit tout ce que l'utilisateur lit et peut tout envoyer, il est « élevé » à lui seul.
POINTS_FACTEUR = {"shell": 6, "disque_entier": 4, "mail": 4, "navigateur": 4, "distant": 4, "canal": 2}
# Ce qu'un serveur peut lire sur le poste, et ce par quoi il peut le faire sortir.
LECTURES = {"fichiers", "mail", "shell", "navigateur"}
SORTIES = {"mail", "reseau", "navigateur", "shell"}
LIBELLES_LECTURE = {"fichiers": "des fichiers", "mail": "des mails", "shell": "tout ce que le shell atteint",
                    "navigateur": "des pages ouvertes avec les sessions du salarié"}
LIBELLES_SORTIE = {"mail": "des mails", "reseau": "vers le réseau", "navigateur": "par le navigateur",
                   "shell": "par le shell", "distant": "vers son serveur distant"}

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
    """Niveau de risque d'un serveur MCP de poste : une somme de points, chacun nommé.

    Font monter le niveau : l'envoi de mails, le shell, l'accès à tout le disque, le navigateur
    piloté et un serveur distant (l'app n'envoie pas son hôte : il n'est donc jamais vérifié).
    Un serveur qui lit des données et peut les faire sortir (canal de sortie) est au moins
    « moyen », quel que soit son score.
    """
    types, droits = set(a["types"]), set(a["droits_risques"])
    raisons: list[dict] = []

    def ajouter(code: str, points: int, texte: str, references: list[str]) -> None:
        raisons.append({"code": code, "points": points, "texte": texte, "references": references})

    if "mail" in droits:
        ajouter("droit_mail", POINTS_FACTEUR["mail"],
                "Droit « mails » : il lit la boîte et peut envoyer des mails au nom du salarié.", ["mail"])
    if "shell" in droits:
        ajouter("droit_shell", POINTS_FACTEUR["shell"],
                "Droit « shell » : il lance n'importe quelle commande sur le poste.", ["shell"])
    if "disque_entier" in droits:
        ajouter("droit_disque_entier", POINTS_FACTEUR["disque_entier"],
                "Droit « tout le disque » : il lit tous les fichiers du poste, pas un seul dossier.",
                ["disque_entier"])
    if "navigateur" in types:
        ajouter("navigateur_pilote", POINTS_FACTEUR["navigateur"],
                "Navigateur piloté : il ouvre des pages avec les sessions du salarié et peut remplir des formulaires.",
                ["navigateur"])
    if a["transport"] == "distant":
        ajouter("serveur_distant", POINTS_FACTEUR["distant"],
                "Serveur distant non vérifié : ce qu'il reçoit part vers un service extérieur au poste.",
                ["distant"])

    lit = sorted(types & LECTURES)
    sort = sorted((types & SORTIES) | ({"distant"} if a["transport"] == "distant" else set()))
    canal = bool(lit) and bool(sort)
    if canal:
        nom_lit = ", ".join(LIBELLES_LECTURE[t] for t in lit)
        nom_sort = ", ".join(LIBELLES_SORTIE[t] for t in sort)
        ajouter("canal_de_sortie", POINTS_FACTEUR["canal"],
                f"Canal de sortie : le même serveur lit ({nom_lit}) et peut envoyer ({nom_sort}).",
                lit + [s for s in sort if s not in lit])

    score = sum(r["points"] for r in raisons)
    niveau = ("eleve" if score >= inventaire.SEUIL_ELEVE else "moyen" if score >= inventaire.SEUIL_MOYEN
              else "faible")
    if canal and niveau == "faible":
        niveau = "moyen"
    mots = {"eleve": "élevé", "moyen": "moyen", "faible": "faible"}
    if raisons:
        explication = f"Risque {mots[niveau]} ({score} points). " + " ".join(r["texte"] for r in raisons)
        if canal and score < inventaire.SEUIL_MOYEN:
            explication += " Un canal de sortie compte au moins comme un risque moyen."
    else:
        explication = "Risque faible : ni droit à risque, ni canal de sortie."
    return {"niveau": niveau, "score": score,
            "seuils": {"moyen": inventaire.SEUIL_MOYEN, "eleve": inventaire.SEUIL_ELEVE},
            "canal_de_sortie": canal, "raisons": raisons, "explication": explication}


def fiches_inventaire() -> list[dict]:
    """Les serveurs des postes, au format des fiches de `GET /api/agents` (champ `inventaire`)."""
    sortie = []
    for p in registre.lister():
        for a in p["agents"]:
            ident = f"poste:{p['poste']}:{a['client_id']}:{a['serveur']}"
            droits = [{"code": d, "libelle": LIBELLES_DROITS[d]} for d in a["droits_risques"]]
            if "navigateur" in a["types"]:
                droits.append({"code": "navigateur", "libelle": "Piloter un navigateur"})
            if a["transport"] == "distant":
                droits.append({"code": "distant", "libelle": "Envoyer à un serveur distant"})
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


@routeur.post("/api/agents/poste", status_code=201, dependencies=[auth.POSTE])
async def recevoir_inventaire(corps: dict[str, Any]):
    try:
        return registre.enregistrer(corps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@routeur.get("/api/agents/poste")
async def lister_inventaires():
    return {"postes": registre.lister()}
