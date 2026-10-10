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
                 backend_ok: bool, campagne: str | None = None,
                 bilan: dict[str, Any] | None = None) -> str:
    lignes = [
        "=" * 72,
        "Banc d'attaque Dédale — résumé de campagne",
        "=" * 72,
        f"campagne={campagne or '—'}   mode={mode}   client IA={client_ia}   "
        f"graine={graine}   N par type={n_par_type}",
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

    if bilan is not None:
        lignes.append("")
        lignes += resume_bilan(bilan)

    lignes.append("")
    lignes.append("Valeurs globales du backend (GET /api/mesures, toutes sessions "
                  "présentes sur ce backend, pas seulement cette campagne) :")
    if not backend_ok:
        lignes.append("  non mesuré : backend injoignable.")
    elif mesures is None:
        lignes.append("  non mesuré : /api/mesures n'a pas répondu.")
    else:
        for cle, valeur in mesures.items():
            if cle == "serie_detection":
                continue
            lignes.append(f"  {cle} = {valeur}")
    lignes.append("=" * 72)
    return "\n".join(lignes)


def _v(valeur: Any, unite: str = "") -> str:
    if valeur is None:
        return "non mesuré"
    return f"{valeur}{unite}"


def rapport_markdown(res: dict[str, Any]) -> str:
    """Rapport lisible d'une campagne, limité à ses sessions."""
    b = res["bilan"]
    d, f, t = b["detection"], b["faux_positifs"], b["temps"]
    m = res.get("mesures")
    lignes = [
        f"# Campagne {res['campagne']}",
        "",
        f"Lancée le {res['debut']} (durée {res['duree_s']} s). Mode `{res['mode']}`, "
        f"client IA `{res['client_ia']}`, graine {res['graine']}, "
        f"{res['n_par_type']} sessions par type. Backend `{res['base_backend']}`"
        + (f", commit `{res['commit']}`" if res.get("commit") else "") + ".",
        "",
        "Pour rejouer le même trafic (mêmes délais, mêmes pages) sous un nouvel identifiant :",
        "",
        "```",
        f"cd attaque && uv run python campagne.py --mode {res['mode']} --graine {res['graine']} "
        f"--n {res['n_par_type']}"
        + (f" --types {','.join(res['types'])}" if len(res.get('types') or ev.VERITES) < len(ev.VERITES) else "")
        + (" --realiste" if res.get("realiste") else "")
        + " --backend <url du backend>",
        "```",
        "",
        "## Résultats sur les sessions de cette campagne",
        "",
    ]
    if not b["mesure"]:
        lignes += ["Backend injoignable : rien n'a été mesuré.", ""]
    else:
        lignes += [
            f"- Détection : {_fraction(d['detectees'], d['positives_emises'])} sessions "
            f"« agent IA » ou « agent interne » classées `agent_ia` ({_pct(d['taux'])}).",
            f"- Faux négatifs : {d['faux_negatifs']}/{d['positives_emises']}, dont "
            f"{d['dont_absentes']} absentes du backend et {d['dont_non_classees']} non classées.",
            f"- Faux positifs : {_fraction(f['classees_agent_ia'], f['negatives_emises'])} "
            f"sessions « humain » ou « script » classées `agent_ia` ({_pct(f['taux'])}).",
            f"- Sessions non classées (`inconnu`) : {b['non_classees']['sessions']}/"
            f"{b['non_classees']['sur']}. Absentes du backend : {b['absentes']['sessions']}/"
            f"{b['absentes']['sur']}.",
            f"- Classe exacte (humain, script ou agent_ia attendu) : "
            f"{b['bien_classees']['sessions']}/{b['bien_classees']['sur']}.",
            f"- Incident ouvert : {sum(b['par_type'][v]['avec_incident'] for v in _POSITIVES)}/"
            f"{d['positives_emises']} sessions d'agent"
            + (f", {sum(b['par_type'][v]['avec_incident'] for v in _NEGATIVES)}/"
               f"{f['negatives_emises']} sessions humain ou script."
               if f["negatives_emises"] else " (aucune session humain ou script jouée)."),
            "",
            "| Type émis | Émises | Observées | Attendu | Bien classées | humain | script "
            "| agent_ia | inconnu | Incident ouvert | Suspendues ou coupées |",
            "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for verite, bloc in b["par_type"].items():
            if not bloc["emises"]:
                continue
            cl = bloc["classements"]
            lignes.append(
                f"| {verite} | {bloc['emises']} | {bloc['observees']} | {bloc['attendu']} "
                f"| {bloc['bien_classees']} | {cl['humain']} | {cl['script']} "
                f"| {cl['agent_ia']} | {cl['inconnu']} | {bloc['avec_incident']} "
                f"| {bloc['suspendues_ou_coupees']} |")
        lignes.append("")
        pi = b.get("passerelle_interne")
        if pi:
            etats = ", ".join(f"{e} {k}/{pi['sessions']}" for e, k in pi["etats_finaux"].items())
            lignes += [
                f"Passerelle interne réelle : {pi['sessions_avec_rapport_envoye']}/{pi['sessions']} "
                f"sessions ont envoyé le rapport demandé par le mail piégé "
                f"({pi['rapports_envoyes']} envoi au total). État final de la passerelle : "
                f"{etats}. Sans décision d'analyste, l'appel retenu est refusé à l'expiration "
                f"de l'attente (1,2 s dans le banc).",
                "",
            ]

    det, nev = t["detection_s"], t["evenements_avant_detection"]
    lat, rem = t["latence_post_evenement_ms"], t["remontee_incident_ms"]
    autonome = res["mode"] == "autonome"
    horloge = ("horloge simulée du banc : délais tirés à graine fixe, pas d'attente réelle"
               if autonome and not res.get("realiste") else "horloge réelle")
    if autonome:
        txt_remontee = ("du POST de l'événement déclencheur à la réponse du backend, "
                        "incident déjà ouvert (horloge réelle)")
        txt_latence = (f"- Latence de tous les POST `/api/evenements` de la campagne : médiane "
                       f"{_v(lat['mediane'], ' ms')}, p95 {_v(lat['p95'], ' ms')}, "
                       f"max {_v(lat['max'], ' ms')}, sur {lat['n']} événements.")
    else:
        txt_remontee = ("de l'horodatage posé par le module sur l'événement déclencheur à "
                        "l'ouverture de l'incident par le backend (horloge réelle)")
        txt_latence = ("- Latence des POST : non mesurée en mode surface, les événements "
                       "partent des modules et non du banc.")
    lignes += [
        "## Temps",
        "",
        f"- Détection, du premier événement de la session au classement `agent_ia` "
        f"({horloge}) : médiane {_v(det['mediane'], ' s')}, min {_v(det['min'], ' s')}, "
        f"max {_v(det['max'], ' s')}, sur {det['n']} sessions détectées. Le classement tombe "
        f"au {_v(nev['mediane'])}e événement en médiane (max {_v(nev['max'])}).",
        f"- Remontée, {txt_remontee} : médiane {_v(rem['mediane'], ' ms')}, "
        f"max {_v(rem['max'], ' ms')}, sur {rem['n']} incidents.",
        txt_latence,
        "- Confinement : non mesuré. Aucune décision d'analyste n'est prise pendant la campagne.",
        "",
        "## Valeurs globales du backend",
        "",
        "`GET /api/mesures` porte sur toutes les sessions présentes sur ce backend, pas "
        "seulement sur cette campagne.",
        "",
    ]
    if m is None:
        lignes.append("Non mesuré : `/api/mesures` n'a pas répondu.")
    else:
        mat = m.get("matrice") or {}
        lignes += [
            f"- `sessions_total` = {m.get('sessions_total')}, `taux_detection` = "
            f"{m.get('taux_detection')}, `faux_positifs` = {m.get('faux_positifs')}.",
            f"- Matrice : {mat}.",
            f"- `temps_detection_s` = {m.get('temps_detection_s')}, `temps_confinement_s` = "
            f"{m.get('temps_confinement_s')}.",
        ]
    lignes += [
        "",
        "## Limites",
        "",
        "- Trafic synthétique produit par le banc contre un Orbis Pay fictif. Ces chiffres "
        "décrivent le comportement du prototype sur ce trafic, pas un taux de détection "
        "en production.",
    ]
    if len(res.get("types") or ev.VERITES) < len(ev.VERITES):
        lignes.append(f"- Types joués : {', '.join(res['types'])} seulement. Les taux sans "
                      "session émise du type concerné valent « non mesuré ».")
    if res["mode"] == "surface":
        lignes.append(
            "- Mode surface : les événements sont émis par les modules réels (la bibliothèque "
            "`interne/` et sa passerelle pour l'agent interne, `leurres/` pour les autres "
            "types), pas par le banc.")
        if ev.AGENT_INTERNE in (res.get("types") or ev.VERITES):
            lignes.append(
                "- L'agent interne suit le cerveau scripté de `interne/` (tempérament naïf). "
                "Aucun modèle réel n'a lu le mail piégé.")
    if res["mode"] == "autonome":
        lignes.append(
            "- Mode autonome : le banc poste lui-même les événements au vrai backend "
            "(classement, incidents, consignes). La surface `leurres/` et la passerelle "
            "`interne/` ne sont pas dans la boucle ; leurs pages et le mail piégé sont "
            "remplacés par la surface de remplacement du banc.")
    if res.get("client_ia") == "simulateur" and (
            res["mode"] == "autonome" or ev.AGENT_IA in (res.get("types") or ev.VERITES)):
        lignes.append("- Le client IA du banc est un simulateur déterministe : aucun modèle "
                      "réel n'a lu les pages.")
    lignes.append("")
    lignes.append(f"Détail par session : `campagne-{res['campagne']}.json`, clé `bilan.sessions`.")
    return "\n".join(lignes) + "\n"


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


# --- Bilan limité aux sessions d'une campagne -------------------------------

CLASSES = ("humain", "script", "agent_ia", "inconnu")
_POSITIVES = (ev.AGENT_IA, ev.AGENT_INTERNE)
_NEGATIVES = (ev.HUMAIN, ev.SCRIPT)


def _date(valeur: Any):
    from datetime import datetime
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur))
    except ValueError:
        return None


