"""Qui reçoit quoi : notifications par rôle, par webhook (Slack, Teams, JSON) et par SMS simulé.

Deux destinataires, qui suivent la séparation des rôles de `auth.py` et du besoin d'en connaître
(`besoin_d_en_connaitre.py`, `validation_metier.py`) :

- un geste critique **retenu** sans signal de fraude (virement, export que le relecteur fait
  confirmer : acte `validation_demandee`) prévient le **validateur métier**, celui de l'espace
  `/validation`. Le message donne le geste, une tranche de montant et le service demandeur, avec
  le lien vers l'espace. Le bénéficiaire et le montant exact restent derrière son jeton ;
- une **menace** (tout incident de la console : agent IA détourné, lien piégé ouvert, fuite,
  geste au signal de fraude) prévient le **SOC** : webhook et ligne syslog dès la gravité
  moyenne, SMS d'astreinte en plus quand elle est critique. Un message au SOC ne contient jamais
  de montant ni de bénéficiaire : il est bâti sur des gabarits sans texte libre, puis
  `expurger_soc` retire en dernier filet tout montant, IBAN, adresse ou nom de bénéficiaire ;
- un geste accordé, un dossier déjà tranché, une trace de gravité faible ne préviennent personne.

Connecteurs (variables lues à chaque envoi) :

| Variable | Rôle |
|---|---|
| `DEDALE_NOTIF_SOC_URL`, `DEDALE_NOTIF_SOC_FORMAT` | webhook du SOC, format `slack`, `teams` ou `json` (défaut) |
| `DEDALE_NOTIF_VALIDATION_URL`, `DEDALE_NOTIF_VALIDATION_FORMAT` | webhook du validateur métier |
| `DEDALE_SMS_SOC`, `DEDALE_SMS_VALIDATION` | numéros d'astreinte (défaut : numéros fictifs ARCEP 06 39 98) |
| `DEDALE_SMS_JOURNAL` | journal de démo des SMS (défaut : `sms-demo.log` à côté de la base) |
| `DEDALE_SMS` | `off` coupe le SMS simulé |
| `DEDALE_NOTIFICATIONS` | `off` coupe tout le module |

**Le SMS n'est jamais envoyé.** Il est écrit dans le journal de démo (une ligne JSON par SMS)
et la console montre le texte qui partirait, avec son nombre de segments. Un webhook ne part
que si son URL est posée ; pour la démo, `python -m app.recepteur_siem` en écoute un en local.

Chaque envoi est dédoublonné par dossier et par règle : une menace prévient une fois, puis une
seconde fois par SMS si elle devient critique. Le webhook part dans un fil à part ; rien ne
ralentit le collecteur, et une erreur ne remonte jamais à l'appelant.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from . import cef, config, montants, sigma_regles, transfert_syslog

_journal = logging.getLogger(__name__)

DESTINATAIRES = {"soc": "Équipe sécurité (SOC)", "validation": "Validateur métier"}
FORMATS = ("slack", "teams", "json")
# Numéros réservés par l'ARCEP à la fiction (06 39 98 00 00 à 06 39 98 99 99).
SMS_DEFAUT = {"soc": "+33639980001", "validation": "+33639980002"}
_RANG = {"faible": 1, "moyenne": 2, "haute": 3, "critique": 4}
RESERVE_METIER = "Détail réservé à la validation métier."

historique: deque = deque(maxlen=200)
_envoyes: set[str] = set()
_signatures: dict[str, tuple] = {}
_fenetre_webhook: deque = deque()
_fenetre_sms: dict[str, deque] = {}
_fils: list[threading.Thread] = []
_verrou = threading.RLock()

# ---------------------------------------------------------------- Phrases sans jargon
# Une phrase par type d'incident : ce qui s'est passé, sans nom ni chiffre. Reprise par le SMS,
# le webhook, le transfert syslog et le résumé du lundi.
QUOI = {
    "externe_agent_ia": "Un robot d'IA a fouillé le site public et suivi un piège posé pour lui.",
    "interne_canari": "Un agent IA de l'entreprise a suivi une instruction cachée dans un mail ou un document.",
    "interne_outil_mcp": "Un agent IA a été piégé par un outil qu'on lui avait branché.",
    "interne_outil_modifie": "Un outil utilisé par un agent IA a changé en cours de route.",
    "interne_outil_inconnu": "Un agent IA a voulu se servir d'un outil qu'on ne lui a jamais donné.",
    "interne_appel": "Un agent IA a suivi une instruction glissée dans la transcription d'un appel.",
    "interne_chatbot": "Le chatbot a été détourné par un message piégé.",
    "interne_memoire": "Un agent IA a été trompé par une fausse information glissée dans sa mémoire.",
    "interne_inter_agent": "Un agent IA a reçu une demande d'un faux collègue.",
    "interne_droits": "Un agent IA a voulu faire une action qui sort de sa mission.",
    "interne_desarme": "Une instruction cachée a été retirée d'un document avant qu'un agent IA le lise.",
    "interne_envoi_externe": "Un agent IA a voulu envoyer des données hors de l'entreprise.",
    "interne_canal_detourne": "Un agent IA a détourné un outil pour faire sortir des données.",
    "interne_politique": "Un agent IA a buté sur une règle écrite par l'équipe sécurité.",
    "interne_anomalie": "Un agent IA s'est comporté autrement que d'habitude.",
    "humain_phishing": "Un salarié a ouvert un lien piégé malgré l'alerte de son poste.",
    "humain_secret": "Un salarié a failli partager un mot de passe ou une clé d'accès.",
    "humain_mail_externe": "Un salarié a envoyé des données sensibles vers une adresse extérieure.",
    "humain_upload_ia": "Un salarié a déposé un fichier confidentiel dans une IA non autorisée.",
    "humain_intrusion_physique": "Quelqu'un a touché à un équipement-piège dans les locaux.",
    "humain_signalement": "Un salarié a signalé un mail suspect.",
}

GESTES = {"virement": "un virement", "export_clients": "un export de données clients"}


def geste_de(detail: dict) -> str | None:
    """`virement` ou `export_clients` lu sur la demande à quatre yeux de l'incident."""
    for e in detail.get("_evenements") or []:
        g = (e.get("details") or {}).get("geste")
        if g in GESTES:
            return g
    for m in detail.get("chaine") or []:
        texte = str(m.get("detail") or "")
        if "un virement" in texte:
            return "virement"
        if "export de données clients" in texte:
            return "export_clients"
    return None


