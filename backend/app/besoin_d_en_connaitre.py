"""Besoin d'en connaître : la console du SOC voit les menaces, pas les affaires de l'entreprise.

Ce que Dédale fait remonter porte des informations confidentielles : montants de virements,
bénéficiaires, IBAN, noms de clients. L'équipe sécurité n'en a pas besoin pour traiter une
menace, et ce n'est pas à elle de valider un virement : un geste retenu sans signal de fraude
est confirmé par le responsable du salarié ou par la finance, dans l'espace de validation
métier (`validation_metier.py`).

Pour la console du SOC (jeton analyste), les réponses de l'API qui portent un dossier
(`/api/incidents…`, `/api/sessions…`, `/api/activite`, `/api/relecteur/…`) et le flux `/ws`
passent par `minimiser` :

- un montant devient une tranche (« entre 10 et 50 k€ »), dans les champs chiffrés comme dans
  les textes ; le champ chiffré vaut `null` et `<champ>_tranche` porte la tranche ;
- un bénéficiaire (liste des connus, ou nommé dans un geste) devient « [bénéficiaire masqué] »,
  un IBAN « [IBAN masqué] », même déjà réduit à ses quatre derniers chiffres ;
- la partie `confidentiel` d'un acte de validation métier (nom du validateur, motif) disparaît.

Exception : un dossier qui porte un signal de fraude (mail jugé frauduleux ou douteux, consigne
cachée, RIB changé après un mail, piège touché par un agent…) se lit en clair, mais seulement
dans sa vue détaillée (`/api/incidents/{id}` et ses sous-routes, `/api/sessions/{id}`). La
réponse porte alors `confidentialite.niveau: "en_clair"` et la mention « Détail visible : signal
de fraude », et la consultation entre au journal scellé (événement `console`, acte
`consultation`), une fois par minute et par dossier au plus : la console relit le détail à
chaque changement. Les listes et le flux temps réel restent minimisés, même sur un dossier en
fraude.

Les seuils d'une règle du SOC (« plus de 10 000 € ») ne sont pas des données métier : un montant
précédé de « plus de », « au-dessus de », « plafond »… reste tel quel. Une erreur de lecture
laisse la réponse minimisée, jamais en clair.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

from . import auth, identites, montants, paiements
from .store import store

_journal = logging.getLogger(__name__)

MASQUE_BENEFICIAIRE = "[bénéficiaire masqué]"
MASQUE_IBAN = "[IBAN masqué]"
MENTION_CLAIR = "Détail visible : signal de fraude"
MENTION_MINIMISE = ("Montants en tranches, bénéficiaire et IBAN masqués. Le responsable du salarié ou "
                    "la finance voit le détail dans l'espace de validation.")
DELAI_CONSULTATION_S = 60.0
ANALYSTE_CONSULTATION = "console du SOC"

# Routes qui portent un dossier. Les règles, mesures, inventaires et leurres n'ont pas de donnée
# métier : leurs seuils et leurs compteurs restent tels quels.
PREFIXES = ("/api/incidents", "/api/sessions", "/api/activite", "/api/relecteur/")
_DETAIL_INCIDENT = re.compile(r"^/api/incidents/([A-Za-z0-9_-]{1,40})(?:/([a-z_-]{1,30}))?$")
# Sous-routes d'un dossier qui montrent son contenu : seules elles s'ouvrent en clair sur un signal
# de fraude, et seules elles comptent comme une consultation. La vérification du journal et le
# pré-tri ne montrent pas le dossier : ils restent minimisés, sans acte au journal.
_SOUS_ROUTES_EN_CLAIR = {None, "source", "synthese", "rapport", "export", "nis2", "decision"}
_DETAIL_SESSION = re.compile(r"^/api/sessions/([^/]{1,200})$")

# ------------------------------------------------------------------ tranches
_TRANCHES = ((1_000, "moins de 1 k€"), (10_000, "entre 1 et 10 k€"), (50_000, "entre 10 et 50 k€"),
             (100_000, "entre 50 et 100 k€"), (500_000, "entre 100 et 500 k€"),
             (1_000_000, "entre 500 k€ et 1 M€"))


def tranche(montant: Any) -> str | None:
    """« entre 10 et 50 k€ » pour 48 500 €. None si ce n'est pas un montant."""
    if not isinstance(montant, (int, float)) or isinstance(montant, bool) or montant < 0:
        return None
    for borne, libelle in _TRANCHES:
        if montant < borne:
            return libelle
    return "plus de 1 M€"


