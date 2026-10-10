"""Transfert syslog vers le SIEM du SOC : `DEDALE_SYSLOG=udp://hôte:port` ou `tcp://hôte:port`.

Chaque changement d'un incident (ouverture, gravité qui monte, décision, relecture) part en une
ligne CEF dans une trame RFC 5424 (`cef.trame_syslog`). En TCP, la trame est préfixée par sa
longueur (RFC 6587, « octet counting »), comme l'attendent rsyslog, syslog-ng et la plupart des
collecteurs. Sans variable, rien ne sort de la machine et le transfert est noté `non_configure`.

L'envoi passe dans un fil à part, avec un délai de 2 s : il ne ralentit jamais l'ingestion et
une erreur réseau ne remonte jamais à l'appelant. Pas de TLS ici : en production, passer par
un relais local (rsyslog avec `omfwd` en TLS) ou ajouter `tls://` (voir docs/INTEGRATIONS.md).

Démo : `cd backend && uv run python -m app.recepteur_siem` écoute en local et affiche chaque
ligne reçue.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlsplit

_journal = logging.getLogger(__name__)
_TAILLE_MAX_UDP = 8192
historique: deque = deque(maxlen=100)
_verrou = threading.Lock()


def configuration() -> dict | None:
    """`{"protocole", "hote", "port"}` lu dans `DEDALE_SYSLOG` à chaque envoi, ou None."""
    brut = os.environ.get("DEDALE_SYSLOG", "").strip()
    if not brut:
        return None
    try:
        morceaux = urlsplit(brut)
        protocole = morceaux.scheme.lower()
        hote, port = morceaux.hostname, morceaux.port
    except ValueError:
        return {"erreur": "DEDALE_SYSLOG illisible : attendu udp://hôte:port ou tcp://hôte:port"}
    if protocole not in ("udp", "tcp") or not hote or not port:
        return {"erreur": "DEDALE_SYSLOG illisible : attendu udp://hôte:port ou tcp://hôte:port"}
    return {"protocole": protocole, "hote": hote, "port": port}


def etat() -> dict:
    conf = configuration()
    if conf is None:
        return {"configure": False, "cible": None, "erreur": None}
    if "erreur" in conf:
        return {"configure": False, "cible": None, "erreur": conf["erreur"]}
    return {"configure": True, "cible": f"{conf['protocole']}://{conf['hote']}:{conf['port']}", "erreur": None}


def _envoyer(conf: dict, trame: str) -> None:
    donnees = trame.encode("utf-8")
    if conf["protocole"] == "udp":
        if len(donnees) > _TAILLE_MAX_UDP:
            donnees = donnees[:_TAILLE_MAX_UDP]
        with socket.socket(socket.AF_INET6 if ":" in conf["hote"] else socket.AF_INET,
                           socket.SOCK_DGRAM) as s:
            s.settimeout(2.0)
            s.sendto(donnees, (conf["hote"], conf["port"]))
        return
    with socket.create_connection((conf["hote"], conf["port"]), timeout=2.0) as s:
        s.sendall(str(len(donnees)).encode() + b" " + donnees)


def _noter(entree: dict) -> None:
    with _verrou:
        historique.appendleft(entree)


def transferer(trame: str, incident_id: str | None = None, motif: str = "incident") -> dict:
    """Envoie une trame (dans le fil courant). Rend l'entrée d'historique, sans lever."""
    entree = {"horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "incident_id": incident_id, "motif": motif, "statut": None, "trame": trame[:2000]}
    conf = configuration()
    if conf is None:
        entree["statut"] = "non_configure"
    elif "erreur" in conf:
        entree["statut"] = "configuration_invalide"
        entree["raison"] = conf["erreur"]
    else:
        try:
            _envoyer(conf, trame)
            entree["statut"] = "envoyee"
        except OSError as exc:
            entree["statut"] = "echec"
            entree["raison"] = type(exc).__name__
            _journal.warning("Syslog : trame %s non transmise (%s)", incident_id, type(exc).__name__)
    _noter(entree)
    return entree


def transferer_en_fond(trame: str, incident_id: str | None = None, motif: str = "incident") -> None:
    """Envoi dans un fil démon : la réponse au module n'attend jamais le réseau."""
    if configuration() is None:
        _noter({"horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "incident_id": incident_id, "motif": motif, "statut": "non_configure",
                "trame": trame[:2000]})
        return
    threading.Thread(target=transferer, args=(trame, incident_id, motif), daemon=True,
                     name="dedale-syslog").start()
