"""Mémoire du relecteur IA : les gestes déjà jugés par un analyste humain.

Qui l'alimente. Seule une décision humaine qui confirme ou renverse une relecture y entre :
jamais le relecteur seul, jamais ce que déclare le salarié. Sinon un attaquant pourrait
l'empoisonner (« memory poisoning », OWASP agentique). Chaque entrée est un événement `memoire`
scellé dans le journal, et elle ne compte que si elle cite le sceau d'une décision humaine
présente dans la chaîne des décisions : un événement `memoire` envoyé de l'extérieur est ignoré.

Ce qu'elle garde. Le geste, jamais la personne : type de geste, bénéficiaire connu ou domaine
interne en clair, sinon une empreinte ; tranche et ordre de grandeur du montant ou du volume ;
empreinte des quatre derniers chiffres du RIB ; fréquence ; verdict final ; motif de l'analyste ;
date. Aucun pseudonyme, aucun score ni historique par salarié (RGPD, annexe III de l'AI Act). Elle
vit dans le journal : même conservation que le reste.

Comment on s'en sert. À chaque geste, les 3 à 5 précédents les plus proches, par des critères
simples : même type, même bénéficiaire ou domaine, montant proche. Ils vont au modèle comme des
données et aux règles de repli. Les règles dures du SOC gagnent toujours sur la mémoire.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import journal_scelle
from .store import store

MAX_PRECEDENTS = 5
RENVERSEMENT_RECENT_JOURS = 30
ECART_MONTANT = 0.3  # « montant proche » : à 30 % près
_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


# ---------------------------------------------------------------- Clés du geste (jamais la personne)
def _plat(t: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().split())


def _empreinte(prefixe: str, valeur: str) -> str:
    return f"{prefixe}:" + hashlib.sha256(f"dedale:memoire:{prefixe}:{valeur}".encode("utf-8")).hexdigest()[:12]


def cle_geste(faits: dict) -> tuple[str | None, str]:
    """(clé de rapprochement, libellé) : bénéficiaire connu en clair, domaine d'Orbis Pay en clair,
    sinon une empreinte. None quand le geste ne désigne personne de reconnaissable."""
    geste = faits.get("geste")
    b = faits.get("beneficiaire") or {}
    if geste == "virement":
        if b.get("connu"):
            return f"beneficiaire:{_plat(b['nom'])}", "même " + (b.get("nature") or "bénéficiaire")
        if b.get("cle_nom"):
            return _empreinte("nom", b["cle_nom"]), "même bénéficiaire"
        return None, ""
    dest = faits.get("destination") or {}
    dom = dest.get("domaine")
    if geste == "export_clients" and dom:
        return (f"domaine:{dom}" if dest.get("interne") else _empreinte("domaine", dom)), "même destination"
    return None, ""


def tranche(geste: str | None, montant: float | None, volume: int | None) -> str | None:
    if geste == "virement" and montant is not None:
        bornes = [(500, "moins de 500 €"), (1000, "500 à 1 000 €"), (5000, "1 000 à 5 000 €"),
                  (10000, "5 000 à 10 000 €")]
        return next((lib for b, lib in bornes if montant <= b), "plus de 10 000 €")
    if geste == "export_clients" and volume is not None:
        return "moins de 100 fiches" if volume < 100 else "100 à 1 000 fiches" if volume < 1000 else "1 000 fiches ou plus"
    return None


def _ordre_de_grandeur(geste: str | None, montant: float | None, volume: int | None) -> float | None:
    """Montant arrondi à la centaine (ou volume à la dizaine) : assez pour comparer, pas plus."""
    if geste == "virement" and montant is not None:
        return float(round(montant / 100) * 100)
    if geste == "export_clients" and volume is not None:
        return float(round(volume / 10) * 10)
    return None


def empreinte(prefixe: str, valeur: str) -> str:
    return _empreinte(prefixe, valeur)


def _rib(faits: dict) -> str | None:
    """Empreinte de l'IBAN du geste (`beneficiaire.rib_cle`, posée par le relecteur)."""
    b = faits.get("beneficiaire") or {}
    if isinstance(b.get("rib_cle"), str):
        return b["rib_cle"]
    fin = (b.get("rib_demande") or "").replace("•", "").strip()
    return _empreinte("rib", fin) if re.fullmatch(r"\d{4}", fin) else None


