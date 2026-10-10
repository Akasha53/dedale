"""Journal scellé : chaînes de hachage SHA-256 sur le journal de Dédale.

Trois chaînes, toutes calculées par le backend au moment où il écrit :

- les événements, dans l'ordre de leur identifiant (une chaîne pour toute la base) ;
- les décisions des analystes, dans leur ordre d'arrivée (une chaîne pour toute la base) ;
- les maillons de la boîte noire, une chaîne par incident, qui part d'une genèse propre à
  l'incident et cite l'empreinte de l'événement d'où vient chaque maillon.

Empreinte d'un élément = SHA-256(empreinte précédente, horodatage, contenu canonique). Le
contenu canonique est un JSON aux clés triées, sans espace, accents gardés : la même forme en
mémoire et après un aller-retour par SQLite.

Le sceau d'un incident résume son en-tête (statut, analyste, décision), la tête de sa boîte
noire et les empreintes de ses décisions. Il est écrit avec l'incident et recalculé à la
vérification, qui lit la base et jamais la mémoire.

Limite : une chaîne de hachage montre qu'une donnée écrite a changé ou disparu. Quelqu'un qui
réécrit toute la base et recalcule chaque empreinte n'est repéré qu'en comparant à une copie
gardée ailleurs. ancrage.py s'en charge : signature Ed25519 de chaque entrée, déclencheurs
d'ajout seul, racines de Merkle publiées sur la C-Chain de test d'Avalanche.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

ALGORITHME = "SHA-256"
GENESE = "0" * 64

# Champs d'un événement couverts par son sceau : toutes les colonnes écrites par le backend.
CHAMPS_EVENEMENT = (
    "id", "horodatage", "recu_a", "source", "surface", "type", "session_id", "leurre_id",
    "leurre_nature", "ip", "user_agent", "methode", "chemin", "outil", "details",
)
CHAMPS_DECISION = ("incident_id", "action", "analyste", "horodatage")
CHAMPS_INCIDENT = (
    "id", "session_id", "type", "cree_a", "titre", "statut", "riposte_validee", "analyste",
    "decide_a", "action", "gravite", "resume",
)


# ---------------------------------------------------------------- Empreintes
def _convertir(v):
    if isinstance(v, set):
        return sorted(v)
    if isinstance(v, datetime):
        return v.isoformat()
    raise TypeError(f"Type non scellable : {type(v).__name__}")


def canonique(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=_convertir)


def empreinte(precedent: str, horodatage: str | None, contenu: Any) -> str:
    brut = f"{precedent}\n{horodatage or ''}\n{canonique(contenu)}"
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def genese_incident(iid: str) -> str:
    """Point de départ de la boîte noire d'un incident : deux incidents ne partagent rien."""
    return hashlib.sha256(f"dedale:boite-noire:{iid}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- Scellement (écriture)
def _contenu_evenement(ev: dict) -> dict:
    return {k: ev.get(k) for k in CHAMPS_EVENEMENT}


def _contenu_decision(d: dict) -> dict:
    return {k: d.get(k) for k in CHAMPS_DECISION}


def sceller_evenement(ev: dict, precedent: str) -> str:
    """Pose `sceau_precedent` et `sceau` sur l'événement, horodaté par sa réception, puis la
    signature Ed25519 de son émetteur (ancrage.py)."""
    from . import ancrage  # import tardif : ancrage lit ce module

    ev["sceau_precedent"] = precedent
    ev["sceau"] = empreinte(precedent, ev.get("recu_a"), _contenu_evenement(ev))
    ancrage.signer_entree(ev, "evenement")
    return ev["sceau"]


def sceller_decision(d: dict, precedent: str) -> str:
    from . import ancrage

    d["sceau_precedent"] = precedent
    d["sceau"] = empreinte(precedent, d.get("horodatage"), _contenu_decision(d))
    ancrage.signer_entree(d, "decision")  # signée par le backend, au nom de l'analyste
    return d["sceau"]


def _empreinte_maillon(maillon: dict, precedent: str, lien: str | None) -> str:
    contenu = {k: v for k, v in maillon.items() if k != "sceau"}
    return empreinte(precedent, maillon.get("horodatage"), {"maillon": contenu, "evenement": lien})


def sceller_chaine(iid: str, chaine: list[dict], evenements: dict) -> str:
    """Scelle les maillons dans l'ordre de la frise. Renvoie la tête de chaîne.

    La boîte noire se reconstruit à partir des événements : chaque reconstruction rescelle la
    frise entière. Chaque maillon cite le sceau de son événement source, ce qui rattache la
    boîte noire au journal des événements.
    """
    precedent = genese_incident(iid)
    for rang, maillon in enumerate(chaine, start=1):
        ev = evenements.get(maillon.get("evenement_id")) if maillon.get("evenement_id") is not None else None
        lien = ev.get("sceau") if ev else None
        maillon.pop("sceau", None)
        valeur = _empreinte_maillon(maillon, precedent, lien)
        maillon["sceau"] = {"rang": rang, "precedent": precedent, "evenement": lien, "empreinte": valeur}
        precedent = valeur
    return precedent


def entete_incident(inc) -> dict:
    """En-tête d'un incident sous une forme identique en mémoire (dataclass) et en base (ligne)."""
    lire = (lambda k: inc.get(k)) if isinstance(inc, dict) else (lambda k: getattr(inc, k, None))
    entete = {}
    for champ in CHAMPS_INCIDENT:
        v = lire(champ)
        if isinstance(v, datetime):
            v = v.isoformat()
        if champ == "riposte_validee":
            v = bool(v)
        entete[champ] = v
    return entete


def calculer_sceau_incident(inc, tete: str, sceaux_decisions: list[str]) -> str:
    return empreinte(tete, None, {"incident": entete_incident(inc), "decisions": list(sceaux_decisions)})


def sceller_incident(inc, decisions: list[dict], evenements: dict) -> str:
    """Rescelle la boîte noire de l'incident puis pose son sceau (`inc.sceau`)."""
    from . import ancrage

    tete = sceller_chaine(inc.id, inc.chaine, evenements)
    sceaux = [d["sceau"] for d in decisions if d.get("incident_id") == inc.id and d.get("sceau")]
    inc.sceau = calculer_sceau_incident(inc, tete, sceaux)
    ancrage.noter_statut(inc.id, inc.statut)  # un incident qui se clôt demande un ancrage
    return inc.sceau


def tete_journal(elements) -> str:
    """Dernier sceau posé dans une suite d'éléments, ou la genèse si rien n'est scellé."""
    for el in reversed(list(elements)):
        if el.get("sceau"):
            return el["sceau"]
    return GENESE


# ---------------------------------------------------------------- Empreintes par champ
# Le sceau dit qu'une entrée a changé ; il ne dit pas quel champ. À l'écriture, le backend
# range donc à côté une empreinte courte de chaque champ (table `empreintes_champs`, clé
# `evenement:<sceau>`, `decision:<sceau>`, `maillon:<empreinte>` ou `incident:<id>`). La
# vérification la compare aux valeurs relues pour nommer le champ modifié. Le sceau reste le
# seul juge : cette table sert au diagnostic, et quelqu'un qui la réécrit aussi obtient
# « contenu modifié » sans nom de champ.
SCHEMA_CHAMPS = "CREATE TABLE IF NOT EXISTS empreintes_champs (cle TEXT PRIMARY KEY, champs TEXT NOT NULL)"


def _empreinte_courte(valeur: Any) -> str:
    return hashlib.sha256(canonique(valeur).encode("utf-8")).hexdigest()[:16]


def empreintes_champs(contenu: dict) -> dict:
    """Empreinte courte de chaque champ ; un sous-champ s'écrit `details.motif`."""
    sortie = {}
    for cle, valeur in contenu.items():
        if isinstance(valeur, dict) and valeur:
            for sous, v in valeur.items():
                sortie[f"{cle}.{sous}"] = _empreinte_courte(v)
        else:
            sortie[cle] = _empreinte_courte(valeur)
    return sortie


def preparer(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_CHAMPS)


def ecrire_champs(conn: sqlite3.Connection, cle: str, contenu: dict, remplacer: bool = False) -> None:
    conn.execute(f"INSERT OR {'REPLACE' if remplacer else 'IGNORE'} INTO empreintes_champs (cle, champs) "
                 "VALUES (?, ?)", (cle, json.dumps(empreintes_champs(contenu), sort_keys=True)))


def contenu_maillon(maillon: dict) -> dict:
    return {k: v for k, v in maillon.items() if k != "sceau"}


def contenu_incident_ecrit(inc, sceau: str | None) -> dict:
    """Champs d'un incident en base : son en-tête et son sceau."""
    return {**entete_incident(inc), "sceau": sceau}


def contenu_decision_ecrite(d: dict, ident: int | None) -> dict:
    """Champs d'une décision en base : ceux du sceau, plus son identifiant, posé à l'écriture."""
    return {**_contenu_decision(d), "id": ident}


def champs_modifies(conn: sqlite3.Connection, cle: str | None, contenu: dict) -> list[str]:
    """Champs dont la valeur relue ne retombe plus sur l'empreinte gardée à l'écriture."""
    if not cle:
        return []
    try:
        row = conn.execute("SELECT champs FROM empreintes_champs WHERE cle = ?", (cle,)).fetchone()
    except sqlite3.OperationalError:  # base d'avant cette table
        return []
    if row is None:
        return []
    try:
        gardees = json.loads(row[0])
    except (TypeError, ValueError):
        return []
    actuelles = empreintes_champs(contenu)
    return sorted(k for k in set(gardees) | set(actuelles) if gardees.get(k) != actuelles.get(k))


def _cle_connue(conn: sqlite3.Connection, cle: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM empreintes_champs WHERE cle = ?", (cle,)).fetchone() is not None
    except sqlite3.OperationalError:
        return False


def _champs_entree(conn, prefixe: str, sceau: str | None, recalcule: str | None, contenu: dict) -> list[str]:
    """Champs modifiés d'un événement ou d'une décision. Contenu intact sous son ancienne
    empreinte (la clé `<prefixe>:<recalculé>` existe) : c'est la colonne `sceau` qui a bougé."""
    champs = champs_modifies(conn, f"{prefixe}:{sceau}", contenu) if sceau else []
    if not champs and recalcule and recalcule != sceau and _cle_connue(conn, f"{prefixe}:{recalcule}"):
        champs = ["sceau"]
    return champs


def _nommer(champs: list[str]) -> str:
    """« champ motif modifié », « champs analyste, horodatage modifiés » ; `details.` tombe."""
    noms = [c.removeprefix("details.") for c in champs]
    if not noms:
        return ""
    return f"champ {noms[0]} modifié" if len(noms) == 1 else f"champs {', '.join(noms)} modifiés"


# ---------------------------------------------------------------- Vérification (lecture)
def ouvrir_lecture(chemin) -> sqlite3.Connection:
    """Connexion en lecture seule : vérifier ne doit jamais écrire dans la base."""
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _colonnes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _ligne_evenement(row) -> dict:
    ev = dict(row)
    try:
        ev["details"] = json.loads(ev["details"]) if ev.get("details") is not None else None
    except (TypeError, json.JSONDecodeError):
        ev["details"] = {"__illisible__": ev["details"]}
    return ev


def _verifier_suite(conn, lignes: list[dict], contenu, horodatage: str, nom: str, cle_champs) -> dict:
    """Parcourt une suite scellée (événements ou décisions) dans l'ordre des identifiants.

    Les éléments sans sceau placés avant le premier sceau sont antérieurs au scellement. Un
    élément sans sceau placé après le premier sceau est une altération : le sceau a été retiré.
    `cle_champs(ligne)` rend (clé, contenu écrit) pour nommer le champ modifié.
    """
    precedent = GENESE
    commence = False
    anterieurs = verifies = 0
    for rang, ligne in enumerate(lignes, start=1):
        ident = ligne.get("id")
        if not ligne.get("sceau"):
            if commence:
                return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                        "anterieurs": anterieurs,
                        "raison": f"{nom} {ident} : sceau absent alors que le journal est scellé"}
            anterieurs += 1
            continue
        commence = True
        if ligne.get("sceau_precedent") != precedent:
            seul = empreinte(precedent, ligne.get(horodatage), contenu(ligne)) == ligne["sceau"]
            return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                    "anterieurs": anterieurs, "champs_modifies": ["sceau_precedent"] if seul else [],
                    "raison": f"{nom} {ident} : " + ("contenu modifié (champ sceau_precedent modifié)" if seul else
                                                     "chaîne rompue juste avant (élément supprimé, inséré ou déplacé)")}
        cle, ecrit = cle_champs(ligne)
        recalcule = empreinte(precedent, ligne.get(horodatage), contenu(ligne))
        if recalcule != ligne["sceau"]:
            champs = _champs_entree(conn, cle.split(":", 1)[0], ligne["sceau"], recalcule, ecrit)
            return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                    "anterieurs": anterieurs, "champs_modifies": champs,
                    "raison": f"{nom} {ident} : contenu modifié" + (f" ({_nommer(champs)})" if champs else "")}
        champs = champs_modifies(conn, cle, ecrit)  # un champ hors sceau (identifiant de décision)
        if champs:
            return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                    "anterieurs": anterieurs, "champs_modifies": champs,
                    "raison": f"{nom} {ident} : contenu modifié ({_nommer(champs)})"}
        precedent = ligne["sceau"]
        verifies += 1
    return {"intacte": True, "rang": None, "id": None, "verifies": verifies,
            "anterieurs": anterieurs, "raison": None, "tete": precedent}