def _est_geste(detail: dict) -> bool:
    return bool(detail.get("quatre_yeux")) and geste_de(detail) is not None


def quoi(detail: dict) -> str:
    """Ce qui s'est passé, en une phrase, pour un incident (geste au signal de fraude compris)."""
    geste = geste_de(detail)
    if geste and detail.get("quatre_yeux"):
        if detail.get("contexte_humain") == "mail reçu" or detail.get("type") == "humain_phishing":
            return f"Un mail frauduleux a poussé un salarié à demander {GESTES[geste]}."
        return f"Un salarié a demandé {GESTES[geste]} qui porte un signal de fraude."
    return QUOI.get(detail.get("type") or "", "sAIfe a ouvert un dossier de sécurité.")


def _decisions_humaines(detail: dict) -> list[dict]:
    return [d for d in detail.get("decisions") or []
            if not str(d.get("analyste") or "").lower().startswith("relecteur")]


def issue(detail: dict) -> str:
    """Où en est le dossier, en une phrase : ce que Dédale ou un humain a fait, ce qui attend."""
    rel = detail.get("relecteur") or {}
    humaines = _decisions_humaines(detail)
    geste = geste_de(detail)
    if detail.get("quatre_yeux") and geste:
        mot = "le virement" if geste == "virement" else "l'export"
        if humaines:
            a = humaines[-1].get("action")
            return (f"L'équipe sécurité a accordé {mot}." if a in ("accorder", "ignorer")
                    else f"L'équipe sécurité a refusé {mot}, qui n'a pas eu lieu.")
        d = rel.get("decision")
        if d == "refuse":
            return f"Le relecteur de sAIfe l'a refusé et {mot} n'a pas eu lieu."
        if d == "accorde":
            return "Le relecteur de sAIfe l'a accordé."
        return f"{mot[0].upper()}{mot[1:]} est suspendu jusqu'à la décision de l'équipe sécurité."
    if detail.get("source") in ("humain", "physique"):
        if detail.get("statut") in ("clos", "ignore"):
            return "Le dossier est clos et le poste n'a jamais été bloqué."
        return "Le poste n'a pas été bloqué et le dossier attend une relecture."
    etat = detail.get("etat")
    if etat == "coupee":
        return "L'agent a été coupé."
    if detail.get("statut") in ("clos", "ignore"):
        return "Le dossier est clos."
    if etat == "suspendue":
        return "L'agent est suspendu jusqu'à votre décision."
    return "L'agent continue son travail sous surveillance."