def couples(faits: dict) -> dict:
    """Couples bénéficiaire et IBAN confirmés par un humain : `{"confirmes": {empreinte IBAN:
    montant le plus haut accordé}, "pays": {pays d'IBAN accordés}}`. La dernière décision humaine
    sur un couple l'emporte : un refus après un accord le retire. Sous verrou."""
    cle, _ = cle_geste(faits)
    confirmes: dict[str, float] = {}
    pays: set[str] = set()
    if cle is None or faits.get("geste") != "virement":
        return {"confirmes": confirmes, "pays": pays}
    vus: set[str] = set()
    for e in entrees():  # de la plus récente à la plus ancienne
        rib = e.get("rib")
        if e.get("geste") != "virement" or e.get("cle") != cle or not isinstance(rib, str) or rib in vus:
            continue
        vus.add(rib)
        if e.get("verdict") == "accorde":
            og = e.get("ordre_de_grandeur")
            confirmes[rib] = float(og) if isinstance(og, (int, float)) else 0.0
            if isinstance(e.get("iban_pays"), str):
                pays.add(e["iban_pays"])
    return {"confirmes": confirmes, "pays": pays}


# ---------------------------------------------------------------- Signature des entrées
# Une entrée n'est écrite que par le backend, après la décision d'un humain (analyste ou
# validateur métier). Elle porte une signature HMAC d'une clé qui ne quitte pas le serveur
# (`cle-memoire`, dans le dossier des jetons, en 600) : un événement `memoire` envoyé par le
# collecteur, même par un client authentifié, n'a pas de signature valable et reste ignoré.
_verrou_cle = threading.Lock()
_cles: dict[str, bytes] = {}


def _dossier_cles() -> Path:
    brut = os.environ.get("DEDALE_JETONS", "").strip()
    return Path(brut).expanduser() if brut else Path.home() / ".config" / "dedale"


def _cle() -> bytes:
    chemin = _dossier_cles() / "cle-memoire"
    with _verrou_cle:
        if str(chemin) not in _cles:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(chemin.parent, 0o700)
            except OSError:
                pass
            if not chemin.exists():
                fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(secrets.token_hex(32))
            _cles[str(chemin)] = chemin.read_text().strip().encode()
        return _cles[str(chemin)]


def signer(details: dict) -> str:
    contenu = journal_scelle.canonique({k: v for k, v in details.items() if k != "signature"})
    return hmac.new(_cle(), contenu.encode("utf-8"), hashlib.sha256).hexdigest()


def _signature_valide(details: dict) -> bool:
    sig = details.get("signature")
    return isinstance(sig, str) and hmac.compare_digest(sig, signer(details))


def sceller(sess, type_: str, details: dict, user_agent: str = "dedale-memoire") -> dict:
    """Ajoute un événement de service à la session (scellé), et rend le travail à persister."""
    moment = datetime.now(timezone.utc).isoformat()
    eid = store._nouvel_id()
    enreg = {"id": eid, "horodatage": moment, "recu_a": moment, "source": sess.source, "surface": "soc",
             "type": type_, "session_id": sess.id, "leurre_id": None, "leurre_nature": None, "ip": None,
             "user_agent": user_agent, "methode": None, "chemin": None, "outil": None, "details": details}
    store.tete_evenements = journal_scelle.sceller_evenement(enreg, store.tete_evenements)
    store.evenements[eid] = enreg
    sess.evenement_ids.append(eid)
    return enreg


# ---------------------------------------------------------------- Entrées valides
def entrees() -> list[dict]:
    """Entrées signées par le backend après une décision humaine, de la plus récente à la plus
    ancienne. Sous verrou."""
    sortie = []
    for e in store.evenements.values():
        d = e.get("details") or {}
        if e.get("type") != "memoire" or not _signature_valide(d):
            continue  # pas écrite par le backend après une décision humaine : ignorée
        sortie.append(d)
    sortie.sort(key=lambda d: d.get("date") or "", reverse=True)
    return sortie


