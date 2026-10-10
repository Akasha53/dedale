"""Authentification des appels au backend : quatre identités, quatre jetons.

- `analyste` : la console du SOC. Lit tout et décide (accorder, refuser, couper, reprendre,
  ignorer, clore, révéler une identité, retirer un droit, activer ou retirer une règle). La
  décision porte le nom de l'analyste envoyé par la console, et seulement si le jeton est bon.
- `passerelle` : la passerelle des agents internes, les leurres, la messagerie et le banc.
  Elle écrit des événements et lit l'état d'une session ; elle ne décide jamais.
- `poste` : l'app du poste du salarié. Elle déclare des gestes et un inventaire, et attend
  le verdict des quatre yeux ; elle ne décide jamais.
- `validateur` : le responsable du salarié ou la finance, dans l'espace `/validation`. Il
  confirme les gestes métier retenus (virement, export). Il ne voit pas la console du SOC, et
  l'analyste ne décide pas d'un geste métier : les routes de cet espace, sous
  `/api/validation/`, déclarent `dependencies=[auth.VALIDATEUR]` et n'admettent que lui.

Les jetons vivent hors du dépôt, dans `~/.config/dedale/` (dossier en 700, fichiers en 600),
ou dans le dossier que nomme `DEDALE_JETONS`. Le backend les tire au premier démarrage ; chaque
client relit le sien dans ce dossier. Ils voyagent dans `Authorization: Bearer <jeton>`.

Refus par défaut : `brancher(app)` pose une dépendance sur l'application entière et un
middleware devant le routeur. Une route qui ne déclare rien n'accepte que le jeton analyste, même
ajoutée plus tard par un autre module. Une route ouverte à une machine le déclare par une
dépendance (`dependencies=[auth.PASSERELLE]`, `auth.ECRIVAINS`…). Le flux `/ws` est réservé à
l'analyste. Seules `GET /api/sante` et les fichiers de la console restent ouverts. Sans jeton
valable : 401. Jeton valable d'une autre identité : 403. Chaque refus est journalisé, sans le
jeton, et compté dans `GET /api/mesures` (`acces_refuses`).

Limite assumée : un jeton par identité, pas un par personne. En production il faudrait un SSO
(OIDC) qui authentifie chaque analyste et des rôles fins ; ici le nom signé est celui que la
console déclare.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import stat
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from starlette.requests import HTTPConnection

ROLES = ("analyste", "passerelle", "poste", "validateur")
# Seules routes de l'API servies sans jeton : (méthode, gabarit de chemin).
OUVERTES = {("GET", "/api/sante"), ("HEAD", "/api/sante"), ("GET", "/")}
_TAILLE_MAX_JETON = 512

_journal = logging.getLogger("dedale.auth")
_verrou = threading.Lock()
_jetons: dict[str, bytes] = {}
_refus = {"401": 0, "403": 0}
_derniers_refus: deque = deque(maxlen=20)


# ------------------------------------------------------------------ jetons sur disque
def dossier() -> Path:
    brut = os.environ.get("DEDALE_JETONS", "").strip()
    return Path(brut).expanduser() if brut else Path.home() / ".config" / "dedale"


def chemin_jeton(role: str) -> Path:
    return dossier() / f"jeton-{role}"


def _creer_si_absent(chemin: Path) -> bool:
    """Tire un jeton neuf si le fichier manque. Écriture atomique : fichier temporaire en 600,
    puis lien dur, qui échoue si un autre processus a gagné la course (on garde alors le sien)."""
    if chemin.exists():
        return False
    temporaire = chemin.with_name(f".{chemin.name}.{os.getpid()}.{secrets.token_hex(4)}")
    fd = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temporaire, chemin)
        except FileExistsError:
            return False
        return True
    finally:
        temporaire.unlink(missing_ok=True)


def _lire_jeton(chemin: Path) -> bytes:
    info = os.lstat(chemin)
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"{chemin} n'est pas un fichier ordinaire : jeton refusé.")
    if info.st_mode & 0o077:
        os.chmod(chemin, 0o600)
        _journal.warning("Droits trop larges sur %s, ramenés à 600", chemin)
    jeton = chemin.read_text(encoding="ascii").strip()
    if len(jeton) < 32 or len(jeton) > _TAILLE_MAX_JETON or any(c.isspace() for c in jeton):
        raise RuntimeError(f"Jeton illisible ou trop court dans {chemin}.")
    return jeton.encode("ascii")


def preparer() -> None:
    """Crée le dossier (700) et les jetons (600) qui manquent, puis les charge. Deux jetons
    identiques ne distingueraient plus deux identités : le backend refuse de démarrer."""
    d = dossier()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(os.stat(d).st_mode) & 0o077:
        os.chmod(d, 0o700)
    crees = [role for role in ROLES if _creer_si_absent(chemin_jeton(role))]
    lus = {role: _lire_jeton(chemin_jeton(role)) for role in ROLES}
    if len(set(lus.values())) != len(ROLES):
        raise RuntimeError(f"Les jetons de {d} doivent être distincts.")
    with _verrou:
        _jetons.clear()
        _jetons.update(lus)
    if crees:
        _journal.warning("Jetons créés dans %s : %s", d, ", ".join(crees))


# ------------------------------------------------------------------ identification
def identifier(autorisation: str | None) -> str | None:
    """Rôle du jeton présenté dans `Authorization: Bearer …`, ou None. Le jeton est comparé à
    chacun en temps constant, sans sortie anticipée : la durée ne dit pas lequel a failli."""
    if not autorisation:
        return None
    schema, _, valeur = autorisation.partition(" ")
    if schema.lower() != "bearer":
        return None
    presente = valeur.strip().encode("utf-8", "replace")
    if not presente or len(presente) > _TAILLE_MAX_JETON:
        return None
    with _verrou:
        attendus = list(_jetons.items())
    trouve = None
    for role, attendu in attendus:
        egal = hmac.compare_digest(presente, attendu)
        if egal and trouve is None:
            trouve = role
    return trouve


def _client(scope: dict) -> str:
    client = scope.get("client")
    return str(client[0]) if client else "inconnu"


def noter_refus(code: int, methode: str, chemin: str, motif: str, role: str | None,
                client: str) -> None:
    """Journal et compteur d'un refus. Jamais le jeton, ni la chaîne de requête."""
    entree = {
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code,
        "methode": methode,
        "chemin": chemin[:200],
        "identite": role,
        "motif": motif,
        "client": client,
    }
    with _verrou:
        _refus[str(code)] = _refus.get(str(code), 0) + 1
        _derniers_refus.appendleft(entree)
    _journal.warning("Accès refusé %d %s %r : %s (identité %s, client %s)",
                     code, methode, chemin[:200], motif, role or "aucune", client)