# ---------------------------------------------------------------- Expurger ce qui part au SOC
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[  ]?[0-9A-Z•*]{4}){2,7}(?:[  ]?[0-9A-Z•*]{1,4})?\b")
_ADRESSE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CHIFFRE_ARGENT = re.compile(
    r"\d[\d  .,']*\s?(?:k|m|md)?\s?(?:€|eur\b|euros?\b|\$|usd\b|£|gbp\b|chf\b)", re.IGNORECASE)


def _noms_beneficiaires(detail: dict | None) -> list[str]:
    noms: list[str] = []
    try:
        from . import relecteur
        for b in relecteur.beneficiaires():
            noms += [b.get("nom") or ""] + list(b.get("alias") or [])
    except Exception:  # la liste aide ; sans elle, le gabarit seul garde le texte propre
        pass
    for e in (detail or {}).get("_evenements") or []:
        d = e.get("details") or {}
        virement = d.get("virement") if isinstance(d.get("virement"), dict) else {}
        for v in (d.get("beneficiaire"), virement.get("beneficiaire")):
            if isinstance(v, str) and len(v.strip()) >= 3:
                noms.append(v.strip())
    return sorted({n for n in noms if len(n) >= 3}, key=len, reverse=True)


def expurger_soc(texte: str, detail: dict | None = None) -> str:
    """Retire d'un texte destiné au SOC tout montant, IBAN, adresse et nom de bénéficiaire."""
    t = _IBAN.sub("[IBAN retiré]", texte)
    t = _ADRESSE.sub("[adresse retirée]", t)
    t = montants._APRES.sub("[montant retiré]", t)
    t = montants._AVANT.sub("[montant retiré]", t)
    t = _CHIFFRE_ARGENT.sub("[montant retiré]", t)
    for nom in _noms_beneficiaires(detail):
        t = re.sub(r"(?<!\w)" + re.escape(nom) + r"(?!\w)", "[bénéficiaire retiré]", t, flags=re.IGNORECASE)
    return t


# ---------------------------------------------------------------- Envois
@dataclass
class Envoi:
    cle: str
    regle: str
    destinataire: str
    canaux: list[str]
    raison: str
    titre: str
    texte: str
    sms: str
    lien: str
    gravite: str
    faits: list[tuple[str, str]] = field(default_factory=list)


REGLES = [
    {"regle": "geste_retenu", "destinataire": "validation", "canaux": ["webhook", "sms"],
     "quand": "Un virement ou un export de données clients sans signal de fraude, que le relecteur fait "
              "confirmer par le responsable du salarié ou la finance.",
     "contenu": "Le geste, une tranche de montant, le service demandeur et le lien vers l'espace de "
                "validation. Jamais le bénéficiaire ni le montant exact."},
    {"regle": "menace", "destinataire": "soc", "canaux": ["webhook", "syslog"],
     "quand": "Un dossier de gravité moyenne ou plus dans la console : agent IA détourné, lien piégé ouvert, "
              "fuite de données, geste qui porte un signal de fraude.",
     "contenu": "Ce qui s'est passé, l'état de l'agent ou du poste, la gravité et le lien vers le "
                "dossier. Jamais de montant, de bénéficiaire ni de nom de salarié."},
    {"regle": "menace_critique", "destinataire": "soc", "canaux": ["sms"],
     "quand": "La même menace, quand sa gravité est critique (hors surface exposée et hors banc d'essai).",
     "contenu": "Un SMS d'astreinte, mêmes interdits que le webhook."},
    {"regle": "personne", "destinataire": None, "canaux": [],
     "quand": "Geste accordé, dossier déjà clos, ou trace de gravité faible.",
     "contenu": "Rien ne part. Le dossier reste dans la console et dans le résumé du lundi."},
]


