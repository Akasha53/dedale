"""Sortie CEF (Common Event Format, ArcSight) et trame syslog RFC 5424 pour les SIEM.

Chaque ligne CEF se construit depuis le document ECS du même événement (`ecs.py`) : une seule
correspondance des champs, deux formats. En-tête :

    CEF:0|Dedale|Dedale|<version>|<type d'incident>:<action>|<nom>|<sévérité 0-10>|<extensions>

- En-tête : `\\` et `|` échappés. Extensions : `\\`, `=` échappés, retours à la ligne en `\\n`.
  Le fournisseur et le produit restent en ASCII (« Dedale ») : certains analyseurs CEF lisent mal
  un accent dans l'en-tête. Les extensions sont en UTF-8.
- Clés du dictionnaire CEF : `rt` (horodatage en ms), `src`, `dhost`, `request`,
  `requestMethod`, `requestClientApplication`, `suser` et `suid` (pseudonyme du salarié ou
  identifiant de l'agent), `act`, `outcome`, `cat`, `externalId`, `msg`, et six chaînes nommées :
  `cs1` incident, `cs2` session (pseudonymisée pour un salarié), `cs3` technique, `cs4` règle ou
  piège, `cs5` type d'incident, `cs6` lien vers la console. `cn1` porte le score de risque.
- Sévérité : 3 faible, 5 moyenne, 8 haute, 10 critique pour un document `alert` ; 2 sinon.

`trame_syslog` enveloppe une ligne en RFC 5424 (facilité local4, sévérité syslog tirée de la
gravité), prête pour `transfert_syslog`.
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone

from . import __version__, ecs

SEVERITE_CEF = {"faible": 3, "moyenne": 5, "haute": 8, "critique": 10}
# Sévérité syslog (RFC 5424) : 2 critique, 3 erreur, 4 avertissement, 5 notice, 6 information.
SEVERITE_SYSLOG = {"critique": 2, "haute": 3, "moyenne": 4, "faible": 5}
FACILITE_LOCAL4 = 20
_LIMITE = {"msg": 1023, "request": 1023, "requestClientApplication": 1023, "suser": 1023}


def echapper_entete(valeur) -> str:
    return str(valeur if valeur is not None else "").replace("\\", "\\\\").replace("|", "\\|").replace(
        "\r", " ").replace("\n", " ")


def echapper_extension(valeur) -> str:
    t = str(valeur if valeur is not None else "")
    return (t.replace("\\", "\\\\").replace("=", "\\=").replace("\r\n", "\\n")
            .replace("\n", "\\n").replace("\r", "\\r"))


def _premier(valeur):
    if isinstance(valeur, list):
        return valeur[0] if valeur else None
    return valeur


def ligne(doc: dict, incident: dict, lien: str | None = None) -> str:
    """Ligne CEF d'un document ECS."""
    ev = doc.get("event") or {}
    alerte = ev.get("kind") == "alert"
    gravite = incident.get("gravite") or "moyenne"
    severite = SEVERITE_CEF.get(gravite, 5) if alerte else 2
    type_inc = incident.get("type") or "inconnu"
    signature = f"{type_inc}:{ev.get('action') or 'evenement'}"
    nom = (incident.get("titre") if alerte else None) or f"Événement {ev.get('action') or ''} de Dédale"
    ext: list[tuple[str, object]] = []
    rt = ecs.horodatage_ms(doc.get("@timestamp"))
    if rt is not None:
        ext.append(("rt", rt))
    if (doc.get("source") or {}).get("ip"):
        ext.append(("src", doc["source"]["ip"]))
    dhost = (doc.get("destination") or {}).get("domain") or (doc.get("url") or {}).get("domain")
    if dhost:
        ext.append(("dhost", dhost))
    if (doc.get("url") or {}).get("original"):
        ext.append(("request", doc["url"]["original"]))
    elif (doc.get("url") or {}).get("path"):
        ext.append(("request", doc["url"]["path"]))
    methode = ((doc.get("http") or {}).get("request") or {}).get("method")
    if methode:
        ext.append(("requestMethod", methode))
    if (doc.get("user_agent") or {}).get("original"):
        ext.append(("requestClientApplication", doc["user_agent"]["original"]))
    user = doc.get("user") or {}
    if user.get("name"):
        ext.append(("suser", user["name"]))
    if user.get("id"):
        ext.append(("suid", user["id"]))
    ext.append(("act", ev.get("action")))
    ext.append(("outcome", ev.get("outcome")))
    ext.append(("cat", _premier(ev.get("category"))))
    ext.append(("externalId", ev.get("id")))
    if alerte and ev.get("reason"):
        ext.append(("msg", ev["reason"]))
    ext += [("cs1Label", "incident"), ("cs1", incident.get("id"))]
    ext += [("cs2Label", "session"), ("cs2", (doc.get("dedale") or {}).get("session_id"))]
    menace = doc.get("threat") or {}
    tech = ((menace.get("technique") or {}).get("id")) or []
    if tech:
        ext += [("cs3Label", "technique"), ("cs3", ",".join(tech))]
    regle = doc.get("rule") or {}
    if regle.get("id"):
        ext += [("cs4Label", "regle"), ("cs4", regle["id"])]
    ext += [("cs5Label", "type_incident"), ("cs5", type_inc)]
    if lien:
        ext += [("cs6Label", "console"), ("cs6", lien)]
    if alerte and ev.get("risk_score") is not None:
        ext += [("cn1Label", "score_risque"), ("cn1", int(ev["risk_score"]))]
    morceaux = []
    for cle, valeur in ext:
        if valeur is None or valeur == "":
            continue
        texte = echapper_extension(valeur)
        limite = _LIMITE.get(cle, 4000)
        morceaux.append(f"{cle}={texte[:limite]}")
    entete = "|".join([
        "CEF:0", "Dedale", "Dedale", echapper_entete(__version__), echapper_entete(signature),
        echapper_entete(str(nom)[:512]), str(severite),
    ])
    return entete + "|" + " ".join(morceaux)