# ------------------------------------------------------------------ champs
_CLES_MONTANT = {"montant", "montant_eur", "montant_habituel", "montant_habituel_eur", "montant_max",
                 "montant_max_eur", "ordre_de_grandeur"}
_CLES_IBAN = {"iban", "iban_masque", "iban_fin", "rib_enregistre", "rib_demande"}
_CLES_BENEFICIAIRE = {"beneficiaire", "beneficiaire_nom"}
_CLES_RETIREES = {"confidentiel"}
# Clés de jointure, empreintes, horodatages et codes : jamais réécrits.
_CLES_INTACTES = identites._CLES_INTACTES | {
    "horodatage", "recu_a", "ouvert_le", "cree_a", "decide_a", "date", "signature", "decision_sceau",
    "sceau_incident", "type", "statut", "etat", "etape", "phase", "acte", "code", "source", "surface",
    "gravite", "classement", "leurre_id", "demande_id", "algorithme", "verdict", "decision", "action",
}

# ------------------------------------------------------------------ textes
_ESP = "[   ]"
_NOMBRE = r"(\d{1,3}(?:[   .,'’]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)"
_MULT = r"(k|mds?|mrd|mille|milliers?|millions?|milliards?|m)?"
_DEVISE_APRES = r"(€|eur(?:os?)?\b|\$|usd\b|dollars?\b|£|gbp\b|chf\b)"
_MONTANT_APRES = re.compile(r"(?<![\w.,'’])" + _NOMBRE + _ESP + "?" + _MULT + _ESP
                            + r"?(?:d['’]" + _ESP + r"?|de" + _ESP + r")?" + _DEVISE_APRES, re.IGNORECASE)
_MONTANT_AVANT = re.compile(r"(€|\$|£|\beur\b|\busd\b|\bgbp\b|\bchf\b)" + _ESP + "?" + _NOMBRE + _ESP
                            + r"?(k|mds?|m|millions?)?\b", re.IGNORECASE)
_MULTIPLICATEURS = {"k": 1e3, "mille": 1e3, "millier": 1e3, "milliers": 1e3, "m": 1e6, "million": 1e6,
                    "millions": 1e6, "md": 1e9, "mds": 1e9, "mrd": 1e9, "milliard": 1e9, "milliards": 1e9}
_SEUIL_AVANT = re.compile(r"(?:plus de|au[- ]dessus de|au[- ]del[àa] de|moins de|plafond(?: de)?|seuil(?: de)?|"
                          r"jusqu['’]à|maximum(?: de)?|max\.?|limite(?: de)?|[<>≤≥])" + _ESP + r"*$", re.IGNORECASE)
# IBAN en clair ou déjà réduit (« FR76 •••• •••• 6789 ») : en majuscules, pour ne jamais toucher
# une empreinte hexadécimale en minuscules.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[  ]?[A-Z0-9•]{4}){2,7}(?:[  ]?[A-Z0-9]{1,4})?\b")
_FIN_IBAN = re.compile(r"•{2,}[  ]?\d{4}\b")
_TERMINE_PAR = re.compile(r"((?:se termin\w*|finissant|termin\w*)\s+(?:par\s+)?)\d{4}\b", re.IGNORECASE)
_DEJA_MASQUE = re.compile(r"(\[[^\[\]]{0,80}\])")

_cache_noms: dict[str, Any] = {"version": None, "motif": None}


