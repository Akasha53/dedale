"""Persistance SQLite (WAL) alimentée par un unique écrivain en tâche de fond.

Schéma : cinq tables — evenements, sessions, leurres, incidents, decisions.
Un seul writer (la boucle de fond) écrit : pas de contention d'écriture concurrente.
Les lectures live de l'API passent par le Store en mémoire, pas par SQLite.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime

from . import config, journal_scelle

_SCHEMA = """
CREATE TABLE IF NOT EXISTS evenements (
  id INTEGER PRIMARY KEY, horodatage TEXT, recu_a TEXT, source TEXT, surface TEXT,
  type TEXT, session_id TEXT, leurre_id TEXT, ip TEXT, user_agent TEXT,
  methode TEXT, chemin TEXT, outil TEXT, details TEXT
);
CREATE INDEX IF NOT EXISTS idx_ev_session ON evenements(session_id);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, source TEXT, premier_vu TEXT, dernier_vu TEXT, etat TEXT,
  classement TEXT, score REAL, signaux TEXT, leurres_touches TEXT,
  verite_terrain TEXT, detecte_a TEXT, confine_a TEXT, n_evenements INTEGER
);
CREATE TABLE IF NOT EXISTS leurres (
  id TEXT PRIMARY KEY, source TEXT, surface TEXT, nature TEXT, emplacement TEXT,
  description TEXT, risques TEXT, techniques TEXT, humain_visible INTEGER,
  touches INTEGER, premier_touche TEXT, dernier_touche TEXT
);
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY, session_id TEXT, type TEXT, cree_a TEXT, titre TEXT,
  statut TEXT, riposte_validee INTEGER, analyste TEXT, decide_a TEXT, action TEXT, chaine TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, action TEXT, analyste TEXT, horodatage TEXT
);
"""


def ouvrir() -> sqlite3.Connection:
    config.assurer_dossiers()
    conn = sqlite3.connect(str(config.CHEMIN_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    # Ajouts compatibles avec les bases créées avant le rechargement au démarrage.
    for table, colonnes in {
        "sessions": {"etat_json": "TEXT"},
        "evenements": {"leurre_nature": "TEXT", "sceau_precedent": "TEXT", "sceau": "TEXT",
                       "signataire": "TEXT", "signature": "TEXT"},
        "incidents": {"gravite": "TEXT", "resume": "TEXT", "sceau": "TEXT"},
        # Journal scellé (journal_scelle.py) : NULL pour les lignes antérieures au scellement.
        "decisions": {"sceau_precedent": "TEXT", "sceau": "TEXT", "signataire": "TEXT", "signature": "TEXT"},
    }.items():
        presentes = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for nom, type_ in colonnes.items():
            if nom not in presentes:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {type_}")
    conn.commit()
    # Empreintes par champ (diagnostic du journal scellé), puis ancrage (ancrage.py) :
    # déclencheurs d'ajout seul et table des ancres.
    journal_scelle.preparer(conn)
    from . import ancrage
    ancrage.preparer(conn)
    return conn


def _j(valeur) -> str:
    def convertir(v):
        if isinstance(v, set):
            return sorted(v)
        if isinstance(v, datetime):
            return v.isoformat()
        raise TypeError(f"Type non sérialisable : {type(v).__name__}")
    return json.dumps(valeur, ensure_ascii=False, default=convertir)


def lire(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Lit un état cohérent ; une ligne illisible interrompt le démarrage."""
    champs_json = {
        "evenements": {"details": dict},
        "sessions": {"signaux": list, "leurres_touches": list, "etat_json": dict},
        "leurres": {"risques": list, "techniques": list},
        "incidents": {"chaine": list},
        "decisions": {},
    }
    etat = {}
    conn.execute("BEGIN")
    try:
        for table, champs in champs_json.items():
            lignes = []
            for ligne in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
                objet = dict(ligne)
                for champ, type_ in champs.items():
                    if champ == "etat_json" and objet[champ] is None:
                        continue
                    valeur = json.loads(objet[champ])
                    if not isinstance(valeur, type_):
                        raise ValueError(f"{table}.{champ} : type invalide pour {objet['id']}")
                    objet[champ] = valeur
                lignes.append(objet)
            etat[table] = lignes
        conn.commit()
        return etat
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Impossible de recharger la base Dédale {config.CHEMIN_DB}") from exc


