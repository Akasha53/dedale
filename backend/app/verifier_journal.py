"""Vérifie le journal scellé de toute une base Dédale, en lecture seule.

    uv run python -m app.verifier_journal [--db CHEMIN] [--json] [--sans-reseau]

Recalcule la chaîne des événements, celle des décisions et la boîte noire de chaque incident,
vérifie la signature Ed25519 de chaque entrée, puis recalcule la racine de Merkle de chaque lot
ancré et la compare à celle publiée sur Avalanche Fuji (ancrage.py). Code de sortie : 0 si tout
est intact (les lignes antérieures au scellement sont signalées, pas comptées comme altérées),
1 si une altération est trouvée, 2 si la base est absente ou illisible.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import ancrage, config, journal_scelle


def _n(nombre: int, singulier: str, pluriel: str) -> str:
    return f"{nombre} {singulier if nombre <= 1 else pluriel}"


def _suite(nom: str, res: dict, genre: str) -> str:
    morceaux = [_n(res["verifies"], f"scellé{genre}", f"scellé{genre}s")]
    if res["anterieurs"]:
        morceaux.append(_n(res["anterieurs"], f"antérieur{genre} au scellement",
                           f"antérieur{genre}s au scellement"))
    etat = "chaîne intacte" if res["intacte"] else f"ALTÉRÉE au rang {res['rang']} ({res['raison']})"
    return f"{nom} : {', '.join(morceaux)} : {etat}"


def rendre(chemin: Path, res: dict) -> str:
    lignes = [f"Journal Dédale : {chemin}", _suite("Événements", res["evenements"], ""),
              _suite("Décisions", res["decisions"], "e")]
    incidents = [i for i in res["incidents"] if i]
    compte = {"intacte": 0, "alteree": 0, "anterieure_au_scellement": 0}
    for i in incidents:
        compte[i["statut"]] = compte.get(i["statut"], 0) + 1
    lignes.append(
        f"Incidents : {_n(compte['intacte'], 'intact', 'intacts')}, "
        f"{_n(compte['alteree'], 'altéré', 'altérés')}, "
        f"{_n(compte['anterieure_au_scellement'], 'antérieur', 'antérieurs')} au scellement"
    )
    for i in incidents:
        if i["statut"] == "intacte":
            detail = (f" ({_n(i['maillons_verifies'], 'maillon', 'maillons')}, "
                      f"{_n(i['decisions_verifiees'], 'décision', 'décisions')})")
        else:
            detail = f" : {i['raison']}" if i.get("raison") else ""
        lignes.append(f"  {i['incident_id']} {i['verdict']}{detail}")
    lignes += _lignes_ancrage(res)
    lignes.append(f"Verdict : {'intacte' if _intacte(res) else 'ALTÉRÉE'}")
    return "\n".join(lignes)


def _intacte(res: dict) -> bool:
    anc = res.get("ancrage") or {}
    sig = anc.get("signatures") or {}
    return (res["statut"] == "intacte" and anc.get("statut") != "altere"
            and not sig.get("falsifiees") and not sig.get("retirees"))


def _lignes_ancrage(res: dict) -> list[str]:
    anc = res.get("ancrage")
    if not anc:
        return []
    sig = anc["signatures"]
    emetteurs = ", ".join(f"{e} {n}" for e, n in sorted(sig["par_emetteur"].items()))
    morceaux = [_n(sig["valides"], "valide", "valides") + (f" ({emetteurs})" if emetteurs else "")]
    morceaux.append(_n(sig["falsifiees"], "falsifiée", "falsifiées"))
    if sig["retirees"]:
        morceaux.append(_n(sig["retirees"], "retirée", "retirées"))
    if sig["absentes"]:
        morceaux.append(f"{sig['absentes']} antérieure(s) à la signature")
    if sig["cles_inconnues"]:
        morceaux.append(f"{sig['cles_inconnues']} sans clé sur cette machine")
    lignes = [f"Signatures Ed25519 : {', '.join(morceaux)}"]
    lignes.append("Ajout seul : déclencheurs en place sur evenements et decisions" if anc["ajout_seul"]
                  else "Ajout seul : déclencheurs ABSENTS, retirés par un administrateur de la base")
    libelle = anc["libelle"]
    if anc["statut"] in ("ancre", "en_attente") and res["statut"] == "intacte":
        libelle = f"Journal intact, {libelle}"
    if anc["statut"] == "en_attente" and anc.get("raison_attente"):
        libelle += f" ({ancrage.libelle_attente(anc['raison_attente'])})"
    lien = (anc.get("alteration") or {}).get("lien") or (anc.get("derniere_ancre") or {}).get("lien")
    lignes.append(f"Ancrage : {libelle}" + (f", {lien}" if lien else ""))
    confirmes = sum(1 for l in anc["lots"] if l["statut_envoi"] == "confirmee")
    if anc["lots"]:
        relue = "relue sur la chaîne" if anc["chaine_relue"] else "chaîne non relue, comparée à la base"
        lignes.append(f"  {_n(len(anc['lots']), 'lot', 'lots')}, {confirmes} sur Avalanche ({relue})")
    return lignes


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Vérifie le journal scellé d'une base Dédale.")
    parseur.add_argument("--db", default=str(config.CHEMIN_DB), help="base SQLite (défaut : DEDALE_DB)")
    parseur.add_argument("--json", action="store_true", help="sortie JSON")
    parseur.add_argument("--sans-reseau", action="store_true",
                         help="ne relit pas les ancres sur Avalanche (comparaison à la base seule)")
    args = parseur.parse_args(argv)
    chemin = Path(args.db)
    if not chemin.is_file():
        print(f"Base introuvable : {chemin}", file=sys.stderr)
        return 2
    try:
        conn = journal_scelle.ouvrir_lecture(chemin)
        try:
            res = journal_scelle.verifier_base(conn)
            rpc = None if args.sans_reseau else ancrage.client_rpc()
            # Chaque dossier passe par la vérification du badge de la console.
            res["incidents"] = [ancrage.verifier_dossier(conn, i["incident_id"], rpc) if i else i
                                for i in res["incidents"]]
            res["incidents_alteres"] = [i["incident_id"] for i in res["incidents"]
                                        if i and i["statut"] == "alteree"]
            if res["incidents_alteres"]:
                res["statut"] = "alteree"
            res["ancrage"] = ancrage.verifier_base(conn, rpc)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"Base illisible : {chemin} ({exc})", file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else rendre(chemin, res))
    return 0 if _intacte(res) else 1


if __name__ == "__main__":
    sys.exit(main())