def verifier_evenements(conn: sqlite3.Connection) -> dict:
    if "sceau" not in _colonnes(conn, "evenements"):
        lignes = [dict(r) for r in conn.execute("SELECT id FROM evenements ORDER BY id")]
        return {"intacte": True, "rang": None, "id": None, "verifies": 0,
                "anterieurs": len(lignes), "raison": None, "tete": GENESE}
    lignes = [_ligne_evenement(r) for r in conn.execute("SELECT * FROM evenements ORDER BY id")]
    return _verifier_suite(conn, lignes, _contenu_evenement, "recu_a", "événement",
                           lambda l: (f"evenement:{l['sceau']}", _contenu_evenement(l)))


def verifier_decisions(conn: sqlite3.Connection) -> dict:
    if "sceau" not in _colonnes(conn, "decisions"):
        lignes = [dict(r) for r in conn.execute("SELECT id FROM decisions ORDER BY id")]
        return {"intacte": True, "rang": None, "id": None, "verifies": 0,
                "anterieurs": len(lignes), "raison": None, "tete": GENESE}
    lignes = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id")]
    return _verifier_suite(conn, lignes, _contenu_decision, "horodatage", "décision",
                           lambda l: (f"decision:{l['sceau']}", contenu_decision_ecrite(l, l["id"])))


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resultat(iid: str, statut: str, verdict: str, **autres) -> dict:
    base = {
        "incident_id": iid,
        "statut": statut,
        "verdict": verdict,
        "etape_alteree": None,
        "element_altere": None,
        "raison": None,
        "champs_modifies": [],
        "maillons_verifies": 0,
        "evenements_anterieurs": 0,
        "decisions_verifiees": 0,
        "sceau": None,
        "sceau_recalcule": None,
        "algorithme": ALGORITHME,
        "verifie_a": _maintenant(),
    }
    base.update(autres)
    return base