def bilan() -> dict:
    """Refus comptés depuis le démarrage, pour `GET /api/mesures`."""
    with _verrou:
        return {"refus_401": _refus.get("401", 0), "refus_403": _refus.get("403", 0),
                "derniers": list(_derniers_refus)}


def vider_bilan() -> None:
    with _verrou:
        _refus.update({"401": 0, "403": 0})
        _derniers_refus.clear()


# ------------------------------------------------------------------ dépendances des routes
@dataclass(frozen=True)
class Identite:
    role: str


def exiger(*roles: str) -> Callable[[Request], Identite]:
    """Dépendance FastAPI : la route n'accepte que ces identités."""
    inconnus = set(roles) - set(ROLES)
    if not roles or inconnus:
        raise ValueError(f"Identités inconnues : {sorted(inconnus)}")

    def verifier_jeton(request: Request) -> Identite:
        role = identifier(request.headers.get("authorization"))
        chemin, methode = request.url.path, request.method
        if role is None:
            noter_refus(401, methode, chemin, "jeton absent ou invalide", None, _client(request.scope))
            raise HTTPException(status_code=401, detail="Jeton absent ou invalide.",
                                headers={"WWW-Authenticate": "Bearer"})
        if role not in roles:
            noter_refus(403, methode, chemin, f"réservée à {', '.join(roles)}", role,
                        _client(request.scope))
            raise HTTPException(status_code=403,
                                detail=f"Route réservée à : {', '.join(roles)}.")
        return Identite(role)

    verifier_jeton.roles_dedale = tuple(roles)  # lu par la garde et par les tests
    return verifier_jeton


# Nom demandé par l'espace de validation : même dépendance.
exige_role = exiger


ANALYSTE = Depends(exiger("analyste"))
PASSERELLE = Depends(exiger("passerelle"))
POSTE = Depends(exiger("poste"))
# Écrire un événement : la passerelle (agents, leurres, messagerie, banc) ou le poste.
ECRIVAINS = Depends(exiger("passerelle", "poste"))
# L'état d'une session : la console, et la passerelle qui attend la décision de l'analyste.
LECTURE_SESSION = Depends(exiger("analyste", "passerelle"))
# Le verdict des quatre yeux : la console, et le poste qui l'attend.
VERDICT_POSTE = Depends(exiger("analyste", "poste"))
# Les décisions prises sur une session : la console, la passerelle et le poste qui les attendent.
DECISIONS_SESSION = Depends(exiger("analyste", "passerelle", "poste"))
# Espace /validation : le responsable ou la finance confirme un geste métier retenu. Seul.
VALIDATEUR = Depends(exiger("validateur"))