def vers_cef(incident: dict, evenements: list[dict], lien: str | None = None) -> str:
    """Toutes les lignes CEF d'un incident, une par événement, séparées par un saut de ligne."""
    docs = ecs.vers_ecs(incident, evenements)["documents"]
    return "\n".join(ligne(d, incident, lien) for d in docs) + ("\n" if docs else "")


def ligne_incident(incident: dict, titre: str, phrase: str, lien: str | None = None,
                   motif: str = "incident") -> str:
    """Ligne CEF qui résume un incident (ouverture, gravité qui monte, décision). `titre` et
    `phrase` viennent de `notifications` : ni montant, ni bénéficiaire, ni nom de salarié."""
    gravite = incident.get("gravite") or "moyenne"
    type_inc = incident.get("type") or "inconnu"
    techniques = [t["id"] for t in ecs.sigma_regles.techniques_incident(type_inc)]
    rt = ecs.horodatage_ms(incident.get("cree_a")) or int(datetime.now(timezone.utc).timestamp() * 1000)
    ext = [
        ("rt", rt), ("act", motif), ("cat", "intrusion_detection"), ("externalId", incident.get("id")),
        ("msg", phrase), ("cs1Label", "incident"), ("cs1", incident.get("id")),
        ("cs3Label", "technique"), ("cs3", ",".join(techniques)),
        ("cs5Label", "type_incident"), ("cs5", type_inc),
        ("cs6Label", "console"), ("cs6", lien),
        ("cn1Label", "score_risque"), ("cn1", ecs.SEVERITE.get(gravite, 47)),
        ("flexString1Label", "statut"), ("flexString1", incident.get("statut")),
    ]
    morceaux = [f"{k}={echapper_extension(v)[:_LIMITE.get(k, 4000)]}" for k, v in ext if v not in (None, "")]
    entete = "|".join(["CEF:0", "Dedale", "Dedale", echapper_entete(__version__),
                       echapper_entete(f"{type_inc}:{motif}"), echapper_entete(str(titre)[:512]),
                       str(SEVERITE_CEF.get(gravite, 5))])
    return entete + "|" + " ".join(morceaux)


def trame_syslog(message: str, gravite: str | None = "moyenne", msgid: str = "incident",
                 hote: str | None = None, maintenant: datetime | None = None) -> str:
    """Enveloppe RFC 5424 : `<PRI>1 HORODATAGE HÔTE dedale - MSGID - MESSAGE`."""
    pri = FACILITE_LOCAL4 * 8 + SEVERITE_SYSLOG.get(gravite or "", 6)
    instant = (maintenant or datetime.now(timezone.utc)).astimezone(timezone.utc)
    horo = instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{instant.microsecond // 1000:03d}Z"
    nom = (hote or socket.gethostname() or "dedale").split(".")[0][:255] or "dedale"
    nom = "".join(c for c in nom if 33 <= ord(c) <= 126) or "dedale"
    return f"<{pri}>1 {horo} {nom} dedale - {msgid[:32]} - {message}"