def _alteree(iid: str, etape: int | None, element: str, raison: str, champs: list[str] | None = None,
             lieu: str | None = None, **autres) -> dict:
    """Verdict d'altération. `lieu` remplace le lieu par défaut (étape, décision, en-tête)."""
    if lieu is None:
        if element == "maillon" and etape is not None:
            lieu = f"altérée à l'étape {etape}"
        elif element == "decision" and etape is not None:
            lieu = f"altérée à la décision {etape}"
        else:
            lieu = "altérée : en-tête de l'incident"
    champs = champs or []
    sep = ", " if lieu.startswith("altérée :") else " : "
    verdict = f"{lieu}{sep}{_nommer(champs)}" if champs else lieu
    return _resultat(iid, "alteree", verdict, etape_alteree=etape, element_altere=element,
                     raison=raison, champs_modifies=champs, **autres)


def _lieu_hors_boite(ev: dict, numeros: dict) -> tuple[int | None, str]:
    """Lieu d'un événement du dossier qui n'est pas un maillon : acte de la console (motif,
    levée d'anonymat, remédiation), relecture, ou événement nommé par son identifiant."""
    type_ = ev.get("type")
    if type_ in ("console", "relecture"):
        n = numeros.get(ev["id"])
        if type_ == "console":
            return n, f"altérée à l'acte {n} du journal de la console"
        return n, f"altérée à la relecture {n}"
    return None, f"altérée à l'événement {ev['id']} ({type_})"


