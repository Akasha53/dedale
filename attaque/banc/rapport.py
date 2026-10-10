"""Résumé lisible et vérification de cohérence du banc.

Les métriques officielles (détection, faux positifs, temps) sont calculées par le
backend via ``GET /api/mesures`` à partir de la vérité terrain que le banc a
étiquetée. Ici, le banc vérifie seulement que son propre trafic est cohérent avec
ce qu'il prétend produire : un humain ne touche aucun leurre, un agent IA en
touche au moins un, l'agent interne touche un canari. Une incohérence est un bug
du banc, pas un résultat.
"""

from __future__ import annotations

from typing import Any

from . import evenement as ev


def coherence(manifeste: dict[str, list[dict]]) -> dict[str, Any]:
    """Agrège le manifeste par vérité terrain et relève les incohérences."""
    par_verite: dict[str, dict[str, Any]] = {
        v: {"sessions": 0, "evenements": 0, "leurres_touches": 0,
            "leurres_distincts": set(), "sessions_avec_leurre": 0}
        for v in ev.VERITES
    }
    anomalies: list[str] = []

    for sid, evenements in manifeste.items():
        verite = ev.verite_depuis_session(sid)
        if verite is None:
            anomalies.append(f"session {sid} sans vérité terrain lisible")
            continue
        bloc = par_verite[verite]
        bloc["sessions"] += 1
        bloc["evenements"] += len(evenements)
        touches = [e for e in evenements if e["type"] == "leurre_touche"]
        bloc["leurres_touches"] += len(touches)
        for e in touches:
            if e.get("leurre_id"):
                bloc["leurres_distincts"].add(e["leurre_id"])
        if touches:
            bloc["sessions_avec_leurre"] += 1
        # étiquetage : chaque événement doit porter sa vérité
        for e in evenements:
            if e["details"].get("verite_terrain") != verite:
                anomalies.append(f"{sid}: événement sans la bonne vérité terrain")
                break

        # règles attendues par type
        if verite in (ev.HUMAIN, ev.SCRIPT) and touches:
            anomalies.append(
                f"{sid}: {verite} a touché un leurre ({len(touches)}) — "
                f"ne devrait jamais arriver")
        if verite == ev.AGENT_IA and not touches:
            anomalies.append(f"{sid}: agent IA n'a touché aucun leurre")
        if verite == ev.AGENT_INTERNE:
            canaris = [e for e in touches if (e.get("leurre_id") or "").startswith("C-")]
            if not canaris:
                anomalies.append(f"{sid}: agent interne n'a touché aucun canari")

    for bloc in par_verite.values():
        bloc["leurres_distincts"] = sorted(bloc["leurres_distincts"])
    return {"par_verite": par_verite, "anomalies": anomalies}


def _ligne_verite(verite: str, bloc: dict[str, Any]) -> str:
    return (f"  {verite:14s} sessions={bloc['sessions']:>3}  "
            f"événements={bloc['evenements']:>4}  "
            f"sessions avec leurre={bloc['sessions_avec_leurre']:>3}  "
            f"leurres distincts={','.join(bloc['leurres_distincts']) or '—'}")


def resume_texte(stats: dict[str, Any], *, mode: str, client_ia: str, graine: int,
                 n_par_type: int, mesures: dict | None,
                 backend_ok: bool) -> str:
    lignes = [
        "=" * 72,
        "Banc d'attaque Dédale — résumé de campagne",
        "=" * 72,
        f"mode={mode}   client IA={client_ia}   graine={graine}   "
        f"N par type={n_par_type}",
        "",
        "Trafic produit (vérité terrain établie par le banc) :",
    ]
    for verite in ev.VERITES:
        lignes.append(_ligne_verite(verite, stats["par_verite"][verite]))

    lignes.append("")
    if stats["anomalies"]:
        lignes.append("INCOHÉRENCES (bug du banc à corriger) :")
        lignes += [f"  - {a}" for a in stats["anomalies"]]
    else:
        lignes.append("Cohérence : OK (humain/script sans leurre, agent IA avec "
                      "leurre, canari interne touché).")

    lignes.append("")
    lignes.append("Métriques officielles (backend GET /api/mesures) :")
    if not backend_ok:
        lignes.append("  backend injoignable — pas de métriques. En mode autonome, "
                      "lancer le backend puis relancer ; en mode surface, vérifier "
                      "leurres/ et interne/.")
    elif mesures is None:
        lignes.append("  /api/mesures indisponible (route pas encore implémentée ?).")
    else:
        for cle, valeur in mesures.items():
            lignes.append(f"  {cle} = {valeur}")
    lignes.append("=" * 72)
    return "\n".join(lignes)


def comparer_classements(sessions: list[dict] | None) -> list[str]:
    """Faux positifs/négatifs à partir de GET /api/sessions, si disponible."""
    if not sessions:
        return []
    ecarts = []
    for s in sessions:
        sid = s.get("id", "")
        verite = ev.verite_depuis_session(sid)
        if verite is None:
            continue
        attendu = ev.CLASSEMENT_ATTENDU[verite]
        obtenu = s.get("classement")
        if obtenu and obtenu != attendu and obtenu != "inconnu":
            genre = "faux positif" if verite in (ev.HUMAIN, ev.SCRIPT) else "écart"
            ecarts.append(f"{sid}: attendu {attendu}, classé {obtenu} ({genre})")
    return ecarts
