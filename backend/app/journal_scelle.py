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
réécrit toute la base et recalcule chaque empreinte n'est repéré qu'en comparant le sceau à
une copie gardée ailleurs, par exemple celle du rapport d'incident ou de l'alerte.
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
    """Pose `sceau_precedent` et `sceau` sur l'événement, horodaté par sa réception."""
    ev["sceau_precedent"] = precedent
    ev["sceau"] = empreinte(precedent, ev.get("recu_a"), _contenu_evenement(ev))
    return ev["sceau"]


def sceller_decision(d: dict, precedent: str) -> str:
    d["sceau_precedent"] = precedent
    d["sceau"] = empreinte(precedent, d.get("horodatage"), _contenu_decision(d))
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
    tete = sceller_chaine(inc.id, inc.chaine, evenements)
    sceaux = [d["sceau"] for d in decisions if d.get("incident_id") == inc.id and d.get("sceau")]
    inc.sceau = calculer_sceau_incident(inc, tete, sceaux)
    return inc.sceau


def tete_journal(elements) -> str:
    """Dernier sceau posé dans une suite d'éléments, ou la genèse si rien n'est scellé."""
    for el in reversed(list(elements)):
        if el.get("sceau"):
            return el["sceau"]
    return GENESE


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


def _verifier_suite(lignes: list[dict], contenu, horodatage: str, nom: str) -> dict:
    """Parcourt une suite scellée (événements ou décisions) dans l'ordre des identifiants.

    Les éléments sans sceau placés avant le premier sceau sont antérieurs au scellement. Un
    élément sans sceau placé après le premier sceau est une altération : le sceau a été retiré.
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
            return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                    "anterieurs": anterieurs,
                    "raison": f"{nom} {ident} : chaîne rompue juste avant (élément supprimé, inséré ou déplacé)"}
        if empreinte(precedent, ligne.get(horodatage), contenu(ligne)) != ligne["sceau"]:
            return {"intacte": False, "rang": rang, "id": ident, "verifies": verifies,
                    "anterieurs": anterieurs, "raison": f"{nom} {ident} : contenu modifié"}
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
    return _verifier_suite(lignes, _contenu_evenement, "recu_a", "événement")


def verifier_decisions(conn: sqlite3.Connection) -> dict:
    if "sceau" not in _colonnes(conn, "decisions"):
        lignes = [dict(r) for r in conn.execute("SELECT id FROM decisions ORDER BY id")]
        return {"intacte": True, "rang": None, "id": None, "verifies": 0,
                "anterieurs": len(lignes), "raison": None, "tete": GENESE}
    lignes = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id")]
    return _verifier_suite(lignes, _contenu_decision, "horodatage", "décision")


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


def _alteree(iid: str, etape: int | None, element: str, raison: str, **autres) -> dict:
    if element == "maillon" and etape is not None:
        verdict = f"altérée à l'étape {etape}"
    elif element == "decision" and etape is not None:
        verdict = f"altérée à la décision {etape}"
    else:
        verdict = "altérée : en-tête de l'incident"
    return _resultat(iid, "alteree", verdict, etape_alteree=etape, element_altere=element,
                     raison=raison, **autres)


def verifier_incident(conn: sqlite3.Connection, iid: str) -> dict | None:
    """Recalcule depuis la base la boîte noire d'un incident, ses événements et ses décisions.

    Renvoie None si l'incident n'est pas encore écrit. Le verdict vaut `intacte`,
    `altérée à l'étape N` (N compté à partir de 1 dans la frise), `altérée à la décision N`,
    `altérée : en-tête de l'incident` ou `antérieure au scellement`.
    """
    cols_inc = _colonnes(conn, "incidents")
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (iid,)).fetchone()
    if row is None:
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

    precedent = genese_incident(iid)
    anterieurs = 0
    for rang, maillon in enumerate(chaine, start=1):
        sceau = maillon.get("sceau") if isinstance(maillon, dict) else None
        if not isinstance(sceau, dict):
            return _alteree(iid, rang, "maillon", "maillon sans sceau dans une boîte noire scellée",
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        if sceau.get("rang") != rang or sceau.get("precedent") != precedent:
            return _alteree(iid, rang, "maillon",
                            "chaîne rompue : maillon supprimé, inséré ou déplacé",
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        lien = sceau.get("evenement")
        if _empreinte_maillon(maillon, precedent, lien) != sceau.get("empreinte"):
            return _alteree(iid, rang, "maillon", "contenu du maillon modifié",
                            maillons_verifies=rang - 1, sceau=sceau_stocke)
        eid = maillon.get("evenement_id")
        if eid is not None:
            ev = evenement(eid)
            if lien is not None:
                if ev is None:
                    return _alteree(iid, rang, "maillon", f"événement source {eid} supprimé",
                                    maillons_verifies=rang - 1, sceau=sceau_stocke)
                if (
                    ev.get("sceau") != lien
                    or ev.get("sceau_precedent") != sceau_avant(eid)
                    or empreinte(ev["sceau_precedent"], ev.get("recu_a"), _contenu_evenement(ev)) != lien
                ):
                    return _alteree(iid, rang, "maillon", f"événement source {eid} modifié en base",
                                    maillons_verifies=rang - 1, sceau=sceau_stocke)
            elif ev is not None and sceaux_ev and ev.get("sceau"):
                return _alteree(iid, rang, "maillon",
                                f"lien vers l'événement source {eid} retiré du maillon",
                                maillons_verifies=rang - 1, sceau=sceau_stocke)
            else:
                anterieurs += 1
        precedent = sceau["empreinte"]

    # Décisions de l'incident, chacune vérifiée dans la chaîne globale des décisions.
    cols_dec = _colonnes(conn, "decisions")
    decisions = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id")]
    sceaux_dec: list[str] = []
    numero = 0
    prec_dec = GENESE
    commence = False
    for d in decisions:
        sceau_d = d.get("sceau") if "sceau" in cols_dec else None
        if sceau_d is None and not commence:
            continue  # décision antérieure au scellement : hors du sceau de l'incident
        commence = True
        if d.get("incident_id") == iid:
            numero += 1
            if sceau_d is None or d.get("sceau_precedent") != prec_dec or empreinte(
                prec_dec, d.get("horodatage"), _contenu_decision(d)
            ) != sceau_d:
                return _alteree(iid, numero, "decision",
                                "décision modifiée, supprimée ou sans sceau",
                                maillons_verifies=len(chaine), sceau=sceau_stocke)
            sceaux_dec.append(sceau_d)
        if sceau_d:
            prec_dec = sceau_d

    recalcule = calculer_sceau_incident(inc, precedent, sceaux_dec)
    if recalcule != sceau_stocke:
        return _alteree(iid, None, "incident",
                        "en-tête modifié en base (statut, analyste, décision ou titre)",
                        maillons_verifies=len(chaine), decisions_verifiees=len(sceaux_dec),
                        evenements_anterieurs=anterieurs, sceau=sceau_stocke,
                        sceau_recalcule=recalcule)
    return _resultat(
        iid, "intacte", "intacte",
        maillons_verifies=len(chaine), decisions_verifiees=len(sceaux_dec),
        evenements_anterieurs=anterieurs, sceau=sceau_stocke, sceau_recalcule=recalcule,
        raison=(f"événements sources antérieurs au scellement : {anterieurs}" if anterieurs else None),
    )


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