def verifier_incident(conn: sqlite3.Connection, iid: str) -> dict | None:
    """Recalcule depuis la base tout ce qui fait le dossier d'un incident.

    - la boîte noire, maillon par maillon, et l'événement source de chacun ;
    - chaque autre événement de sa session : actes de la console (motif d'une décision, levée
      d'anonymat, remédiation), relectures, correctifs. Chacun est recalculé et son lien avec
      ses voisins de la chaîne globale est contrôlé ; un événement que la session annonce et
      que la base n'a plus est une suppression ;
    - ses décisions, dans la chaîne globale des décisions, y compris une décision rattachée
      depuis à un autre incident ;
    - l'en-tête de l'incident.

    Renvoie None si l'incident n'est pas encore écrit. Le verdict vaut `intacte`,
    `altérée à l'étape N` (N compté à partir de 1 dans la frise), `altérée à l'acte N du
    journal de la console`, `altérée à la relecture N`, `altérée à la décision N`,
    `altérée : en-tête de l'incident` ou `antérieure au scellement`, suivi du champ modifié
    quand il se nomme (`altérée à la décision 1 : champ analyste modifié`).
    """
    cols_inc = _colonnes(conn, "incidents")
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (iid,)).fetchone()
    if row is None:
        if _cle_connue(conn, f"incident:{iid}"):  # il a été écrit : il a disparu depuis
            return _alteree(iid, None, "incident", "incident supprimé ou renuméroté en base", ["id"])
        return None
    inc = dict(row)
    sceau_stocke = inc.get("sceau") if "sceau" in cols_inc else None
    try:
        chaine = json.loads(inc.get("chaine") or "[]")
        if not isinstance(chaine, list):
            raise ValueError
    except (TypeError, ValueError):
        return _alteree(iid, 1, "maillon", "boîte noire illisible en base", sceau=sceau_stocke)

    scelles = [m for m in chaine if isinstance(m, dict) and isinstance(m.get("sceau"), dict)]
    if not scelles and not sceau_stocke:
        return _resultat(
            iid, "anterieure_au_scellement", "antérieure au scellement",
            raison="incident écrit avant la mise en place du scellement : rien à recalculer",
            evenements_anterieurs=len(chaine),
        )

    cols_ev = _colonnes(conn, "evenements")
    sceaux_ev = "sceau" in cols_ev

    def evenement(eid) -> dict | None:
        r = conn.execute("SELECT * FROM evenements WHERE id = ?", (eid,)).fetchone()
        return _ligne_evenement(r) if r is not None else None

    def sceau_avant(eid) -> str:
        r = conn.execute(
            "SELECT sceau FROM evenements WHERE id < ? ORDER BY id DESC LIMIT 1", (eid,)
        ).fetchone()
        return (r["sceau"] if r is not None and r["sceau"] else None) or GENESE

    def suivant(eid) -> dict | None:
        r = conn.execute("SELECT * FROM evenements WHERE id > ? ORDER BY id LIMIT 1", (eid,)).fetchone()
        return _ligne_evenement(r) if r is not None else None

    def champs_ev(ev: dict, sceau: str | None) -> list[str]:
        return champs_modifies(conn, f"evenement:{sceau}" if sceau else None, _contenu_evenement(ev))

    precedent = genese_incident(iid)
    anterieurs = 0
    ids_maillons: dict[int, int] = {}
    for rang, maillon in enumerate(chaine, start=1):
        sceau = maillon.get("sceau") if isinstance(maillon, dict) else None
        if not isinstance(sceau, dict):
            return _alteree(iid, rang, "maillon", "maillon sans sceau dans une boîte noire scellée",
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        lien = sceau.get("evenement")
        eid = maillon.get("evenement_id")
        if sceau.get("rang") != rang or sceau.get("precedent") != precedent:
            # Seul le sceau du maillon a bougé (rang ou précédent réécrits), ou la frise est rompue.
            champs = (["sceau.rang"] if sceau.get("precedent") == precedent
                      else ["sceau.precedent"] if _empreinte_maillon(maillon, precedent, lien) == sceau.get("empreinte")
                      else [])
            return _alteree(iid, rang, "maillon",
                            "contenu du maillon modifié" if champs else
                            "chaîne rompue : maillon supprimé, inséré ou déplacé", champs,
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        recalcule = _empreinte_maillon(maillon, precedent, lien)
        if recalcule != sceau.get("empreinte"):
            champs = champs_modifies(conn, f"maillon:{sceau.get('empreinte')}", contenu_maillon(maillon))
            if not champs and _cle_connue(conn, f"maillon:{recalcule}"):
                champs = ["sceau.empreinte"]
            elif not champs and eid is not None:
                source = evenement(eid)
                if source and _empreinte_maillon(maillon, precedent, source.get("sceau")) == sceau.get("empreinte"):
                    champs = ["sceau.evenement"]
            return _alteree(iid, rang, "maillon", "contenu du maillon modifié", champs,
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        if eid is not None:
            ids_maillons.setdefault(eid, rang)
            ev = evenement(eid)
            if lien is not None:
                if ev is None:
                    # Supprimé, ou déplacé sous un autre identifiant : le sceau cité le retrouve.
                    r = conn.execute("SELECT * FROM evenements WHERE sceau = ?", (lien,)).fetchone()
                    if r is not None:
                        deplace = _ligne_evenement(r)
                        return _alteree(iid, rang, "maillon",
                                        f"événement source {eid} renuméroté {deplace['id']} en base",
                                        champs_ev(deplace, lien) or ["id"],
                                        maillons_verifies=rang - 1, sceau=sceau_stocke)
                    return _alteree(iid, rang, "maillon", f"événement source {eid} supprimé",
                                    maillons_verifies=rang - 1, sceau=sceau_stocke)
                if (
                    ev.get("sceau") != lien
                    or ev.get("sceau_precedent") != sceau_avant(eid)
                    or empreinte(ev["sceau_precedent"], ev.get("recu_a"), _contenu_evenement(ev)) != lien
                ):
                    champs = champs_ev(ev, lien)
                    if not champs:
                        champs = (["sceau"] if ev.get("sceau") != lien
                                  else ["sceau_precedent"] if ev.get("sceau_precedent") != sceau_avant(eid) else [])
                    return _alteree(iid, rang, "maillon", f"événement source {eid} modifié en base", champs,
                                    maillons_verifies=rang - 1, sceau=sceau_stocke)
            elif ev is not None and sceaux_ev and ev.get("sceau"):
                return _alteree(iid, rang, "maillon",
                                f"lien vers l'événement source {eid} retiré du maillon",
                                maillons_verifies=rang - 1, sceau=sceau_stocke)
            else:
                anterieurs += 1
        precedent = sceau["empreinte"]

    # Tous les événements de la session, maillons compris : contenu, voisins dans la chaîne.
    evenements_verifies = 0
    if sceaux_ev:
        session_evs = [_ligne_evenement(r) for r in conn.execute(
            "SELECT * FROM evenements WHERE session_id = ? ORDER BY id", (inc.get("session_id"),))]
        numeros: dict[int, int] = {}
        compte = {"console": 0, "relecture": 0}
        for ev in session_evs:
            if ev.get("type") in compte:
                compte[ev["type"]] += 1
                numeros[ev["id"]] = compte[ev["type"]]
        for ev in session_evs:
            if ev["id"] in ids_maillons:
                etape, lieu, element = ids_maillons[ev["id"]], None, "maillon"
            else:
                (etape, lieu), element = _lieu_hors_boite(ev, numeros), "evenement"
            if not ev.get("sceau"):
                scelle_avant = conn.execute("SELECT 1 FROM evenements WHERE id < ? AND sceau IS NOT NULL LIMIT 1",
                                            (ev["id"],)).fetchone()
                if scelle_avant is not None:
                    return _alteree(iid, etape, element, f"événement {ev['id']} : sceau retiré", lieu=lieu,
                                    maillons_verifies=len(chaine), sceau=sceau_stocke)
                continue
            recalcule = empreinte(ev.get("sceau_precedent"), ev.get("recu_a"), _contenu_evenement(ev))
            if recalcule != ev["sceau"]:
                champs = _champs_entree(conn, "evenement", ev["sceau"], recalcule, _contenu_evenement(ev))
                if not champs and empreinte(sceau_avant(ev["id"]), ev.get("recu_a"),
                                            _contenu_evenement(ev)) == ev["sceau"]:
                    champs = ["sceau_precedent"]
                return _alteree(iid, etape, element, f"événement {ev['id']} modifié en base", champs,
                                lieu=lieu, maillons_verifies=len(chaine), sceau=sceau_stocke)
            if ev.get("sceau_precedent") != sceau_avant(ev["id"]):
                seul = empreinte(sceau_avant(ev["id"]), ev.get("recu_a"), _contenu_evenement(ev)) == ev["sceau"]
                return _alteree(iid, etape, element,
                                f"événement {ev['id']} modifié en base" if seul else
                                f"chaîne rompue avant l'événement {ev['id']} (événement supprimé, inséré ou déplacé)",
                                ["sceau_precedent"] if seul else None,
                                lieu=lieu, maillons_verifies=len(chaine), sceau=sceau_stocke)
            apres = suivant(ev["id"])
            if (apres is not None and apres.get("sceau") and apres.get("sceau_precedent") != ev["sceau"]
                    # Le suivant retombe juste sur ce sceau : seul son `sceau_precedent` a bougé,
                    # et c'est à lui d'en répondre (dans son dossier, ou ci-dessous s'il est d'ici).
                    and empreinte(ev["sceau"], apres.get("recu_a"), _contenu_evenement(apres)) != apres["sceau"]):
                return _alteree(iid, etape, element,
                                f"chaîne rompue après l'événement {ev['id']} (événement supprimé ou inséré)",
                                lieu=lieu, maillons_verifies=len(chaine), sceau=sceau_stocke)
            evenements_verifies += 1
        # Un événement que la session annonce et que la base n'a plus : supprimé.
        sess = conn.execute("SELECT etat_json FROM sessions WHERE id = ?", (inc.get("session_id"),)).fetchone() \
            if "etat_json" in _colonnes(conn, "sessions") else None
        try:
            annonces = (json.loads(sess["etat_json"]) or {}).get("evenement_ids", []) if sess and sess["etat_json"] else []
        except (TypeError, ValueError):
            annonces = []
        presents = {ev["id"] for ev in session_evs}
        manquant = next((i for i in annonces if i not in presents), None)
        if manquant is not None:
            return _alteree(iid, ids_maillons.get(manquant), "maillon" if manquant in ids_maillons else "evenement",
                            f"événement {manquant} supprimé de la base",
                            lieu=None if manquant in ids_maillons else f"altérée : événement {manquant} supprimé",
                            maillons_verifies=len(chaine), sceau=sceau_stocke)

    # Décisions de l'incident, chacune vérifiée dans la chaîne globale des décisions. Une
    # décision qui ne tombe plus juste et dont l'empreinte gardée dit qu'elle était à cet
    # incident compte pour lui : changer son `incident_id` ne la fait pas disparaître.
    cols_dec = _colonnes(conn, "decisions")
    decisions = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id")]
    sceaux_dec: list[str] = []
    numero = 0
    prec_dec = GENESE
    commence = False
    empreinte_iid = _empreinte_courte(iid)
    for d in decisions:
        sceau_d = d.get("sceau") if "sceau" in cols_dec else None
        if sceau_d is None and not commence:
            continue  # décision antérieure au scellement : hors du sceau de l'incident
        commence = True
        cle = f"decision:{sceau_d}" if sceau_d else None
        ecrit = contenu_decision_ecrite(d, d.get("id"))
        champs = champs_modifies(conn, cle, ecrit)
        a_lui = d.get("incident_id") == iid or ("incident_id" in champs and _champ_garde(
            conn, cle, "incident_id") == empreinte_iid)
        if a_lui:
            numero += 1
            if sceau_d is None:
                return _alteree(iid, numero, "decision", "décision sans sceau dans un journal scellé",
                                maillons_verifies=len(chaine), sceau=sceau_stocke)
            attendu = empreinte(prec_dec, d.get("horodatage"), _contenu_decision(d))
            if d.get("sceau_precedent") != prec_dec:
                seul = attendu == sceau_d
                return _alteree(iid, numero, "decision",
                                "décision modifiée en base" if seul else
                                "chaîne des décisions rompue juste avant (décision supprimée, insérée ou déplacée)",
                                ["sceau_precedent"] if seul else None,
                                maillons_verifies=len(chaine), sceau=sceau_stocke)
            if attendu != sceau_d or champs:
                if not champs and _cle_connue(conn, f"decision:{attendu}"):
                    champs = ["sceau"]
                return _alteree(iid, numero, "decision", "décision modifiée en base", champs,
                                maillons_verifies=len(chaine), sceau=sceau_stocke)
            sceaux_dec.append(sceau_d)
        if sceau_d:
            prec_dec = sceau_d

    recalcule = calculer_sceau_incident(inc, precedent, sceaux_dec)
    if recalcule != sceau_stocke:
        champs = champs_modifies(conn, f"incident:{iid}", contenu_incident_ecrit(inc, sceau_stocke))
        raison = ("en-tête modifié en base" if champs
                  else "sceau de l'incident modifié, ou décision retirée du dossier")
        return _alteree(iid, None, "incident", raison, champs,
                        maillons_verifies=len(chaine), decisions_verifiees=len(sceaux_dec),
                        evenements_anterieurs=anterieurs, sceau=sceau_stocke,
                        sceau_recalcule=recalcule)
    return _resultat(
        iid, "intacte", "intacte",
        maillons_verifies=len(chaine), decisions_verifiees=len(sceaux_dec),
        evenements_verifies=evenements_verifies,
        evenements_anterieurs=anterieurs, sceau=sceau_stocke, sceau_recalcule=recalcule,
        raison=(f"événements sources antérieurs au scellement : {anterieurs}" if anterieurs else None),
    )


def _champ_garde(conn: sqlite3.Connection, cle: str | None, champ: str) -> str | None:
    if not cle:
        return None
    try:
        row = conn.execute("SELECT champs FROM empreintes_champs WHERE cle = ?", (cle,)).fetchone()
        return json.loads(row[0]).get(champ) if row else None
    except (sqlite3.OperationalError, TypeError, ValueError):
        return None


def verifier_base(conn: sqlite3.Connection) -> dict:
    """Vérifie toute la base : chaîne des événements, chaîne des décisions, chaque incident."""
    evenements = verifier_evenements(conn)
    decisions = verifier_decisions(conn)
    incidents = []
    for (iid,) in conn.execute("SELECT id FROM incidents ORDER BY id").fetchall():
        incidents.append(verifier_incident(conn, iid))
    alteres = [i for i in incidents if i and i["statut"] == "alteree"]
    intacte = evenements["intacte"] and decisions["intacte"] and not alteres
    return {
        "statut": "intacte" if intacte else "alteree",
        "algorithme": ALGORITHME,
        "verifie_a": _maintenant(),
        "evenements": evenements,
        "decisions": decisions,
        "incidents": incidents,
        "incidents_alteres": [i["incident_id"] for i in alteres],
    }