def url_console() -> str:
    return os.environ.get("DEDALE_CONSOLE_URL", "http://127.0.0.1:5173").strip().rstrip("/")


def url_validation() -> str:
    return os.environ.get("DEDALE_VALIDATION_URL", "").strip().rstrip("/") or f"{url_console()}/validation"


def lien_incident(iid: str) -> str:
    return f"{url_console()}/?incident={quote(iid)}"


def _relecteur_actif() -> bool:
    try:
        from . import relecteur
        return relecteur.actif()
    except Exception:
        return False


def titre_soc(detail: dict) -> str:
    """Titre d'un dossier pour le SOC : celui de la règle Sigma du type, ou du geste en fraude."""
    geste = geste_de(detail) if detail.get("quatre_yeux") else None
    if geste:
        return f"{GESTES[geste][3:].capitalize()} au signal de fraude"
    fiche = sigma_regles.CATALOGUE.get(detail.get("type") or "")
    return fiche.titre if fiche else f"Dossier {detail.get('id')}"


def regle_pour(detail: dict) -> tuple[str, str]:
    """(règle, raison) qui s'applique à l'état actuel d'un incident (toujours côté SOC)."""
    gravite = detail.get("gravite") or "moyenne"
    if detail.get("statut") in ("clos", "ignore"):
        return "personne", "Le dossier est déjà clos."
    if _est_geste(detail):
        if _decisions_humaines(detail):
            return "personne", "L'équipe sécurité a déjà tranché ce geste."
        decision = (detail.get("relecteur") or {}).get("decision")
        if decision == "accorde":
            return "personne", "Le relecteur a accordé le geste : rien à faire."
        if decision is None and _relecteur_actif():
            return "attente", "Le relecteur lit encore le geste : la règle se rejouera après sa décision."
    if _RANG.get(gravite, 2) < _RANG["moyenne"]:
        return "personne", "Gravité faible : le dossier reste dans la console et le résumé du lundi."
    if gravite == "critique" and _sms_soc_permis(detail):
        return "menace", "Gravité critique : webhook, transfert syslog et SMS d'astreinte."
    return "menace", f"Gravité {gravite} : webhook et transfert syslog, pas de SMS en dessous de critique."


def _sms_soc_permis(detail: dict) -> bool:
    """Pas de SMS d'astreinte pour la surface exposée (le banc y envoie des centaines d'agents)
    ni pour une session du banc d'essai."""
    sid = str(detail.get("session_id") or "")
    return detail.get("source") != "externe" and not sid.startswith("banc-")


def envois_pour(detail: dict) -> tuple[str, str, list[Envoi]]:
    """(règle, raison, envois) pour l'état actuel d'un incident."""
    regle, raison = regle_pour(detail)
    iid = str(detail.get("id"))
    gravite = detail.get("gravite") or "moyenne"
    envois: list[Envoi] = []
    if regle != "menace":
        return regle, raison, envois
    titre = expurger_soc(f"Menace {gravite} : {titre_soc(detail)}", detail)
    lien = lien_incident(iid)
    texte = expurger_soc(f"{quoi(detail)} {issue(detail)} Dossier {iid}.", detail)
    envois.append(Envoi(f"{iid}:menace", "menace", "soc", ["webhook"], raison, titre, texte, "", lien, gravite,
                        [("Gravité", gravite), ("Dossier", iid), ("Type", detail.get("type") or "—")]))
    if gravite == "critique" and _sms_soc_permis(detail):
        phrase = quoi(detail)
        sms = expurger_soc(f"sAIfe, menace critique : {phrase[0].lower()}{phrase[1:]} {issue(detail)} {iid} {lien}",
                           detail)
        envois.append(Envoi(f"{iid}:menace_critique", "menace_critique", "soc", ["sms"],
                            "Gravité critique : SMS d'astreinte au SOC.", titre, texte, sms, lien, gravite))
    return regle, raison, envois


