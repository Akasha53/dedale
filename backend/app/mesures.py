"""Mesures d'efficacité, au format lu par la console du SOC.

Vérité terrain (convention du banc d'attaque, agent E), lue de deux façons redondantes :
- préfixe du session_id : `banc-<verite>-NNNN`, verite ∈ humain | script | agentia | interne ;
- `details.verite_terrain` sur un événement : humain | script | agent_ia | agent_interne.

« Positif » = la session devait être détectée comme agent IA (agentia/interne).
Détection = part des sessions positives classées agent_ia ;
faux positifs = part des sessions humain/script classées agent_ia.
"""

from __future__ import annotations

from statistics import mean, median

_POSITIF = {"agentia", "interne", "agent_ia", "agent_interne"}
_NEGATIF = {"humain", "script"}

_NORMALISE = {
    "agentia": "agent_ia", "interne": "agent_interne",
    "agent_ia": "agent_ia", "agent_interne": "agent_interne",
    "humain": "humain", "script": "script",
}


def verite_session(sess) -> str | None:
    """Vérité terrain d'une session : préfixe du session_id d'abord, sinon verite_terrain."""
    sid = sess.id or ""
    if sid.startswith("banc-"):
        morceaux = sid.split("-")
        if len(morceaux) >= 2 and morceaux[1] in _NORMALISE:
            return _NORMALISE[morceaux[1]]
    if sess.verite_terrain in _NORMALISE:
        return _NORMALISE[sess.verite_terrain]
    return None


def duree_ms(secondes: list[float]) -> dict:
    """Médiane et moyenne d'une liste de délais, en millisecondes, avec le nombre de mesures."""
    if not secondes:
        return {"mediane_ms": None, "moyenne_ms": None, "echantillons": 0}
    return {
        "mediane_ms": round(median(secondes) * 1000),
        "moyenne_ms": round(mean(secondes) * 1000),
        "echantillons": len(secondes),
    }


def _relecteur(evenements: list[dict]) -> dict:
    from . import relecteur  # import local : relecteur dépend du store
    return relecteur.mesures(evenements)


def calculer(store) -> dict:
    with store.lock:
        sessions = list(store.sessions.values())
        incidents = list(store.incidents.values())
        evenements = list(store.evenements.values())

    repartition = {"humain": 0, "script": 0, "agent_ia": 0, "inconnu": 0}
    vp = fp = vn = fn = 0
    sans_verite = 0
    delais_detection: list[float] = []
    positifs_ordonnes: list[tuple] = []

    for s in sessions:
        repartition[s.classement] = repartition.get(s.classement, 0) + 1
        v = verite_session(s)
        if v is None:
            sans_verite += 1
            continue
        attendu_positif = v in _POSITIF
        detecte = s.classement == "agent_ia"
        if attendu_positif:
            positifs_ordonnes.append((s.premier_vu, detecte))
            if detecte:
                vp += 1
                if s.detecte_a is not None:
                    delais_detection.append((s.detecte_a - s.premier_vu).total_seconds())
            else:
                fn += 1
        else:
            if detecte:
                fp += 1
            else:
                vn += 1

    taux_detection = vp / (vp + fn) if (vp + fn) else None
    faux_positifs = fp / (fp + vn) if (fp + vn) else None

    # Pilier humain : gestes risqués arrêtés (annuler, bon réflexe) vs passés outre (continuer,
    # signal fort). Comptés sur les événements d'avertissement du garde du corps du poste.
    gestes_arretes = gestes_passes = 0
    signalements = 0
    passes_par_type: dict[str, int] = {}
    for e in evenements:
        if e.get("type") == "signalement":
            signalements += 1
            continue
        if e.get("type") != "avertissement":
            continue
        d = e.get("details") or {}
        choix = d.get("choix")
        if choix == "annuler":
            gestes_arretes += 1
        elif choix == "continuer":
            gestes_passes += 1
            cat = d.get("categorie") or "inconnu"
            passes_par_type[cat] = passes_par_type.get(cat, 0) + 1

    delais_confinement = [
        (s.confine_a - s.detecte_a).total_seconds()
        for s in sessions
        if s.detecte_a is not None and s.confine_a is not None
    ]

    # Série de détection : taux cumulé après chaque session positive, dans l'ordre du temps.
    serie = []
    vus = detectes = 0
    for i, (_, det) in enumerate(sorted(positifs_ordonnes, key=lambda x: x[0]), start=1):
        vus += 1
        detectes += 1 if det else 0
        serie.append({"t": f"#{i}", "valeur": round(detectes / vus, 3)})

    return {
        "taux_detection": round(taux_detection, 3) if taux_detection is not None else None,
        "faux_positifs": round(faux_positifs, 3) if faux_positifs is not None else None,
        "temps_detection_s": round(mean(delais_detection), 2) if delais_detection else None,
        "temps_confinement_s": round(mean(delais_confinement), 2) if delais_confinement else None,
        # Les deux champs *_s ci-dessus sont des moyennes. Médiane et moyenne explicites :
        "temps_detection": duree_ms(delais_detection),
        "temps_confinement": duree_ms(delais_confinement),
        "sessions_total": len(sessions),
        "agents_detectes": repartition.get("agent_ia", 0),
        "incidents_ouverts": sum(1 for i in incidents if i.statut == "ouvert"),
        "incidents_clos": sum(1 for i in incidents if i.statut in ("clos", "ignore")),
        "repartition": repartition,
        "serie_detection": serie,
        # Détail utile à l'analyste (toléré par la console).
        "matrice": {"vrais_positifs": vp, "faux_positifs": fp, "vrais_negatifs": vn, "faux_negatifs": fn},
        "sessions_sans_verite_terrain": sans_verite,
        # Relecteur IA : décisions par acte et par moteur, durée médiane (relecteur.py).
        "relecteur": _relecteur(evenements),
        # Pilier humain : efficacité du garde du corps du poste.
        "gestes_humains": {
            "arretes": gestes_arretes,
            "passes_outre": gestes_passes,
            "total": gestes_arretes + gestes_passes,
            "passes_outre_par_type": passes_par_type,
            "incidents_humains": sum(1 for i in incidents if str(i.type).startswith("humain_")),
            # Mails signalés par les salariés eux-mêmes (app Mac).
            "signalements": signalements,
        },
    }
