"""Backend simulé minimal, pour la démo hors-ligne et les tests.

Il n'implémente QUE les routes dont le module interne a besoin :
  POST /api/leurres, POST /api/evenements, GET /api/sessions/{id},
  GET /api/incidents et POST /api/incidents/{id}/decision (journal des décisions).
Les droits retirés par l'analyste se posent par `retirer_droit(agent, code)` et reviennent,
comme sur le vrai backend, dans `session.droits_retires` et `droits.retires`.

Le vrai backend (agent A, port 8700) est la source de vérité en démo réelle ; ce stub
permet de jouer la chaîne complète, décision d'analyste comprise, sans dépendre de lui.
L'état d'une session (active / coupee / suspendue) est pilotable, pour simuler l'analyste.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

# Décision analyste -> état de session (même table que le vrai backend).
_ETAT_APRES = {"couper": "coupee", "valider_riposte": "coupee", "reprendre": "active",
               "ignorer": "active"}


def _ouvre_incident(ev: dict) -> bool:
    """Même règle que le backend pour une session interne : canari touché, droits dépassés,
    délégation non authentifiée ou consigne désarmée avant lecture."""
    details = ev.get("details") or {}
    desarme = details.get("desarmement") if isinstance(details.get("desarmement"), dict) else {}
    return (ev.get("type") == "leurre_touche" or isinstance(details.get("violation_droits"), dict)
            or isinstance(details.get("provenance_invalide"), dict)
            or (ev.get("type") == "desarmement" and desarme.get("consigne") is True))


class _Etat:
    def __init__(self, suspendre_a_l_incident: bool = False) -> None:
        self.leurres: list[dict] = []
        self.evenements: list[dict] = []
        self.etats: dict[str, str] = {}  # session_id -> "active" | "coupee" | "suspendue"
        self.incidents: dict[str, dict] = {}  # session_id -> incident minimal
        # Fidèle au vrai backend : l'ouverture d'un incident suspend la session. Désactivé par
        # défaut pour les tests historiques, qui fixent l'état à la main.
        self.suspendre_a_l_incident = suspendre_a_l_incident
        # Correctif en un clic : droits retirés par agent fictif, comme le vrai backend.
        self.agents: dict[str, str] = {}  # session_id -> agent annoncé (details.agent)
        self.droits_retires: dict[str, list[str]] = {}  # agent -> codes retirés
        self.verrou = threading.Lock()

    def noter_evenement(self, ev: dict) -> None:
        with self.verrou:
            self.evenements.append(ev)
            sid = ev.get("session_id", "")
            agent = (ev.get("details") or {}).get("agent")
            if sid and isinstance(agent, str) and sid not in self.agents:
                self.agents[sid] = agent
            if sid and sid not in self.incidents and _ouvre_incident(ev):
                self.incidents[sid] = {
                    "id": f"INC-S{len(self.incidents) + 1:04d}", "session_id": sid,
                    "ouvert_le": datetime.now(timezone.utc).isoformat(), "decisions": [],
                }
                if self.suspendre_a_l_incident and self.etats.get(sid, "active") == "active":
                    self.etats[sid] = "suspendue"

    def decider(self, iid: str, action: str, analyste: str) -> dict | None:
        with self.verrou:
            inc = next((i for i in self.incidents.values() if i["id"] == iid), None)
            if inc is None or action not in _ETAT_APRES:
                return None
            inc["decisions"].append({"action": action, "analyste": analyste,
                                     "horodatage": datetime.now(timezone.utc).isoformat()})
            self.etats[inc["session_id"]] = _ETAT_APRES[action]
            return dict(inc)

    def incident_publie(self, inc: dict) -> dict:
        sid = inc["session_id"]
        return {**inc, "decisions": list(inc["decisions"]), "etat": self.etats.get(sid, "active")}

    def retires(self, sid: str) -> list[str]:
        with self.verrou:
            return list(self.droits_retires.get(self.agents.get(sid, f"orbis-{sid}"), []))

    def retirer_droit(self, agent: str, code: str) -> None:
        with self.verrou:
            liste = self.droits_retires.setdefault(agent, [])
            if code not in liste:
                liste.append(code)

    def etat_session(self, sid: str) -> str:
        with self.verrou:
            return self.etats.get(sid, "active")

    def fixer_etat(self, sid: str, etat: str) -> None:
        with self.verrou:
            self.etats[sid] = etat


def _fabriquer_handler(etat: _Etat):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _repondre(self, code: int, corps: dict):
            donnees = json.dumps(corps).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def do_POST(self):
            longueur = int(self.headers.get("Content-Length", 0))
            brut = self.rfile.read(longueur) if longueur else b""
            corps = json.loads(brut) if brut else {}
            if self.path == "/api/leurres":
                with etat.verrou:
                    etat.leurres.extend(corps if isinstance(corps, list) else [corps])
                self._repondre(200, {"ok": True, "total": len(etat.leurres)})
            elif self.path == "/api/evenements":
                etat.noter_evenement(corps)
                sid = corps.get("session_id", "")
                session = {"id": sid, "classement": "agent_ia", "score": 0.9,
                           "etat": etat.etat_session(sid)}
                if etat.retires(sid):
                    session["droits_retires"] = etat.retires(sid)
                self._repondre(200, {"session": session, "consigne": "aucune"})
            elif self.path.startswith("/api/incidents/") and self.path.endswith("/decision"):
                iid = unquote(self.path.split("/")[3])
                inc = etat.decider(iid, corps.get("action", ""), corps.get("analyste", "inconnu"))
                if inc is None:
                    self._repondre(404, {"erreur": "incident ou action inconnus"})
                else:
                    self._repondre(200, {"incident": etat.incident_publie(inc)})
            else:
                self._repondre(404, {"erreur": "route inconnue"})

        def do_GET(self):
            chemin = urlsplit(self.path).path
            if chemin.startswith("/api/sessions/"):
                sid = unquote(chemin.rsplit("/", 1)[-1])
                detail = {"id": sid, "etat": etat.etat_session(sid),
                          "evenements": [e for e in etat.evenements if e.get("session_id") == sid]}
                if etat.retires(sid):
                    detail["droits"] = {"retires": [{"code": c} for c in etat.retires(sid)]}
                self._repondre(200, detail)
            elif chemin == "/api/incidents":
                with etat.verrou:
                    liste = [etat.incident_publie(i) for i in etat.incidents.values()]
                self._repondre(200, {"incidents": liste})
            else:
                self._repondre(404, {"erreur": "route inconnue"})

    return Handler


class BackendSimule:
    """Serveur HTTP de test. Usage : `with BackendSimule() as b: ... b.base`."""

    def __init__(self, hote: str = "127.0.0.1", port: int = 0, *, suspendre_a_l_incident: bool = False):
        self.etat = _Etat(suspendre_a_l_incident=suspendre_a_l_incident)
        self._serveur = ThreadingHTTPServer((hote, port), _fabriquer_handler(self.etat))
        self._fil: threading.Thread | None = None

    @property
    def base(self) -> str:
        hote, port = self._serveur.server_address[:2]
        return f"http://{hote}:{port}"

    def demarrer(self) -> "BackendSimule":
        self._fil = threading.Thread(target=self._serveur.serve_forever, daemon=True)
        self._fil.start()
        return self

    def arreter(self) -> None:
        self._serveur.shutdown()
        self._serveur.server_close()

    def fixer_etat(self, sid: str, etat: str) -> None:
        self.etat.fixer_etat(sid, etat)

    def retirer_droit(self, agent: str, code: str) -> None:
        """Simule POST /api/incidents/{id}/retirer-droit pour un agent fictif."""
        self.etat.retirer_droit(agent, code)

    def evenements(self, type: str | None = None) -> list[dict]:
        evs = list(self.etat.evenements)
        return [e for e in evs if e.get("type") == type] if type else evs

    def leurres(self) -> list[dict]:
        return list(self.etat.leurres)

    def incidents(self) -> list[dict]:
        with self.etat.verrou:
            return [self.etat.incident_publie(i) for i in self.etat.incidents.values()]

    def __enter__(self) -> "BackendSimule":
        return self.demarrer()

    def __exit__(self, *a) -> None:
        self.arreter()
