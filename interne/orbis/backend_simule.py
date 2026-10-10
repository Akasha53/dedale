"""Backend simulé minimal, pour la démo hors-ligne et les tests.

Il n'implémente QUE les trois routes dont le module interne a besoin :
  POST /api/leurres, POST /api/evenements, GET /api/sessions/{id}.

Le vrai backend (agent A, port 8700) est la source de vérité en démo réelle ; ce stub
permet de jouer la chaîne complète, décision d'analyste comprise, sans dépendre de lui.
L'état d'une session (active / coupee / suspendue) est pilotable, pour simuler l'analyste.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Etat:
    def __init__(self) -> None:
        self.leurres: list[dict] = []
        self.evenements: list[dict] = []
        self.etats: dict[str, str] = {}  # session_id -> "active" | "coupee" | "suspendue"
        self.verrou = threading.Lock()

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
                with etat.verrou:
                    etat.evenements.append(corps)
                sid = corps.get("session_id", "")
                self._repondre(
                    200,
                    {
                        "session": {"id": sid, "classement": "agent_ia", "score": 0.9,
                                    "etat": etat.etat_session(sid)},
                        "consigne": "aucune",
                    },
                )
            else:
                self._repondre(404, {"erreur": "route inconnue"})

        def do_GET(self):
            if self.path.startswith("/api/sessions/"):
                sid = self.path.rsplit("/", 1)[-1]
                self._repondre(
                    200,
                    {"id": sid, "etat": etat.etat_session(sid),
                     "evenements": [e for e in etat.evenements if e.get("session_id") == sid]},
                )
            else:
                self._repondre(404, {"erreur": "route inconnue"})

    return Handler


class BackendSimule:
    """Serveur HTTP de test. Usage : `with BackendSimule() as b: ... b.base`."""

    def __init__(self, hote: str = "127.0.0.1", port: int = 0):
        self.etat = _Etat()
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

    def evenements(self, type: str | None = None) -> list[dict]:
        evs = list(self.etat.evenements)
        return [e for e in evs if e.get("type") == type] if type else evs

    def leurres(self) -> list[dict]:
        return list(self.etat.leurres)

    def __enter__(self) -> "BackendSimule":
        return self.demarrer()

    def __exit__(self, *a) -> None:
        self.arreter()