def _noms_metier() -> re.Pattern | None:
    """Bénéficiaires et clients à masquer : la liste des connus, plus tout nom cité comme
    bénéficiaire dans un geste ou un appel de paiement. Recalculé quand le journal grandit."""
    version = store.tete_evenements
    if _cache_noms["version"] == version:
        return _cache_noms["motif"]
    from . import relecteur  # import local : le relecteur importe le store

    noms: set[str] = set()
    for b in relecteur.beneficiaires():
        noms.update([b["nom"], str(b.get("id") or ""), *[str(a) for a in b.get("alias", [])]])
    for cle, b in paiements.BENEFICIAIRES.items():
        noms.update([cle, b.get("nom") or ""])
    with store.lock:
        for e in store.evenements.values():
            d = e.get("details") or {}
            for brut in (d.get("beneficiaire"), (d.get("virement") or {}).get("beneficiaire")
                         if isinstance(d.get("virement"), dict) else None):
                if isinstance(brut, str):
                    noms.add(brut)
            # « Virement de 48 500 € à Compta Express » : le nom écrit après « à », « au », « chez ».
            for brut in ((d.get("confidentiel") or {}).get("beneficiaire") if isinstance(d.get("confidentiel"), dict)
                         else None, d.get("beneficiaire_masque")):
                if isinstance(brut, str) and not brut.endswith("caractères)"):
                    noms.add(brut)
            if e.get("type") == "validation_demandee" and isinstance(d.get("texte"), str):
                noms.update(nom_dans_texte(d["texte"]) or [])
            if d.get("geste") == "virement" and isinstance(d.get("message"), str):
                for m in relecteur._RE_NOM.finditer(relecteur.texte_lisible(d["message"])):
                    noms.add(re.sub(r"(?:\s+(?:du|de|des|la|le|et|&))+$", "", m.group(1)).strip())
    motifs = []
    for nom in sorted({n.strip() for n in noms if isinstance(n, str)}, key=len, reverse=True):
        morceaux = [m for m in re.split(r"[\s\-]+", nom) if m]
        if len("".join(morceaux)) < 4 or nom.lower() in {"orbis pay", "orbispay", "fournisseur", "client"}:
            continue
        motifs.append(r"[\s\-]+".join(re.escape(m) for m in morceaux))
    motif = re.compile(r"(?<![\w])(?:" + "|".join(motifs) + r")(?![\w])", re.IGNORECASE) if motifs else None
    _cache_noms.update(version=version, motif=motif)
    return motif


def nom_dans_texte(texte: str) -> list[str]:
    """Noms écrits après « à », « au », « chez », « pour » : « à Compta Express »."""
    from . import relecteur

    sortie = []
    for m in relecteur._RE_NOM.finditer(relecteur.texte_lisible(texte)):
        nom = re.sub(r"(?:\s+(?:du|de|des|la|le|et|&))+$", "", m.group(1)).strip()
        if len(nom) >= 3:
            sortie.append(nom)
    return sortie


def _phrase(raison: str) -> str:
    raison = raison.strip()
    raison = raison[:1].upper() + raison[1:]
    return raison if raison.endswith((".", "!", "?")) else raison + "."


def _valeur(nombre_brut: str, mult: str | None) -> float | None:
    valeur = montants.nombre(re.sub(r"[  ]", " ", nombre_brut), multiplicateur=bool(mult))
    if valeur is None:
        return None
    return valeur * _MULTIPLICATEURS.get((mult or "").lower(), 1)


def _masquer_montants(texte: str) -> str:
    def remplacer(m: re.Match, groupe_nombre: int, groupe_mult: int) -> str:
        if _SEUIL_AVANT.search(texte[max(0, m.start() - 30):m.start()]):
            return m.group(0)  # seuil d'une règle, pas une donnée métier
        t = tranche(_valeur(m.group(groupe_nombre), m.group(groupe_mult)))
        return f"[{t}]" if t else "[montant masqué]"

    texte = _MONTANT_APRES.sub(lambda m: remplacer(m, 1, 2), texte)
    return _MONTANT_AVANT.sub(lambda m: remplacer(m, 2, 3), texte)


