"""Vérifie le journal scellé de toute une base Dédale, en lecture seule.

    uv run python -m app.verifier_journal [--db CHEMIN] [--json]

Recalcule la chaîne des événements, celle des décisions et la boîte noire de chaque incident.
Code de sortie : 0 si tout est intact (les lignes antérieures au scellement sont signalées,
pas comptées comme altérées), 1 si une altération est trouvée, 2 si la base est absente ou
illisible.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import config, journal_scelle


def _suite(nom: str, res: dict) -> str:
    morceaux = [f"{res['verifies']} scellé(s)"]
    if res["anterieurs"]:
        morceaux.append(f"{res['anterieurs']} antérieur(s) au scellement")
    etat = "chaîne intacte" if res["intacte"] else f"ALTÉRÉE au rang {res['rang']} ({res['raison']})"
    return f"{nom} : {', '.join(morceaux)} : {etat}"


def rendre(chemin: Path, res: dict) -> str:
    lignes = [f"Journal Dédale : {chemin}", _suite("Événements", res["evenements"]),
              _suite("Décisions", res["decisions"])]
    incidents = [i for i in res["incidents"] if i]
    compte = {"intacte": 0, "alteree": 0, "anterieure_au_scellement": 0}
    for i in incidents:
        compte[i["statut"]] = compte.get(i["statut"], 0) + 1
    lignes.append(
        f"Incidents : {compte['intacte']} intact(s), {compte['alteree']} altéré(s), "
        f"{compte['anterieure_au_scellement']} antérieur(s) au scellement"
    )
    for i in incidents:
        detail = f"{i['maillons_verifies']} maillon(s), {i['decisions_verifiees']} décision(s)"
        raison = f" : {i['raison']}" if i.get("raison") else ""
        lignes.append(f"  {i['incident_id']} {i['verdict']} ({detail}){raison}")
    lignes.append(f"Verdict : {'intacte' if res['statut'] == 'intacte' else 'ALTÉRÉE'}")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Vérifie le journal scellé d'une base Dédale.")
    parseur.add_argument("--db", default=str(config.CHEMIN_DB), help="base SQLite (défaut : DEDALE_DB)")
    parseur.add_argument("--json", action="store_true", help="sortie JSON")
    args = parseur.parse_args(argv)
    chemin = Path(args.db)
    if not chemin.is_file():
        print(f"Base introuvable : {chemin}", file=sys.stderr)
        return 2
    try:
        conn = journal_scelle.ouvrir_lecture(chemin)
        try:
            res = journal_scelle.verifier_base(conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"Base illisible : {chemin} ({exc})", file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else rendre(chemin, res))
    return 0 if res["statut"] == "intacte" else 1


if __name__ == "__main__":
    sys.exit(main())