def envoi_validation(enreg: dict) -> Envoi | None:
    """Envoi au validateur pour un acte `validation_demandee` encore à valider, ou None."""
    from . import besoin_d_en_connaitre, identites
    from .store import store

    d = enreg.get("details") or {}
    if enreg.get("type") != "validation_demandee" or d.get("statut", "a_valider") != "a_valider":
        return None
    geste = d.get("geste") if d.get("geste") in GESTES else "virement"
    if geste == "virement":
        t = besoin_d_en_connaitre.tranche(d.get("montant_eur"))
        precision = f" ({t})" if t else " (montant à lire dans l'espace de validation)"
    else:
        v = d.get("volume")
        precision = f" (environ {int(v):,} fiches)".replace(",", " ") if isinstance(v, (int, float)) and v else ""
    with store.lock:
        sess = store.sessions.get(enreg.get("session_id") or "")
        evs = [store.evenements[i] for i in sess.evenement_ids if i in store.evenements] if sess else []
    service = identites.identite(enreg.get("session_id") or "", evs).get("service")
    demandeur = f"Demandé par le service {service}." if service else "Demandé depuis un poste de l'entreprise."
    nom = GESTES[geste]
    nom_maj = nom[0].upper() + nom[1:]
    did = str(d.get("demande_id") or enreg.get("id"))
    titre = f"{nom_maj} attend votre validation"
    texte = (f"{nom_maj}{precision} attend votre validation. {demandeur} sAIfe l'a suspendu : rien ne part "
             f"tant que vous n'avez pas décidé.")
    sms = f"sAIfe : {nom}{precision} attend votre validation. {demandeur} Validez ou refusez ici : {url_validation()}"
    return Envoi(f"validation:{did}", "geste_retenu", "validation", ["webhook", "sms"],
                 "Le relecteur fait confirmer ce geste par le responsable du salarié ou la finance.",
                 titre, texte, sms, url_validation(), "haute",
                 [("Geste", nom), ("Montant", precision.strip(" ()") or "—"), ("Service", service or "—"),
                  ("Demande", did)])


# ---------------------------------------------------------------- Formats de webhook
def _slack(t) -> str:
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def charge_utile(envoi: Envoi, fmt: str, ref: str) -> dict:
    """Message prêt à poster, au format Slack (blocs), Teams (carte adaptative) ou JSON."""
    bouton = "Ouvrir l'espace de validation" if envoi.destinataire == "validation" else "Ouvrir le dossier"
    if fmt == "slack":
        return {"text": f"{envoi.titre}. {envoi.texte} {envoi.lien}", "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": envoi.titre[:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": _slack(envoi.texte)}},
            {"type": "section", "fields": [{"type": "mrkdwn", "text": f"*{_slack(k)}*\n{_slack(v)}"}
                                           for k, v in envoi.faits[:10]]},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": bouton}, "url": envoi.lien}]},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": "sAIfe · Orbis Pay, entreprise fictive · trafic de démonstration"}]},
        ]}
    if fmt == "teams":
        couleur = {"critique": "Attention", "haute": "Warning"}.get(envoi.gravite, "Default")
        return {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": envoi.titre, "weight": "Bolder", "size": "Medium",
                     "color": couleur, "wrap": True},
                    {"type": "TextBlock", "text": envoi.texte, "wrap": True},
                    {"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in envoi.faits]},
                    {"type": "TextBlock", "text": "sAIfe · Orbis Pay, entreprise fictive · trafic de démonstration",
                     "size": "Small", "isSubtle": True, "wrap": True},
                ],
                "actions": [{"type": "Action.OpenUrl", "title": bouton, "url": envoi.lien}],
            }}]}
    return {"source": "dedale", "version": 1, "regle": envoi.regle, "destinataire": envoi.destinataire,
            "gravite": envoi.gravite, "reference": ref, "titre": envoi.titre, "texte": envoi.texte,
            "lien": envoi.lien, "faits": dict(envoi.faits)}


# ---------------------------------------------------------------- SMS simulé
_GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "ÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM7_EXT = set("^{}\\[~]|€\f")