def masquer_texte(texte: str, noms: re.Pattern | None = None) -> str:
    """Le texte sans montant exact, sans IBAN et sans nom de bénéficiaire ou de client.
    Idempotent : ce qui est déjà entre crochets n'est pas relu."""
    if not texte or not any(c.isdigit() for c in texte) and noms is None:
        return texte
    morceaux = _DEJA_MASQUE.split(texte)
    for i, morceau in enumerate(morceaux):
        if i % 2 == 1 or not morceau:
            continue
        m = _IBAN.sub(MASQUE_IBAN, morceau)
        m = _FIN_IBAN.sub("••••", m)
        m = _TERMINE_PAR.sub(lambda x: x.group(1) + "••••", m)
        if noms is not None:
            m = noms.sub(MASQUE_BENEFICIAIRE, m)
        # Les crochets posés ci-dessus protègent l'IBAN et le nom de la lecture des montants.
        morceaux[i] = "".join(_masquer_montants(p) if j % 2 == 0 else p
                              for j, p in enumerate(_DEJA_MASQUE.split(m)))
    return "".join(morceaux)


# ------------------------------------------------------------------ objets
# Actes de l'espace de validation métier : la SOC n'en garde que le sens, sans montant, bénéficiaire,
# texte du salarié, nom du validateur ni motif.
ACTES_METIER = {"validation_demandee", "validation_decidee"}
MENTION_METIER = "Réglé avec le responsable du salarié ou la finance. Détail réservé à la validation métier."


def acte_metier_reduit(details: dict) -> dict:
    sens = {"validation_demandee": "demandée", "validation_decidee": {"accorde": "confirmé par le responsable",
                                                                      "refuse": "refusé par le responsable"}}
    acte = details.get("acte")
    issue = sens.get(acte)
    if isinstance(issue, dict):
        issue = issue.get(details.get("verdict"), "tranché par le responsable")
    return {"acte": acte, "demande_id": details.get("demande_id"), "statut": details.get("statut"),
            "verdict": details.get("verdict"), "validation_metier": issue, "message": MENTION_METIER}


def minimiser(objet: Any, noms: re.Pattern | None = None, _cle: str | None = None,
              _beneficiaire: bool = False) -> Any:
    """Copie de l'objet telle que la console du SOC peut la lire (voir le docstring du module)."""
    if noms is None and _cle is None:
        noms = _noms_metier()
    if isinstance(objet, dict):
        if isinstance(objet.get("type"), str) and objet["type"] in ACTES_METIER and isinstance(objet.get("details"), dict):
            objet = {**objet, "details": acte_metier_reduit(objet["details"])}
        sortie: dict = {}
        for cle, valeur in objet.items():
            if cle in _CLES_RETIREES:
                continue
            if cle in _CLES_INTACTES or cle.endswith("tranche") or cle.endswith("_id"):
                sortie[cle] = valeur
            elif cle in _CLES_MONTANT and isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
                sortie[cle] = None
                sortie.setdefault(f"{cle}_tranche", tranche(valeur))
            elif cle in _CLES_IBAN and isinstance(valeur, str) and valeur:
                sortie[cle] = MASQUE_IBAN
            elif (cle in _CLES_BENEFICIAIRE or (_beneficiaire and cle == "nom")) and isinstance(valeur, str) and valeur:
                sortie[cle] = MASQUE_BENEFICIAIRE
            else:
                sortie[cle] = minimiser(valeur, noms, cle, _beneficiaire or cle in _CLES_BENEFICIAIRE)
        return sortie
    if isinstance(objet, list):
        return [minimiser(v, noms, _cle or "", _beneficiaire) for v in objet]
    if isinstance(objet, str):
        return masquer_texte(objet, noms)
    return objet


# ------------------------------------------------------------------ signal de fraude
_TYPES_ATTAQUE_AGENT = {"interne_canari", "interne_outil_mcp", "interne_inter_agent", "interne_memoire",
                        "interne_desarme", "externe_agent_ia"}
_cache_signal: dict[str, tuple[Any, str | None]] = {}


