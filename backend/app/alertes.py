"""Alerte « décision attendue » vers un webhook Slack ou Teams.

Quand un événement ouvre un incident, le backend prépare un message au format Slack (`text`
et quelques blocs simples) avec le lien vers l'incident dans la console. Le message part vers
`DEDALE_WEBHOOK_URL` si la variable est posée ; sinon rien ne sort de la machine et l'alerte
reste visible dans `GET /api/alertes`. Pour la démo, `uv run python -m app.recepteur_demo`
démarre un faux récepteur local qui affiche chaque message.

L'envoi part en tâche de fond, après la réponse au module : il ne ralentit jamais
l'ingestion et une erreur de webhook ne remonte jamais à l'appelant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from . import synthese
from .rapport import ATTENTE as _ATTENTE
from .store import store

_journal = logging.getLogger(__name__)

# Dernières alertes préparées, de la plus récente à la plus ancienne (sans l'URL du webhook).
historique: deque = deque(maxlen=50)
_taches: set = set()
_envois: deque = deque()

_ETATS = {"active": "active", "suspendue": "suspendue", "coupee": "coupée"}


def url_webhook() -> str | None:
    """URL lue à chaque envoi : la démo peut la poser sans relancer le backend."""
    url = os.environ.get("DEDALE_WEBHOOK_URL", "").strip()
    return url or None


def url_console() -> str:
    return os.environ.get("DEDALE_CONSOLE_URL", "http://127.0.0.1:5173").strip().rstrip("/")


def max_par_minute() -> int:
    try:
        return max(1, int(os.environ.get("DEDALE_ALERTES_MAX_MINUTE", "20")))
    except ValueError:
        return 20


def lien_incident(iid: str) -> str:
    return f"{url_console()}/?incident={quote(iid)}"


def _slack(texte) -> str:
    """Échappement Slack : sans lui, un texte venu d'un leurre pourrait former <!channel>."""
    return str(texte or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _heure(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%d/%m %H:%M:%S")
    except ValueError:
        return str(iso or "")


def construire_message(detail: dict, texte_synthese: str | None = None) -> dict:
    """Message au format Slack (`text` + `blocks`). Teams lit le champ `text`."""
    iid = detail.get("id")
    lien = lien_incident(iid)
    gravite = detail.get("gravite") or "moyenne"
    attente = _ATTENTE.get(detail.get("source"), "Décision de l'analyste attendue.")
    ce_qui_sest_passe = (texte_synthese or detail.get("resume") or "")[:2500]
    texte = f"Décision attendue sur {iid} (gravité {gravite}) : {detail.get('titre')}. {attente} {lien}"
    blocs = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Décision attendue : {iid}"[:150]}},
        {"type": "section", "text": {"type": "mrkdwn",
                                     "text": f"*{_slack(detail.get('titre'))}*\n{_slack(ce_qui_sest_passe)}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Gravité*\n{_slack(gravite)}"},
            {"type": "mrkdwn", "text": f"*Session*\n{_slack(detail.get('session_id'))}"},
            {"type": "mrkdwn", "text": f"*État*\n{_slack(_ETATS.get(detail.get('etat'), detail.get('etat')))}"},
            {"type": "mrkdwn", "text": f"*Ouvert le*\n{_slack(_heure(detail.get('ouvert_le')))}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": _slack(attente)}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Ouvrir l'incident"}, "url": lien},
        ]},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": "sAIfe · Orbis Pay, entreprise fictive · trafic de démonstration"},
        ]},
    ]
    return {"text": texte, "blocks": blocs}


def _quota_atteint() -> bool:
    maintenant = time.monotonic()
    while _envois and maintenant - _envois[0] > 60:
        _envois.popleft()
    if len(_envois) >= max_par_minute():
        return True
    _envois.append(maintenant)
    return False


async def envoyer(iid: str) -> dict | None:
    """Prépare l'alerte de l'incident et la poste si un webhook est configuré."""
    detail = store.incident_detail(iid)
    if detail is None:
        return None
    entree = {"incident_id": iid, "horodatage": datetime.now(timezone.utc).isoformat(),
              "statut": None, "lien": lien_incident(iid), "message": None}
    try:
        sess = store.session_detail(detail["session_id"]) or {}
        try:
            texte = synthese.construire(detail, sess.get("evenements", [])).get("texte")
        except Exception:  # la synthèse aide, elle ne doit pas empêcher l'alerte
            texte = None
        entree["message"] = construire_message(detail, texte)
        url = url_webhook()
        if url is None:
            entree["statut"] = "non_envoyee"
            entree["raison"] = "DEDALE_WEBHOOK_URL absent : aucun envoi"
        elif not url.startswith(("http://", "https://")):
            entree["statut"] = "configuration_invalide"
            entree["raison"] = "DEDALE_WEBHOOK_URL doit commencer par http:// ou https://"
        elif _quota_atteint():
            entree["statut"] = "limitee"
            entree["raison"] = f"plus de {max_par_minute()} alertes dans la minute"
        else:
            async with httpx.AsyncClient(timeout=3.0) as client:
                rep = await client.post(url, json=entree["message"])
            entree["statut"] = "envoyee" if rep.status_code < 300 else "refusee"
            entree["code_http"] = rep.status_code
    except Exception as exc:
        entree["statut"] = "echec"
        entree["raison"] = type(exc).__name__
        _journal.warning("Alerte %s non envoyée : %s", iid, type(exc).__name__)
    historique.appendleft(entree)
    return entree


def planifier(iid: str) -> None:
    """Lance l'envoi en tâche de fond sur la boucle courante ; sans boucle, ne fait rien."""
    try:
        boucle = asyncio.get_running_loop()
    except RuntimeError:
        return
    tache = boucle.create_task(envoyer(iid))
    _taches.add(tache)
    tache.add_done_callback(_taches.discard)


async def attendre(delai: float = 2.0) -> None:
    """À l'arrêt : laisse finir les envois en cours, puis annule ce qui traîne."""
    boucle = asyncio.get_running_loop()
    en_cours = [t for t in _taches if t.get_loop() is boucle and not t.done()]
    if not en_cours:
        return
    _, restantes = await asyncio.wait(en_cours, timeout=delai)
    for t in restantes:
        t.cancel()