def _entree(faits: dict, verdict: str, humain: str, role: str, date: str | None, motif: str | None,
            **extra) -> dict | None:
    """Entrée signée pour un geste tranché par un humain : le geste, jamais la personne."""
    from . import relecteur  # import local : le relecteur importe ce module
    cle, _ = cle_geste(faits)
    if cle is None:
        return None
    geste = faits.get("geste")
    b = faits.get("beneficiaire") or {}
    details = {
        "acte": "memoire", "geste": geste, "cle": cle,
        "beneficiaire": b.get("nom") if b.get("connu") else None,
        "tranche": tranche(geste, faits.get("montant_eur"), faits.get("volume")),
        "ordre_de_grandeur": _ordre_de_grandeur(geste, faits.get("montant_eur"), faits.get("volume")),
        "rib": _rib(faits), "iban_pays": b.get("pays_iban"),
        "frequence": sum(1 for x in entrees() if x.get("cle") == cle) + 1,
        "verdict": verdict, "role": role,
        "motif_analyste": relecteur.motif_propre(motif) if motif else None,
        "analyste": str(humain or "")[:40], "date": date or datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    details["signature"] = signer(details)
    return details


# ---------------------------------------------------------------- Écrire après une décision humaine
def apres_decision(iid: str, faits_de: callable) -> dict | None:
    """Appelé après `POST /api/incidents/{iid}/decision`. Si un analyste vient de confirmer ou de
    renverser la relecture d'un geste, ajoute une entrée scellée et rend le travail à persister.
    `faits_de(sess, demande)` reconstruit les faits du geste (relecteur.faits_geste)."""
    from . import relecteur  # import local : le relecteur importe ce module
    with store.lock:
        inc = store.incidents.get(iid)
        sess = store.sessions.get(inc.session_id) if inc else None
        if sess is None:
            return None
        evs = relecteur._evenements(sess)
        rels = [e for e in relecteur._relectures(evs, "quatre_yeux")
                if (e.get("details") or {}).get("incident_id") == iid]
        if not rels:
            return None
        rel = rels[-1]
        suivi = relecteur.suivi_humain(rel, store.decisions)
        if suivi["etat"] not in ("confirme", "renverse", "tranche_par_analyste"):
            return None
        dec = next((d for d in reversed(store.decisions) if d.get("incident_id") == iid
                    and d.get("horodatage") == suivi["horodatage"] and d.get("sceau")), None)
        if dec is None or dec.get("action") not in ("accorder", "refuser"):
            return None
        if any((e.get("details") or {}).get("decision_sceau") == dec["sceau"] for e in evs if e.get("type") == "memoire"):
            return None  # déjà notée
        did = (rel.get("details") or {}).get("demande_id")
        demande = next((e for e, x in relecteur._demandes(evs) if x == did), None)
        if demande is None:
            return None
        faits = faits_de(sess, demande)
        motif = next((j.get("motif") for j in reversed(store._journal_console(iid, evs))
                      if j.get("acte") == "decision" and j.get("action") == dec["action"]), None)
        details = _entree(faits, "accorde" if dec["action"] == "accorder" else "refuse", dec.get("analyste"),
                          "analyste", dec.get("horodatage"), motif, incident_id=iid, decision_sceau=dec["sceau"],
                          relecteur=(rel.get("details") or {}).get("decision"),
                          renversement=suivi["etat"] == "renverse")
        if details is None:
            return None
        enreg = sceller(sess, "memoire", details)
        return {"evenements": [enreg], "sessions": [sess], "diffusions": [("memoire", details)]}


# ---------------------------------------------------------------- Lire les précédents
def _jours(date: str | None, maintenant: datetime) -> int | None:
    try:
        d = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(int((maintenant - (d if d.tzinfo else d.replace(tzinfo=timezone.utc))).total_seconds() // 86400), 0)


def precedents(faits: dict) -> list[dict]:
    """Les 3 à 5 décisions passées les plus proches : même type, même bénéficiaire ou domaine,
    montant proche d'abord. Appelé sous `store.lock`."""
    cle, rapprochement = cle_geste(faits)
    if cle is None:
        return []
    geste = faits.get("geste")
    taille = _ordre_de_grandeur(geste, faits.get("montant_eur"), faits.get("volume"))
    maintenant = datetime.now(timezone.utc)
    retenus = []
    for e in entrees():
        if e.get("geste") != geste or e.get("cle") != cle:
            continue
        og = e.get("ordre_de_grandeur")
        proche = (taille is not None and isinstance(og, (int, float)) and og > 0
                  and abs(taille - og) <= ECART_MONTANT * max(taille, og))
        retenus.append({
            "verdict": e.get("verdict"), "renversement": bool(e.get("renversement")),
            "relecteur_avait_dit": e.get("relecteur"), "jours": _jours(e.get("date"), maintenant),
            "date": e.get("date"), "analyste": e.get("analyste"), "rapprochement": rapprochement,
            "tranche": e.get("tranche"), "ordre_de_grandeur": og, "montant_proche": proche,
            # Même compte : le précédent et le geste portent le même IBAN. Un accord donné sans IBAN
            # ne vaut pour aucun compte.
            "meme_rib": e.get("rib") is not None and e.get("rib") == _rib(faits),
            "motif_analyste": e.get("motif_analyste"),
        })
    # Proches d'abord, puis les plus récents (la liste est déjà du plus récent au plus ancien).
    retenus.sort(key=lambda p: not p["montant_proche"])
    return retenus[:MAX_PRECEDENTS]


def pour_le_modele(precs: list[dict]) -> list[dict]:
    """Ce que le modèle lit d'un précédent : ni nom d'analyste, ni date exacte."""
    return [{k: p[k] for k in ("verdict", "renversement", "relecteur_avait_dit", "jours", "rapprochement",
                               "tranche", "montant_proche", "meme_rib", "motif_analyste")} for p in precs]


def avis(precs: list[dict]) -> dict | None:
    """Ce que la mémoire conseille aux règles : `retenir` (un refus humain proche, ou un renversement
    récent vers le refus), `accorder` (au moins un accord confirmé, montant proche, même RIB, aucun
    refus), ou None (rien d'utile)."""
    if not precs:
        return None
    recents = [p for p in precs if p["renversement"] and (p["jours"] or 0) <= RENVERSEMENT_RECENT_JOURS]
    if recents:  # un renversement récent pèse plus lourd que tout le reste
        return {"conseil": "retenir" if recents[0]["verdict"] == "refuse" else "accorder", "appui": [recents[0]],
                "renversement": True}
    refus = [p for p in precs if p["verdict"] == "refuse"]
    if refus:
        return {"conseil": "retenir", "appui": refus[:1], "renversement": False}
    accords = [p for p in precs if p["verdict"] == "accorde" and p["montant_proche"] and p["meme_rib"]]
    if accords:
        return {"conseil": "accorder", "appui": accords, "renversement": False}
    return None


def _nom_analyste(brut: str | None) -> str:
    morceaux = [m for m in re.split(r"[._\s-]+", str(brut or "")) if m]
    if not morceaux:
        return "un analyste"
    if len(morceaux) == 1:
        return morceaux[0].capitalize()
    return f"{morceaux[0].capitalize()} {morceaux[1][0].upper()}."


def _date_courte(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return "à une date inconnue"
    jour = "1er" if d.day == 1 else str(d.day)
    return f"le {jour} {_MOIS[d.month - 1]}"


def phrase(precs: list[dict], geste: str | None) -> str | None:
    """« Appuyé sur 3 décisions passées : accordé le 3 oct. par Claire D. (même fournisseur, 1 200 €) ; … »."""
    if not precs:
        return None
    morceaux = []
    for p in precs[:3]:
        og = p.get("ordre_de_grandeur")
        taille = (f"{og:,.0f}".replace(",", " ") + (" €" if geste == "virement" else " fiches")
                  if isinstance(og, (int, float)) else p.get("tranche") or "")
        verbe = "accordé" if p["verdict"] == "accorde" else "refusé"
        if p["renversement"]:
            verbe += " contre l'avis du relecteur"
        details = ", ".join(x for x in (p.get("rapprochement"), taille) if x)
        morceaux.append(f"{verbe} {_date_courte(p.get('date'))} par {_nom_analyste(p.get('analyste'))}"
                        + (f" ({details})" if details else ""))
    n = len(precs)
    return f"Appuyé sur {n} décision{'s' if n > 1 else ''} passée{'s' if n > 1 else ''} : " + " ; ".join(morceaux) + "."


def mesures(evenements: list[dict]) -> dict:
    with store.lock:
        valides = entrees()
    relectures = [e.get("details") or {} for e in evenements if e.get("type") == "relecture"]
    return {"entrees": len(valides), "renversements": sum(1 for e in valides if e.get("renversement")),
            "decisions_appuyees": sum(1 for d in relectures if d.get("appui_memoire"))}