def _signal_humain(sess, evs: list[dict]) -> str | None:
    from . import relecteur

    for e in evs:
        d = e.get("details") or {}
        if e.get("type") != "avertissement" or d.get("quatre_yeux") != "demande":
            continue
        faits = relecteur.faits_geste(sess, e)
        signaux = getattr(relecteur, "signaux_geste", None)
        if callable(signaux):
            fraude = [s for s in signaux(faits) if isinstance(s, dict) and s.get("fraude")]
            if fraude:
                return str(fraude[0].get("raison") or fraude[0].get("code") or "signal de fraude")
            continue
        # Repli tant que le relecteur ne classe pas ses signaux.
        mail = faits.get("mail") or {}
        b = faits.get("beneficiaire") or {}
        if mail.get("verdict") == "frauduleux":
            return "le geste suit un mail jugé frauduleux"
        if mail.get("verdict") == "suspect":
            return "le geste suit un mail douteux"
        if faits.get("consigne_retiree"):
            return "consigne cachée dans le message"
        if b.get("rib") == "nouveau" and mail:
            return "RIB changé après un mail"
        if (faits.get("destination") or {}).get("personnelle"):
            return "destination personnelle"
    verdict = relecteur._verdict_mail(evs)
    if verdict and verdict.get("verdict") == "frauduleux":
        return "mail jugé frauduleux"
    if verdict and verdict.get("verdict") == "suspect":
        return "mail jugé douteux"
    if any(e.get("type") == "desarmement" for e in evs):
        return "consigne cachée retirée avant lecture"
    return None


def signal_fraude(session_id: str) -> str | None:
    """Raison en français si le dossier de cette session porte un signal de fraude, sinon None.
    Une erreur vaut None : on minimise plutôt que d'ouvrir. Sous verrou."""
    sess = store.sessions.get(session_id)
    if sess is None:
        return None
    version = (store.tete_evenements, store.tete_decisions, len(sess.evenement_ids))
    deja = _cache_signal.get(session_id)
    if deja is not None and deja[0] == version:
        return deja[1]
    raison = None
    try:
        evs = [store.evenements[i] for i in sess.evenement_ids if i in store.evenements]
        if sess.source in ("humain", "physique"):
            raison = _signal_humain(sess, evs)
        else:
            inc = next((i for i in store.incidents.values() if i.session_id == sess.id), None)
            if any(l.startswith("C-") for l in sess.leurres_touches):
                raison = "piège touché par l'agent : il a suivi une consigne cachée"
            elif any(e.get("type") == "desarmement" for e in evs):
                raison = "consigne cachée retirée avant lecture"
            elif inc is not None and inc.type in _TYPES_ATTAQUE_AGENT:
                raison = "attaque par injection sur l'agent"
    except Exception:  # fermer plutôt qu'ouvrir
        _journal.exception("Besoin d'en connaître : signal de fraude illisible pour %s", session_id)
        raison = None
    _cache_signal[session_id] = (version, raison)
    return raison


# ------------------------------------------------------------------ détail d'un geste en fraude
def detail_confidentiel(faits: dict, details: dict) -> dict:
    """Ce que la SOC lira en clair si le dossier porte un signal de fraude : montant exact,
    bénéficiaire, quatre derniers chiffres de l'IBAN. Posé par le relecteur sur l'événement du
    geste, sous `confidentiel` ; `minimiser` le retire de toute autre vue."""
    from . import relecteur

    b = faits.get("beneficiaire") or {}
    nom = b.get("nom") if b.get("connu") else (relecteur.texte_lisible(details.get("beneficiaire"))[:80] or None)
    if nom is None and faits.get("geste") == "virement":
        m = relecteur._RE_NOM.search(relecteur.texte_lisible(details.get("message")))
        nom = re.sub(r"(?:\s+(?:du|de|des|la|le|et|&))+$", "", m.group(1)).strip() if m else None
    fin = re.sub(r"\D", "", str(b.get("rib_demande") or ""))[-4:]
    return {"geste": faits.get("geste"), "montant_eur": faits.get("montant_eur"), "beneficiaire": nom,
            "iban": f"•••• {fin}" if len(fin) == 4 else None, "volume": faits.get("volume"),
            "destination": (faits.get("destination") or {}).get("domaine")}


