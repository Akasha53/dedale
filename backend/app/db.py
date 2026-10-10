"""Persistance SQLite (WAL) alimentée par un unique écrivain en tâche de fond.

Schéma : cinq tables — evenements, sessions, leurres, incidents, decisions.
Un seul writer (la boucle de fond) écrit : pas de contention d'écriture concurrente.
Les lectures live de l'API passent par le Store en mémoire, pas par SQLite.
"""

from __future__ import annotations

import json
import sqlite3

from . import config

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
    conn.commit()
    return conn


def _j(valeur) -> str:
    return json.dumps(valeur, ensure_ascii=False, default=str)


def ecrire_evenement(conn: sqlite3.Connection, ev: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO evenements
        (id,horodatage,recu_a,source,surface,type,session_id,leurre_id,ip,user_agent,methode,chemin,outil,details)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ev["id"], ev["horodatage"], ev["recu_a"], ev["source"], ev["surface"], ev["type"],
            ev["session_id"], ev["leurre_id"], ev["ip"], ev["user_agent"], ev["methode"],
            ev["chemin"], ev["outil"], _j(ev["details"]),
        ),
    )


def ecrire_session(conn: sqlite3.Connection, s) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO sessions
        (id,source,premier_vu,dernier_vu,etat,classement,score,signaux,leurres_touches,verite_terrain,detecte_a,confine_a,n_evenements)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            s.id, s.source, s.premier_vu.isoformat(), s.dernier_vu.isoformat(), s.etat,
            s.classement, s.score, _j(s.signaux), _j(sorted(s.leurres_touches)),
            s.verite_terrain, s.detecte_a.isoformat() if s.detecte_a else None,
            s.confine_a.isoformat() if s.confine_a else None, len(s.evenement_ids),
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
        (id,session_id,type,cree_a,titre,statut,riposte_validee,analyste,decide_a,action,chaine)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            i.id, i.session_id, i.type, i.cree_a.isoformat(), i.titre, i.statut,
            int(i.riposte_validee), i.analyste, i.decide_a.isoformat() if i.decide_a else None,
            i.action, _j(i.chaine),
        ),
    )


def ecrire_decision(conn: sqlite3.Connection, d: dict) -> None:
    conn.execute(
        "INSERT INTO decisions (incident_id,action,analyste,horodatage) VALUES (?,?,?,?)",
        (d["incident_id"], d["action"], d["analyste"], d["horodatage"]),
    )