def ecrire_evenement(conn: sqlite3.Connection, ev: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO evenements
        (id,horodatage,recu_a,source,surface,type,session_id,leurre_id,ip,user_agent,methode,chemin,outil,details,leurre_nature,sceau_precedent,sceau,signataire,signature)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ev["id"], ev["horodatage"], ev["recu_a"], ev["source"], ev["surface"], ev["type"],
            ev["session_id"], ev["leurre_id"], ev["ip"], ev["user_agent"], ev["methode"],
            ev["chemin"], ev["outil"], _j(ev["details"]), ev.get("leurre_nature"),
            ev.get("sceau_precedent"), ev.get("sceau"), ev.get("signataire"), ev.get("signature"),
        ),
    )
    if ev.get("sceau"):
        journal_scelle.ecrire_champs(conn, f"evenement:{ev['sceau']}", journal_scelle._contenu_evenement(ev))


def ecrire_session(conn: sqlite3.Connection, s) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO sessions
        (id,source,premier_vu,dernier_vu,etat,classement,score,signaux,leurres_touches,verite_terrain,detecte_a,confine_a,n_evenements,etat_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            s.id, s.source, s.premier_vu.isoformat(), s.dernier_vu.isoformat(), s.etat,
            s.classement, s.score, _j(s.signaux), _j(sorted(s.leurres_touches)),
            s.verite_terrain, s.detecte_a.isoformat() if s.detecte_a else None,
            s.confine_a.isoformat() if s.confine_a else None, len(s.evenement_ids), _j(asdict(s)),
        ),
    )


def ecrire_leurre(conn: sqlite3.Connection, l) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO leurres
        (id,source,surface,nature,emplacement,description,risques,techniques,humain_visible,touches,premier_touche,dernier_touche)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            l.id, l.source, l.surface, l.nature, l.emplacement, l.description,
            _j(l.risques), _j(l.techniques), int(l.humain_visible), l.touches,
            l.premier_touche, l.dernier_touche,
        ),
    )


def ecrire_incident(conn: sqlite3.Connection, i) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO incidents
        (id,session_id,type,cree_a,titre,statut,riposte_validee,analyste,decide_a,action,chaine,gravite,resume,sceau)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            i.id, i.session_id, i.type, i.cree_a.isoformat(), i.titre, i.statut,
            int(i.riposte_validee), i.analyste, i.decide_a.isoformat() if i.decide_a else None,
            i.action, _j(i.chaine), i.gravite, i.resume, getattr(i, "sceau", None),
        ),
    )
    if getattr(i, "sceau", None):
        journal_scelle.ecrire_champs(conn, f"incident:{i.id}", journal_scelle.contenu_incident_ecrit(i, i.sceau),
                                     remplacer=True)
        for m in i.chaine:
            sceau = m.get("sceau") if isinstance(m, dict) else None
            if isinstance(sceau, dict) and sceau.get("empreinte"):
                journal_scelle.ecrire_champs(conn, f"maillon:{sceau['empreinte']}", journal_scelle.contenu_maillon(m))


def ecrire_decision(conn: sqlite3.Connection, d: dict) -> None:
    cur = conn.execute(
        "INSERT INTO decisions (incident_id,action,analyste,horodatage,sceau_precedent,sceau,signataire,signature) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (d["incident_id"], d["action"], d["analyste"], d["horodatage"],
         d.get("sceau_precedent"), d.get("sceau"), d.get("signataire"), d.get("signature")),
    )
    if d.get("sceau"):
        journal_scelle.ecrire_champs(conn, f"decision:{d['sceau']}",
                                     journal_scelle.contenu_decision_ecrite(d, cur.lastrowid))