def _detail_du_dossier(iid: str) -> dict | None:
    """Le détail confidentiel d'un dossier : celui posé par le relecteur, ou le virement d'un agent."""
    inc = store.incidents.get(iid)
    sess = store.sessions.get(inc.session_id) if inc else None
    if sess is None:
        return None
    for i in reversed(sess.evenement_ids):
        d = (store.evenements.get(i) or {}).get("details") or {}
        if isinstance(d.get("confidentiel"), dict) and d.get("quatre_yeux") == "demande":
            return d["confidentiel"]
        v = d.get("virement")
        if isinstance(v, dict) and isinstance(v.get("montant"), (int, float)):
            return {"geste": "virement", "montant_eur": v.get("montant"), "beneficiaire": v.get("beneficiaire"),
                    "iban": v.get("iban_masque"), "volume": None, "destination": None}
    return None


# ------------------------------------------------------------------ consultations journalisées
persister: Callable[[dict], None] = lambda job: None
_dernieres_consultations: dict[str, float] = {}


def vider() -> None:
    """Remise à zéro pour les tests."""
    _dernieres_consultations.clear()
    _cache_signal.clear()
    _cache_noms.update(version=None, motif=None)


def journaliser_consultation(iid: str, raison: str, chemin: str) -> dict | None:
    """Acte `consultation` scellé : la console a lu en clair le détail d'un dossier en fraude."""
    maintenant = time.monotonic()
    with store.lock:
        derniere = _dernieres_consultations.get(iid)
        if derniere is not None and maintenant - derniere < DELAI_CONSULTATION_S:
            return None
        inc = store.incidents.get(iid)
        sess = store.sessions.get(inc.session_id) if inc else None
        if inc is None or sess is None:
            return None
        note = store._note_console(inc, sess, "consultation", ANALYSTE_CONSULTATION,
                                   {"motif": f"{MENTION_CLAIR}. {_phrase(raison[:160])}", "message": chemin[:120]})
        _dernieres_consultations[iid] = maintenant
    # L'acte, sa session et son incident : une seule transaction, comme les autres actes.
    persister({"evenements": [note], "sessions": [sess], "incidents": [inc]})
    return note


def _cible_detail(chemin: str) -> str | None:
    """Incident dont cette route montre le contenu, ou None (liste, vérification, pré-tri)."""
    m = _DETAIL_INCIDENT.match(chemin)
    if m:
        return m.group(1) if m.group(2) in _SOUS_ROUTES_EN_CLAIR else None
    m = _DETAIL_SESSION.match(chemin)
    if m:
        with store.lock:
            return next((i.id for i in store.incidents.values() if i.session_id == m.group(1)), None)
    return None


def preparer_reponse(chemin: str, methode: str, corps: Any) -> Any:
    """Ce que la console du SOC reçoit pour cette route. JSON déjà décodé.

    Un dossier sans donnée métier (un piège touché par un agent qui ne paie rien, par exemple)
    sort tel quel : il n'y a rien à ouvrir, donc ni mention ni consultation au journal."""
    sortie = minimiser(corps)
    iid = _cible_detail(chemin)
    if iid is None or sortie == corps:
        return sortie
    with store.lock:
        inc = store.incidents.get(iid)
        raison = signal_fraude(inc.session_id) if inc else None
        detail = _detail_du_dossier(iid) if raison else None
    if raison:
        journaliser_consultation(iid, raison, f"{methode} {chemin}")
        if isinstance(corps, dict):
            corps = {**corps, "confidentialite": {
                "niveau": "en_clair", "signal_fraude": raison, "detail": detail,
                "mention": f"{MENTION_CLAIR}. {_phrase(raison)} Cette consultation est notée au journal scellé."}}
        return corps
    if isinstance(sortie, dict):
        sortie["confidentialite"] = {"niveau": "minimise", "signal_fraude": None, "mention": MENTION_MINIMISE}
    return sortie