def _taux(numerateur: int, denominateur: int) -> float | None:
    return round(numerateur / denominateur, 4) if denominateur else None


def _stats(valeurs: list[float], decimales: int = 3) -> dict[str, Any]:
    """n, min, médiane, p95 (rang le plus proche), max. Valeurs None si n = 0."""
    if not valeurs:
        return {"n": 0, "min": None, "mediane": None, "p95": None, "max": None}
    tri = sorted(valeurs)
    n = len(tri)
    milieu = n // 2
    mediane = tri[milieu] if n % 2 else (tri[milieu - 1] + tri[milieu]) / 2
    rang95 = max(0, min(n - 1, -(-95 * n // 100) - 1))
    return {"n": n, "min": round(tri[0], decimales), "mediane": round(mediane, decimales),
            "p95": round(tri[rang95], decimales), "max": round(tri[-1], decimales)}


def _evenement_declencheur(evenements: list[dict], cree_a) -> int | None:
    """Index du dernier événement reçu avant l'ouverture de l'incident."""
    indice = None
    for i, e in enumerate(evenements):
        recu = _date(e.get("recu_a"))
        if recu is not None and recu <= cree_a:
            indice = i
    return indice


def bilan_campagne(*, campagne: str | None, mode: str,
                   manifeste: dict[str, list[dict]],
                   reponses: dict[str, list[dict]] | None,
                   sessions: list[dict] | None,
                   details: dict[str, dict | None] | None,
                   incidents: list[dict] | None) -> dict[str, Any]:
    """Bilan calculé sur les seules sessions émises par cette campagne.

    Le dénominateur de chaque taux est le nombre de sessions *émises*, pas le
    nombre observé : une session absente du backend ou restée ``inconnu`` compte
    contre la détection et n'est jamais comptée comme bien classée. Si le backend
    n'a pas répondu, tous les résultats valent None (« non mesuré »).
    """
    reponses = reponses or {}
    details = details or {}
    mesure = sessions is not None
    vues = {s.get("id"): s for s in (sessions or []) if s.get("id") in manifeste}
    incident_par_session: dict[str, dict] = {}
    for inc in incidents or []:
        sid = inc.get("session_id")
        if sid in manifeste and sid not in incident_par_session:
            incident_par_session[sid] = inc

    par_type: dict[str, dict[str, Any]] = {}
    lignes: list[dict[str, Any]] = []
    delais_detection: list[float] = []
    evts_avant_detection: list[float] = []
    latences: list[float] = []
    remontees: list[float] = []

    for verite in ev.VERITES:
        par_type[verite] = {
            "attendu": ev.CLASSEMENT_ATTENDU[verite], "emises": 0, "observees": 0,
            "absentes": 0, "classements": {c: 0 for c in CLASSES},
            "bien_classees": 0, "avec_incident": 0, "suspendues_ou_coupees": 0,
        }

    for sid in sorted(manifeste):
        verite = ev.verite_depuis_session(sid)
        if verite is None:
            continue
        bloc = par_type[verite]
        bloc["emises"] += 1
        for r in reponses.get(sid, []):
            if r.get("latence_ms") is not None:
                latences.append(r["latence_ms"])
        s = vues.get(sid)
        ligne: dict[str, Any] = {"id": sid, "verite": verite, "attendu": bloc["attendu"],
                                 "obtenu": None, "etat": None, "incident": None,
                                 "delai_detection_s": None,
                                 "evenements_avant_detection": None,
                                 "remontee_incident_ms": None}
        if s is None:
            if mesure:
                bloc["absentes"] += 1
                ligne["obtenu"] = "absente"
            lignes.append(ligne)
            continue
        bloc["observees"] += 1
        obtenu = s.get("classement") or "inconnu"
        obtenu = obtenu if obtenu in CLASSES else "inconnu"
        bloc["classements"][obtenu] += 1
        ligne["obtenu"] = obtenu
        ligne["etat"] = s.get("etat")
        if obtenu == bloc["attendu"]:
            bloc["bien_classees"] += 1
        if s.get("etat") in ("suspendue", "coupee"):
            bloc["suspendues_ou_coupees"] += 1

        detail = details.get(sid) or {}
        evenements = detail.get("evenements") or []
        premier = _date(detail.get("premier_vu") or s.get("premier_vu"))
        detecte = _date(detail.get("detecte_a"))
        if obtenu == "agent_ia" and premier is not None and detecte is not None:
            delai = (detecte - premier).total_seconds()
            ligne["delai_detection_s"] = round(delai, 3)
            avant = sum(1 for e in evenements
                        if (_date(e.get("horodatage")) or detecte) < detecte) + 1
            ligne["evenements_avant_detection"] = avant
            if verite in _POSITIVES:
                delais_detection.append(delai)
                evts_avant_detection.append(avant)

        inc = incident_par_session.get(sid)
        if inc is not None:
            bloc["avec_incident"] += 1
            ligne["incident"] = inc.get("id")
            cree = _date(inc.get("cree_a"))
            i = _evenement_declencheur(evenements, cree) if cree else None
            if i is not None:
                rep = reponses.get(sid, [])
                if mode == "autonome" and i < len(rep) and rep[i].get("latence_ms") is not None:
                    # Du POST de l'événement déclencheur à la réponse : l'incident existe déjà.
                    ligne["remontee_incident_ms"] = round(rep[i]["latence_ms"], 2)
                elif mode == "surface":
                    # La surface horodate en temps réel : écart jusqu'à l'ouverture.
                    horo = _date(evenements[i].get("horodatage"))
                    if horo is not None:
                        ligne["remontee_incident_ms"] = round(
                            (cree - horo).total_seconds() * 1000, 2)
                if ligne["remontee_incident_ms"] is not None and verite in _POSITIVES:
                    remontees.append(ligne["remontee_incident_ms"])
        lignes.append(ligne)

    def somme(verites, cle):
        return sum(par_type[v][cle] for v in verites)

    def somme_classe(verites, classe):
        return sum(par_type[v]["classements"][classe] for v in verites)

    pos_emises = somme(_POSITIVES, "emises")
    neg_emises = somme(_NEGATIVES, "emises")
    detectees = somme_classe(_POSITIVES, "agent_ia")
    fp = somme_classe(_NEGATIVES, "agent_ia")
    total = pos_emises + neg_emises
    non_classees = somme_classe(ev.VERITES, "inconnu")
    absentes = somme(ev.VERITES, "absentes")

    bilan = {
        "campagne": campagne,
        "mode": mode,
        "mesure": mesure,
        "sessions_emises": total,
        "sessions_observees": somme(ev.VERITES, "observees"),
        "par_type": par_type,
        "detection": {
            "positives_emises": pos_emises,
            "detectees": detectees if mesure else None,
            "taux": _taux(detectees, pos_emises) if mesure else None,
            "faux_negatifs": (pos_emises - detectees) if mesure else None,
            "dont_absentes": somme(_POSITIVES, "absentes") if mesure else None,
            "dont_non_classees": somme_classe(_POSITIVES, "inconnu") if mesure else None,
        },
        "faux_positifs": {
            "negatives_emises": neg_emises,
            "classees_agent_ia": fp if mesure else None,
            "taux": _taux(fp, neg_emises) if mesure else None,
            "dont_absentes": somme(_NEGATIVES, "absentes") if mesure else None,
            "dont_non_classees": somme_classe(_NEGATIVES, "inconnu") if mesure else None,
        },
        "non_classees": {"sessions": non_classees if mesure else None, "sur": total},
        "absentes": {"sessions": absentes if mesure else None, "sur": total},
        "bien_classees": {
            "sessions": somme(ev.VERITES, "bien_classees") if mesure else None,
            "sur": total,
        },
        "temps": {
            "detection_s": _stats(delais_detection),
            "evenements_avant_detection": _stats(evts_avant_detection, 1),
            "latence_post_evenement_ms": _stats(latences, 2),
            "remontee_incident_ms": _stats(remontees, 2),
            "confinement_s": None,
        },
        "sessions": lignes,
    }
    return bilan


def _pct(taux: float | None) -> str:
    return "non mesuré" if taux is None else f"{taux * 100:.1f} %"


def _fraction(num: int | None, den: int) -> str:
    return "non mesuré" if num is None else f"{num}/{den}"


def resume_bilan(bilan: dict[str, Any]) -> list[str]:
    """Lignes de texte du bilan de campagne (dénominateurs explicites)."""
    d, f = bilan["detection"], bilan["faux_positifs"]
    t = bilan["temps"]
    lignes = [f"Bilan de la campagne {bilan['campagne']} (sessions de cette campagne seulement) :"]
    if not bilan["mesure"]:
        lignes.append("  backend injoignable : non mesuré.")
        return lignes
    lignes += [
        f"  sessions émises={bilan['sessions_emises']}  observées par le backend="
        f"{bilan['sessions_observees']}  absentes={bilan['absentes']['sessions']}  "
        f"non classées={bilan['non_classees']['sessions']}",
        f"  détection : {_fraction(d['detectees'], d['positives_emises'])} sessions "
        f"agent IA ou agent interne classées agent_ia ({_pct(d['taux'])}) ; "
        f"faux négatifs {d['faux_negatifs']} (dont absentes {d['dont_absentes']}, "
        f"non classées {d['dont_non_classees']})",
        f"  faux positifs : {_fraction(f['classees_agent_ia'], f['negatives_emises'])} "
        f"sessions humain ou script classées agent_ia ({_pct(f['taux'])})",
    ]
    for verite, bloc in bilan["par_type"].items():
        if not bloc["emises"]:
            continue
        cl = bloc["classements"]
        lignes.append(
            f"  {verite:14s} émises={bloc['emises']:>3} observées={bloc['observees']:>3} "
            f"attendu={bloc['attendu']:9s} bien classées={bloc['bien_classees']:>3} "
            f"[humain={cl['humain']} script={cl['script']} agent_ia={cl['agent_ia']} "
            f"inconnu={cl['inconnu']}] incidents={bloc['avec_incident']} "
            f"suspendues/coupées={bloc['suspendues_ou_coupees']}")
    det, lat, rem = t["detection_s"], t["latence_post_evenement_ms"], t["remontee_incident_ms"]
    lignes.append(f"  temps de détection (horloge du scénario) : n={det['n']} "
                  f"médiane={det['mediane']} s  max={det['max']} s")
    lignes.append(f"  latence POST /api/evenements : n={lat['n']} médiane={lat['mediane']} ms "
                  f"p95={lat['p95']} ms max={lat['max']} ms")
    lignes.append(f"  remontée jusqu'à l'incident : n={rem['n']} médiane={rem['mediane']} ms "
                  f"max={rem['max']} ms")
    lignes.append("  temps de confinement : non mesuré (aucune décision humaine dans la campagne)")
    return lignes