def segments(texte: str) -> dict:
    """Encodage et nombre de segments SMS : GSM-7 (160, puis 153 par segment) ou UCS-2 (70, puis 67)."""
    if all(c in _GSM7 or c in _GSM7_EXT for c in texte):
        n = sum(2 if c in _GSM7_EXT else 1 for c in texte)
        return {"encodage": "GSM-7", "caracteres": n, "segments": 1 if n <= 160 else -(-n // 153)}
    n = len(texte.encode("utf-16-le")) // 2
    return {"encodage": "UCS-2", "caracteres": n, "segments": 1 if n <= 70 else -(-n // 67)}


def numero(role: str) -> str | None:
    if os.environ.get("DEDALE_SMS", "").strip().lower() == "off":
        return None
    brut = os.environ.get(f"DEDALE_SMS_{role.upper()}", "").strip() or SMS_DEFAUT[role]
    chiffres = re.sub(r"[^\d+]", "", brut)
    return chiffres if re.fullmatch(r"\+?\d{8,15}", chiffres) else None


def numero_masque(num: str | None) -> str | None:
    if not num:
        return None
    return num[:3] + " " + "•" * max(0, len(num) - 5) + " " + num[-2:]


def journal_sms() -> Path:
    brut = os.environ.get("DEDALE_SMS_JOURNAL", "").strip()
    return Path(brut).expanduser() if brut else Path(config.CHEMIN_DB).parent / "sms-demo.log"


def _ecrire_sms(entree: dict) -> None:
    chemin = journal_sms()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    ligne = json.dumps({k: entree.get(k) for k in ("horodatage", "reference", "destinataire", "a", "texte",
                                                   "encodage", "segments")}, ensure_ascii=False)
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(ligne + "\n")


def _sms_limite(role: str) -> bool:
    try:
        plafond = max(1, int(os.environ.get("DEDALE_SMS_MAX_HEURE", "10")))
    except ValueError:
        plafond = 10
    fenetre = _fenetre_sms.setdefault(role, deque())
    maintenant = time.monotonic()
    while fenetre and maintenant - fenetre[0] > 3600:
        fenetre.popleft()
    if len(fenetre) >= plafond:
        return True
    fenetre.append(maintenant)
    return False


# ---------------------------------------------------------------- Webhooks
def connecteur_webhook(role: str) -> dict | None:
    url = os.environ.get(f"DEDALE_NOTIF_{role.upper()}_URL", "").strip()
    if not url:
        return None
    fmt = os.environ.get(f"DEDALE_NOTIF_{role.upper()}_FORMAT", "json").strip().lower()
    return {"url": url, "format": fmt if fmt in FORMATS else "json"}


def _webhook_limite() -> bool:
    try:
        plafond = max(1, int(os.environ.get("DEDALE_NOTIF_MAX_MINUTE", "20")))
    except ValueError:
        plafond = 20
    maintenant = time.monotonic()
    while _fenetre_webhook and maintenant - _fenetre_webhook[0] > 60:
        _fenetre_webhook.popleft()
    if len(_fenetre_webhook) >= plafond:
        return True
    _fenetre_webhook.append(maintenant)
    return False


def _poster(entree: dict, url: str) -> None:
    try:
        with httpx.Client(timeout=3.0) as client:
            rep = client.post(url, json=entree["message"])
        entree["statut"] = "envoyee" if rep.status_code < 300 else "refusee"
        entree["code_http"] = rep.status_code
    except Exception as exc:
        entree["statut"] = "echec"
        entree["raison"] = type(exc).__name__
        _journal.warning("Notification %s non envoyée : %s", entree.get("reference"), type(exc).__name__)


def _entree(envoi: Envoi, ref: str, canal: str) -> dict:
    return {"id": uuid.uuid4().hex[:12], "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reference": ref, "incident_id": None if envoi.destinataire == "validation" else ref,
            "regle": envoi.regle, "destinataire": envoi.destinataire,
            "destinataire_libelle": DESTINATAIRES[envoi.destinataire], "canal": canal, "statut": None}


def apercus(envoi: Envoi, ref: str) -> list[dict]:
    """Ce qui partirait par chaque canal de cet envoi, sans rien envoyer."""
    sortie = []
    for canal in envoi.canaux:
        e = _entree(envoi, ref, canal)
        if canal == "sms":
            num = numero(envoi.destinataire)
            e.update({"a": numero_masque(num), "texte": envoi.sms, **segments(envoi.sms),
                      "statut": "simule" if num else "coupe"})
        else:
            conn = connecteur_webhook(envoi.destinataire)
            fmt = conn["format"] if conn else "json"
            e.update({"format": fmt, "a": f"webhook {fmt}" if conn else None,
                      "texte": f"{envoi.titre}. {envoi.texte}", "message": charge_utile(envoi, fmt, ref),
                      "statut": "pret" if conn else "non_configure"})
        sortie.append(e)
    return sortie


def expedier(envoi: Envoi, ref: str) -> list[dict]:
    """Envoie (webhook) ou simule (SMS) chaque canal de l'envoi et l'inscrit à l'historique."""
    sorties = []
    for e in apercus(envoi, ref):
        if e["canal"] == "sms":
            if numero(envoi.destinataire) is None:
                e["statut"], e["raison"] = "coupe", "DEDALE_SMS=off ou numéro invalide"
            elif _sms_limite(envoi.destinataire):
                e["statut"], e["raison"] = "limitee", "plafond de SMS par heure atteint"
            else:
                e["statut"] = "simule"
                e["note"] = "SMS non envoyé : écrit dans le journal de démo."
                try:
                    _ecrire_sms(e)
                except OSError as exc:
                    e["statut"], e["raison"] = "echec", type(exc).__name__
        else:
            conn = connecteur_webhook(envoi.destinataire)
            if conn is None:
                e["statut"] = "non_envoyee"
                e["raison"] = f"DEDALE_NOTIF_{envoi.destinataire.upper()}_URL absent : aucun envoi"
            elif not conn["url"].startswith(("http://", "https://")):
                e["statut"], e["raison"] = "configuration_invalide", "l'URL doit commencer par http:// ou https://"
            elif _webhook_limite():
                e["statut"], e["raison"] = "limitee", "plafond de webhooks par minute atteint"
            else:
                e["statut"] = "en_cours"
                fil = threading.Thread(target=_poster, args=(e, conn["url"]), daemon=True, name="dedale-notif")
                with _verrou:
                    _fils.append(fil)
                fil.start()
        with _verrou:
            historique.appendleft(e)
        sorties.append(e)
    return sorties


def _expedier_une_fois(envoi: Envoi, ref: str) -> list[dict]:
    with _verrou:
        if envoi.cle in _envoyes:
            return []
        _envoyes.add(envoi.cle)
    return expedier(envoi, ref)


# ---------------------------------------------------------------- Examen
def actif() -> bool:
    return os.environ.get("DEDALE_NOTIFICATIONS", "").strip().lower() != "off"


def detail_complet(iid: str) -> dict | None:
    """Incident vu par l'API (pseudonymisé), avec ses événements sous `_evenements`."""
    from .store import store
    detail = store.incident_detail(iid)
    if detail is None:
        return None
    sess = store.session_detail(detail["session_id"]) or {}
    detail["_evenements"] = sess.get("evenements") or []
    return detail


def _signature(detail: dict) -> tuple:
    rel = detail.get("relecteur") or {}
    return (detail.get("type"), detail.get("gravite"), detail.get("statut"), rel.get("decision"),
            len(detail.get("decisions") or []))


def ligne_cef(detail: dict, motif: str = "incident") -> str:
    phrase = expurger_soc(f"{quoi(detail)} {issue(detail)}", detail)
    geste = geste_de(detail) if detail.get("quatre_yeux") else None
    return cef.ligne_incident(detail, titre_soc(detail), phrase, lien_incident(str(detail.get("id"))), motif, geste)


def examiner(iid: str) -> list[dict]:
    """Applique la règle à l'état actuel de l'incident : envoie ce qui n'est pas encore parti, et
    transfère au SIEM une ligne CEF quand l'incident a changé. Ne lève jamais."""
    if not actif():
        return []
    try:
        detail = detail_complet(iid)
        if detail is None:
            return []
        regle, _, envois = envois_pour(detail)
        sorties: list[dict] = []
        for envoi in envois:
            sorties += _expedier_une_fois(envoi, iid)
        if regle == "attente":
            return sorties
        signature = _signature(detail)
        with _verrou:
            avant = _signatures.get(iid)
            _signatures[iid] = signature
        if avant != signature and _RANG.get(detail.get("gravite") or "moyenne", 2) >= _RANG["moyenne"]:
            motif = "ouverture" if avant is None else "mise_a_jour"
            trame = cef.trame_syslog(ligne_cef(detail, motif), detail.get("gravite"), motif)
            transfert_syslog.transferer_en_fond(trame, iid, motif)
        return sorties
    except Exception:
        _journal.exception("Notifications : échec sur %s", iid)
        return []


def examiner_validation(enreg: dict) -> list[dict]:
    """Prévient le validateur pour un acte `validation_demandee`. Ne lève jamais."""
    if not actif():
        return []
    try:
        envoi = envoi_validation(enreg)
        if envoi is None:
            return []
        return _expedier_une_fois(envoi, envoi.cle.split(":", 1)[1])
    except Exception:
        _journal.exception("Notifications : échec sur une demande de validation")
        return []


def examiner_session(session_id: str) -> None:
    from .store import store
    with store.lock:
        ids = [i.id for i in store.incidents.values() if i.session_id == session_id]
    for iid in ids:
        examiner(iid)


# ---------------------------------------------------------------- Lectures
def vue_soc(entree: dict) -> dict:
    """Ce que la console du SOC voit d'un envoi : tout pour une menace ; pour le validateur, le
    canal et le statut seulement (besoin d'en connaître)."""
    if entree.get("destinataire") != "validation":
        return dict(entree)
    return {k: entree.get(k) for k in ("id", "horodatage", "regle", "destinataire", "destinataire_libelle",
                                        "canal", "statut", "a")} | {"texte": RESERVE_METIER}


def apercu_incident(iid: str) -> dict | None:
    """Ce qui partirait pour cet incident, qui le recevrait et pourquoi, et ce qui est parti."""
    detail = detail_complet(iid)
    if detail is None:
        return None
    regle, raison, envois = envois_pour(detail)
    prevus = [a for envoi in envois for a in apercus(envoi, iid)]
    with _verrou:
        envoyes = [dict(e) for e in historique if e.get("incident_id") == iid]
    return {
        "incident_id": iid,
        "regle": regle,
        "raison": raison,
        "prevus": prevus,
        "envoyes": envoyes,
        "syslog": {**transfert_syslog.etat(), "ligne_cef": ligne_cef(detail, "apercu")},
        "rien_ne_part": "Le SMS n'est jamais envoyé : il est écrit dans le journal de démo. Un webhook ne "
                        "part que si son URL est posée.",
    }


def pour_validateur() -> list[dict]:
    """Envois au validateur, en entier : lus dans l'espace de validation, jamais par le SOC."""
    with _verrou:
        return [dict(e) for e in historique if e.get("destinataire") == "validation"]


def etat() -> dict:
    """Connecteurs configurés (jamais une URL), règles et derniers envois vus par le SOC."""
    connecteurs = []
    for role in DESTINATAIRES:
        conn = connecteur_webhook(role)
        connecteurs.append({"destinataire": role, "libelle": DESTINATAIRES[role], "canal": "webhook",
                            "configure": conn is not None, "format": conn["format"] if conn else None})
        num = numero(role)
        connecteurs.append({"destinataire": role, "libelle": DESTINATAIRES[role], "canal": "sms",
                            "configure": num is not None, "a": numero_masque(num), "simule": True})
    with _verrou:
        derniers = [vue_soc(e) for e in list(historique)[:50]]
    return {"actif": actif(), "connecteurs": connecteurs, "regles": REGLES,
            "syslog": transfert_syslog.etat(), "journal_sms": journal_sms().name, "historique": derniers}


def attendre(delai: float = 5.0) -> None:
    """Attend la fin des webhooks en cours (tests, arrêt)."""
    fin = time.monotonic() + delai
    with _verrou:
        fils = list(_fils)
        _fils.clear()
    for f in fils:
        f.join(max(0.0, fin - time.monotonic()))


def vider() -> None:
    """Remet le module à zéro (tests)."""
    with _verrou:
        historique.clear()
        _envoyes.clear()
        _signatures.clear()
        _fenetre_webhook.clear()
        _fenetre_sms.clear()
        _fils.clear()
    transfert_syslog.historique.clear()
