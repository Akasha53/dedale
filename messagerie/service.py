"""Service de verdicts du garde-mail (FastAPI, 127.0.0.1:8715).

Il relève la boîte de démo Mailpit chaque seconde, analyse chaque nouveau mail et garde les
verdicts en mémoire. L'app Mac et la console les lisent par `GET /verdicts`, ou les reçoivent
en direct par `GET /flux` (SSE) ou `WS /ws`. Un mail frauduleux part aussi au backend Dédale
(`POST /api/evenements`, surface `poste`, catégorie `phishing`, contexte « mail reçu »).

Le service ne tombe jamais si Mailpit ou le backend sont absents : il réessaie plus tard.

    uv run uvicorn service:app --host 127.0.0.1 --port 8715
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import analyse
from boite import Boite, BoiteIndisponible

journal = logging.getLogger("messagerie")

BACKEND = os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700").rstrip("/")
INTERVALLE = float(os.environ.get("MESSAGERIE_INTERVALLE", "1.0"))
SIGNALER = os.environ.get("MESSAGERIE_SIGNALER", "1") != "0"
MAX_MAILS = 500
ATTENTE_BACKEND_S = 10.0


def _maintenant() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _heure_locale(valeur: str | None) -> str | None:
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(valeur.replace("Z", "+00:00")).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return None


def _sans_balises(texte: str, limite: int = 400) -> str:
    return analyse.citer(texte, limite).replace("<", "‹").replace(">", "›")


# --- Backend Dédale ---------------------------------------------------------------------

class Backend:
    """Client du backend Dédale. Chaque appel avale l'erreur et renvoie None."""

    def __init__(self, base: str = BACKEND, actif: bool = SIGNALER, timeout: float = 1.5):
        self.base = base.rstrip("/")
        self.actif = actif
        self.timeout = timeout

    def session_existe(self, session_id: str) -> bool | None:
        chemin = "/api/sessions/" + urllib.parse.quote(session_id, safe="")
        try:
            with urllib.request.urlopen(self.base + chemin, timeout=self.timeout):
                return True
        except urllib.error.HTTPError as e:
            return False if e.code == 404 else None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def poster(self, corps: dict) -> dict | None:
        req = urllib.request.Request(
            self.base + "/api/evenements", data=json.dumps(corps).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                brut = rep.read().decode("utf-8")
                return json.loads(brut) if brut else {}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None


def evenement_phishing(verdict: dict, mail: analyse.MailLu) -> dict:
    """Événement envoyé au backend pour un mail frauduleux (voir CONTRATS.md, garde-mail)."""
    lien = next((l.destination for l in mail.liens
                 if analyse.hote_de(l.destination) in {s["preuve"] for s in verdict["signaux"]}), None)
    caches = [c.texte for c in mail.caches]
    balises = next((s["preuve"] for s in verdict["signaux"]
                    if s["code"] == "instruction_cachee" and not caches), None)
    segments = [{"texte": mail.lisible, "piege": False}]
    segments += [{"texte": t, "piege": True} for t in caches]
    if balises:
        segments.append({"texte": balises, "piege": True})
    raisons = [_sans_balises(r) for r in verdict["raisons"]]
    details = {
        "categorie": "phishing",
        "contexte": "mail reçu",
        "gravite": "haute",
        "verdict": verdict["verdict"],
        "score": verdict["score"],
        "raisons": raisons,
        "signaux": [s["code"] for s in verdict["signaux"]],
        "message": " ".join(raisons),
        "cible": verdict["de"]["adresse"],
        "mail_id": verdict["id"],
        "objet": _sans_balises(verdict["objet"], 160),
        "document_source": {
            "type": "mail", "id": verdict["id"], "titre": verdict["objet"],
            "expediteur": verdict["de"]["adresse"], "destinataire": ", ".join(verdict["a"]),
            "date": verdict["recu_a"], "origine": "externe", "segments": segments,
        },
    }
    if lien:
        details["lien"] = analyse.desarmer(lien, 300)
    if caches or balises:
        details["extrait"] = (caches[0] if caches else balises)
    return {
        "horodatage": _maintenant(),
        "source": "humain",
        "surface": "poste",
        "type": "avertissement",
        "session_id": f"mail-{verdict['id']}",
        "leurre_id": None,
        "ip": None,
        "user_agent": "dedale-messagerie/0.1",
        "methode": None,
        "chemin": None,
        "outil": None,
        "details": details,
    }


# --- Relève et mémoire des verdicts -----------------------------------------------------

class Service:
    def __init__(self, boite: Boite | None = None, backend: Backend | None = None,
                 intervalle: float = INTERVALLE):
        self.boite = boite or Boite()
        self.backend = backend or Backend()
        self.intervalle = intervalle
        self.verdicts: OrderedDict[str, dict] = OrderedDict()   # du plus ancien au plus récent
        self.mails: dict[str, analyse.MailLu] = {}
        self.a_signaler: list[str] = []
        self.verrou = threading.Lock()
        self.boite_ok: bool | None = None
        self.erreur_boite: str | None = None
        self.erreur_backend: str | None = None
        self._prochain_essai = 0.0

    def _enregistrer(self, identifiant: str, brut: bytes, recu_a: str | None) -> dict:
        mail = analyse.lire(brut)
        verdict = analyse.analyser(mail, id=identifiant, recu_a=_heure_locale(recu_a))
        verdict["signalement"] = None
        if verdict["verdict"] == "frauduleux":
            verdict["signalement"] = {
                "session_id": f"mail-{identifiant}",
                "statut": "en_attente" if self.backend.actif else "desactive",
            }
        with self.verrou:
            self.verdicts[identifiant] = verdict
            self.mails[identifiant] = mail
            if verdict["verdict"] == "frauduleux" and self.backend.actif:
                self.a_signaler.append(identifiant)
            while len(self.verdicts) > MAX_MAILS:
                ancien, _ = self.verdicts.popitem(last=False)
                self.mails.pop(ancien, None)
        return verdict

    def relever(self) -> list[dict]:
        """Analyse les mails arrivés depuis la dernière relève. Renvoie leurs verdicts."""
        try:
            resumes = self.boite.lister(MAX_MAILS)
            self.boite_ok, self.erreur_boite = True, None
        except BoiteIndisponible as e:
            self.boite_ok, self.erreur_boite = False, str(e)
            self.signaler_en_attente()
            return []
        nouveaux: list[dict] = []
        for resume in reversed(resumes):       # Mailpit liste du plus récent au plus ancien
            identifiant = resume.get("ID")
            if not identifiant or identifiant in self.verdicts:
                continue
            try:
                brut = self.boite.brut(identifiant)
            except KeyError:
                continue
            except BoiteIndisponible as e:
                self.boite_ok, self.erreur_boite = False, str(e)
                break
            nouveaux.append(self._enregistrer(identifiant, brut, resume.get("Created")))
        self.signaler_en_attente()
        return nouveaux

    def mail(self, identifiant: str) -> tuple[analyse.MailLu, dict] | None:
        with self.verrou:
            if identifiant in self.verdicts:
                return self.mails[identifiant], self.verdicts[identifiant]
        try:
            brut = self.boite.brut(identifiant)
        except KeyError:
            return None
        verdict = self._enregistrer(identifiant, brut, None)
        return self.mails[identifiant], verdict

    def signaler_en_attente(self) -> None:
        """Envoie au backend les mails frauduleux pas encore signalés. Jamais bloquant longtemps."""
        if not self.backend.actif or not self.a_signaler or time.monotonic() < self._prochain_essai:
            return
        for identifiant in list(self.a_signaler):
            with self.verrou:
                verdict = self.verdicts.get(identifiant)
                mail = self.mails.get(identifiant)
            if verdict is None or mail is None:
                self.a_signaler.remove(identifiant)
                continue
            session_id = f"mail-{identifiant}"
            existe = self.backend.session_existe(session_id)
            if existe is None:
                self._echec_backend()
                return
            if existe:
                statut = "deja_present"
            else:
                if self.backend.poster(evenement_phishing(verdict, mail)) is None:
                    self._echec_backend()
                    return
                statut = "envoye"
            verdict["signalement"] = {"session_id": session_id, "statut": statut, "a": _maintenant()}
            self.a_signaler.remove(identifiant)
            self.erreur_backend = None

    def _echec_backend(self) -> None:
        self.erreur_backend = f"backend injoignable ({self.backend.base}), nouvel essai dans {ATTENTE_BACKEND_S:.0f} s"
        self._prochain_essai = time.monotonic() + ATTENTE_BACKEND_S

    def liste(self, limite: int, verdict: str | None) -> list[dict]:
        with self.verrou:
            tous = list(reversed(self.verdicts.values()))
        if verdict:
            tous = [v for v in tous if v["verdict"] == verdict]
        return tous[:limite]

    def repartition(self) -> dict:
        with self.verrou:
            r = {"sur": 0, "suspect": 0, "frauduleux": 0}
            for v in self.verdicts.values():
                r[v["verdict"]] += 1
        return r


# --- Application ------------------------------------------------------------------------

def creer_app(service: Service | None = None, releve_auto: bool = True) -> FastAPI:
    service = service or Service()
    abonnes: set[asyncio.Queue] = set()

    def diffuser(verdicts: list[dict]) -> None:
        for v in verdicts:
            for q in list(abonnes):
                try:
                    q.put_nowait(v)
                except asyncio.QueueFull:
                    pass

    async def un_cycle() -> list[dict]:
        try:
            nouveaux = await asyncio.to_thread(service.relever)
        except Exception:                       # la relève ne doit jamais arrêter le service
            journal.exception("relève de la boîte en échec")
            return []
        diffuser(nouveaux)
        return nouveaux

    async def boucle() -> None:
        while True:
            await un_cycle()
            await asyncio.sleep(service.intervalle)

    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI):
        tache = asyncio.create_task(boucle()) if releve_auto else None
        try:
            yield
        finally:
            if tache:
                tache.cancel()
                try:
                    await tache
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="Dédale, garde-mail", version="0.1.0", lifespan=cycle_de_vie)
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/sante")
    def sante() -> dict:
        return {
            "ok": True,
            "boite": {"url": service.boite.base, "joignable": service.boite_ok, "erreur": service.erreur_boite},
            "backend": {"url": service.backend.base, "signalement": service.backend.actif,
                        "en_attente": len(service.a_signaler), "erreur": service.erreur_backend},
            "mails_analyses": len(service.verdicts),
            "repartition": service.repartition(),
        }

    @app.get("/verdicts")
    def verdicts(limite: int = Query(50, ge=1, le=MAX_MAILS),
                 verdict: str | None = Query(None, pattern="^(sur|suspect|frauduleux)$")) -> dict:
        return {"verdicts": service.liste(limite, verdict), "total": len(service.verdicts),
                "repartition": service.repartition()}

    @app.get("/mails")
    def mails(limite: int = Query(50, ge=1, le=MAX_MAILS)) -> dict:
        champs = ("id", "recu_a", "de", "objet", "verdict", "score")
        return {"mails": [{k: v[k] for k in champs} for v in service.liste(limite, None)],
                "total": len(service.verdicts)}

    @app.get("/mails/{identifiant}")
    async def mail(identifiant: str) -> dict:
        try:
            trouve = await asyncio.to_thread(service.mail, identifiant)
        except BoiteIndisponible as e:
            raise HTTPException(status_code=503, detail=f"Boîte de démo injoignable : {e}") from e
        if trouve is None:
            raise HTTPException(status_code=404, detail=f"Mail inconnu : {identifiant}")
        return analyse.detail(*trouve)

    @app.post("/relever")
    async def relever() -> dict:
        nouveaux = await un_cycle()
        return {"nouveaux": len(nouveaux), "verdicts": nouveaux}

    @app.get("/flux")
    async def flux(derniers: int = Query(0, ge=0, le=MAX_MAILS), max: int | None = Query(None, ge=1)):
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        abonnes.add(q)
        precedents = list(reversed(service.liste(derniers, None))) if derniers else []

        async def evenements():
            envoyes = 0
            try:
                yield ": connecté au garde-mail\n\n"
                for v in precedents:
                    yield f"event: verdict\nid: {v['id']}\ndata: {json.dumps(v, ensure_ascii=False)}\n\n"
                    envoyes += 1
                    if max and envoyes >= max:
                        return
                while True:
                    try:
                        v = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"event: verdict\nid: {v['id']}\ndata: {json.dumps(v, ensure_ascii=False)}\n\n"
                    envoyes += 1
                    if max and envoyes >= max:
                        return
            finally:
                abonnes.discard(q)

        return StreamingResponse(evenements(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.websocket("/ws")
    async def ws(socket: WebSocket, derniers: int = 0):
        await socket.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        abonnes.add(q)
        try:
            await socket.send_json({"type": "bonjour", "donnees": {
                "mails_analyses": len(service.verdicts), "repartition": service.repartition()}})
            for v in reversed(service.liste(max(0, min(derniers, MAX_MAILS)), None)) if derniers else []:
                await socket.send_json({"type": "verdict", "donnees": v})
            while True:
                v = await q.get()
                await socket.send_json({"type": "verdict", "donnees": v})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            abonnes.discard(q)

    return app


app = creer_app()