# ------------------------------------------------------------------ garde par défaut
def _roles_declares(route: Any) -> tuple[str, ...] | None:
    """Identités déclarées par une dépendance `exiger(...)` de la route, ou None."""
    pile = [getattr(route, "dependant", None)]
    while pile:
        dep = pile.pop()
        if dep is None:
            continue
        roles = getattr(dep.call, "roles_dedale", None)
        if roles:
            return tuple(roles)
        pile.extend(dep.dependencies)
    return None


def garde_par_defaut(connexion: HTTPConnection) -> None:
    """Dépendance posée sur l'application entière, avant celles de chaque route : une route qui
    ne déclare pas ses identités n'admet que l'analyste, qu'elle vienne de main.py ou d'un
    routeur ajouté plus tard. Seules les routes de `OUVERTES` passent sans jeton."""
    if connexion.scope.get("type") != "http":
        return  # le flux /ws est gardé par GardeHttp, avant la poignée de main
    route = connexion.scope.get("route")
    gabarit = getattr(route, "path", connexion.url.path)
    methode = connexion.scope.get("method", "GET")
    if (methode, gabarit) in OUVERTES:
        return
    roles = _roles_declares(route) or ("analyste",)
    role = identifier(connexion.headers.get("authorization"))
    if role is None:
        noter_refus(401, methode, connexion.url.path, "jeton absent ou invalide", None,
                    _client(connexion.scope))
        raise HTTPException(status_code=401, detail="Jeton absent ou invalide.",
                            headers={"WWW-Authenticate": "Bearer"})
    if role not in roles:
        noter_refus(403, methode, connexion.url.path, f"réservée à {', '.join(roles)}", role,
                    _client(connexion.scope))
        raise HTTPException(status_code=403, detail=f"Route réservée à : {', '.join(roles)}.")


class GardeHttp:
    """Middleware ASGI, devant le routeur. Il répond 401 à toute requête `/api/` sans jeton
    valable (même au corps mal formé, que FastAPI lirait avant les dépendances), et réserve le
    flux temps réel à l'analyste. Le choix de l'identité par route revient aux dépendances."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        type_ = scope.get("type")
        chemin = scope.get("path", "")
        if type_ == "websocket":
            role = identifier(_entete(scope, "authorization"))
            if role == "analyste":
                await self.app(scope, receive, send)
                return
            code = 401 if role is None else 403
            noter_refus(code, "WS", chemin, "jeton absent ou invalide" if role is None
                        else "réservée à analyste", role, _client(scope))
            # Fermer avant d'accepter : le serveur refuse la poignée de main (HTTP 403).
            await send({"type": "websocket.close", "code": 1008, "reason": "jeton refusé"})
            return
        methode = scope.get("method", "GET")
        if (type_ != "http" or methode == "OPTIONS" or not chemin.startswith("/api/")
                or (methode, chemin) in OUVERTES):
            await self.app(scope, receive, send)
            return
        if identifier(_entete(scope, "authorization")) is not None:
            await self.app(scope, receive, send)
            return
        noter_refus(401, methode, chemin, "jeton absent ou invalide", None, _client(scope))
        corps = json.dumps({"detail": "Jeton absent ou invalide."}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(corps)).encode()),
            (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": corps})


def _entete(scope: dict, nom: str) -> str | None:
    cle = nom.lower().encode("latin-1")
    for k, v in scope.get("headers") or []:
        if k.lower() == cle:
            return v.decode("latin-1")
    return None


# ------------------------------------------------------------------ décisions d'une session
routeur = APIRouter()


@routeur.get("/api/sessions/{session_id}/decisions", dependencies=[DECISIONS_SESSION])
async def decisions_de_session(session_id: str):
    """Ce que la passerelle et le poste ont besoin de lire, et rien de plus : les décisions
    prises sur l'incident d'une session dont ils connaissent l'identifiant (appel retenu,
    quatre yeux), avec le nom de l'analyste qui les signe pour la boîte noire de l'agent.
    Ni la chaîne, ni le salarié, ni les autres incidents."""
    from .store import store

    sid = session_id[:200]
    with store.lock:
        incidents = [i for i in store.incidents.values() if i.session_id == sid]
        ids = {i.id for i in incidents}
        decisions = [d for d in store.decisions if d.get("incident_id") in ids]
    return {"incidents": [
        {"id": i.id, "session_id": i.session_id, "type": i.type, "statut": i.statut,
         "decisions": [{"action": d["action"], "analyste": d.get("analyste"),
                        "horodatage": d["horodatage"]}
                       for d in decisions if d.get("incident_id") == i.id]}
        for i in incidents
    ]}


def brancher(app: FastAPI) -> None:
    """Seule ligne ajoutée à main.py, avant toute route : jetons prêts, garde posée sur
    l'application (elle couvre aussi les routeurs inclus après), décisions d'une session."""
    preparer()
    app.router.dependencies.insert(0, Depends(garde_par_defaut))
    app.add_middleware(GardeHttp)
    app.include_router(routeur)