# ------------------------------------------------------------------ branchement ASGI et WS
_TYPES_TEXTE = ("text/html", "text/plain", "application/x-yaml", "text/yaml")


class Minimiseur:
    """Middleware ASGI : réécrit les réponses 2xx des routes de dossier, pour le jeton analyste
    seulement. Les autres identités, les autres routes et le WS passent sans changement."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        chemin = scope.get("path") or ""
        if scope.get("type") != "http" or not chemin.startswith(PREFIXES):
            await self.app(scope, receive, send)
            return
        if auth.identifier(auth._entete(scope, "authorization")) != "analyste":
            await self.app(scope, receive, send)
            return
        debut: dict = {}
        morceaux: list[bytes] = []

        async def capter(message):
            if message["type"] == "http.response.start":
                debut.update(message)
                return
            if message["type"] == "http.response.body":
                morceaux.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                corps = b"".join(morceaux)
                try:
                    corps = self._reecrire(scope, debut, corps)
                except Exception:
                    # Rien ne sort en clair par accident : une réponse illisible est retenue.
                    _journal.exception("Besoin d'en connaître : réponse retenue pour %s", chemin)
                    debut["status"] = 500
                    debut["headers"] = [(b"content-type", b"application/json")]
                    corps = json.dumps({"detail": "Réponse retenue : la minimisation a échoué."},
                                       ensure_ascii=False).encode("utf-8")
                await _emettre(send, debut, corps)
                return
            await send(message)

        await self.app(scope, receive, capter)

    @staticmethod
    def _reecrire(scope, debut: dict, corps: bytes) -> bytes:
        statut = debut.get("status", 200)
        if not 200 <= statut < 300 or not corps:
            return corps
        entetes = {k.lower(): v for k, v in debut.get("headers") or []}
        type_ = entetes.get(b"content-type", b"").decode("latin-1").lower()
        chemin, methode = scope.get("path") or "", scope.get("method", "GET")
        if "json" in type_:
            donnees = json.loads(corps)
            return json.dumps(preparer_reponse(chemin, methode, donnees), ensure_ascii=False).encode("utf-8")
        if type_.startswith(_TYPES_TEXTE):
            texte = corps.decode("utf-8")
            masque = masquer_texte(texte, _noms_metier())
            iid = _cible_detail(chemin)
            if iid is None or masque == texte:
                return masque.encode("utf-8")
            with store.lock:
                inc = store.incidents.get(iid)
                raison = signal_fraude(inc.session_id) if inc else None
            if raison:
                journaliser_consultation(iid, raison, f"{methode} {chemin}")
                return corps
            return masque.encode("utf-8")
        return corps


async def _emettre(send, debut: dict, corps: bytes) -> None:
    entetes = [(k, v) for k, v in debut.get("headers") or [] if k.lower() != b"content-length"]
    entetes.append((b"content-length", str(len(corps)).encode()))
    await send({**debut, "headers": entetes})
    await send({"type": "http.response.body", "body": corps})


# Messages du flux sans donnée métier : règles du SOC, mesures, inventaire, leurres, ancrage.
_WS_SANS_DONNEE_METIER = {"politique", "politiques", "mesures", "leurre", "leurres", "agents", "inventaire",
                          "ancrage", "sante"}


def filtre_ws(type_: str, donnees: Any) -> Any:
    """Le flux /ws n'est servi qu'à l'analyste : toujours minimisé, même sur un dossier en fraude
    (la consultation en clair passe par la vue détaillée, journalisée)."""
    if type_ in _WS_SANS_DONNEE_METIER:
        return donnees
    if type_ == "validation" and isinstance(donnees, dict):
        return acte_metier_reduit(donnees)
    try:
        return minimiser(donnees)
    except Exception:
        _journal.exception("Besoin d'en connaître : message WS %s retenu", type_)
        return {"retenu": True}
