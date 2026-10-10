"""Résumé du lundi : un mail HTML d'une page pour une PME sans SOC.

`GET /api/resume-hebdo` rend le mail que recevrait la direction le lundi matin. Il n'est jamais
envoyé : la console l'affiche en aperçu (Mesures, « Résumé du lundi »). Quatre parties, une
phrase par point, sans jargon :

1. les menaces, arrêtées ou à suivre ;
2. les gestes retenus (virement, export) et leur issue ;
3. les agents IA à surveiller ;
4. les règles de l'équipe sécurité qui ont joué.

Puis ce qui attend encore une décision. Les mots techniques (incident, canari, MCP, SOC,
ATT&CK) n'y figurent pas : « dossier », « piège », « outil branché à l'agent », « équipe
sécurité ». Un salarié n'apparaît que par son service, jamais par son nom ni son pseudonyme ;
un montant jamais en chiffre exact.

Le HTML est fait pour un client mail : mise en page en tableaux, styles en ligne, aucune image
distante, aucun script. Couleurs et rayons repris de `design/jetons.css`.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from . import inventaire, notifications

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
_RANG = {"faible": 1, "moyenne": 2, "haute": 3, "critique": 4}
_MAX_LIGNES = 6

CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'self'")

# Jetons de la console (design/jetons.css), recopiés en dur : un client mail ne lit pas les
# variables CSS.
C = {
    "fond": "#f4f4f4", "carte": "#ffffff", "bord": "#e5e5e5", "texte": "#0d0d0d", "secondaire": "#5d5d5d",
    "faible": "#6b6b6b", "danger": "#c4262e", "attente": "#c2410c", "regle": "#0f7b55",
    "police": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
}


def _e(texte) -> str:
    return html.escape(html.unescape(str(texte if texte is not None else "")), quote=True)


def _dt(iso) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def jour(d: datetime) -> str:
    local = d.astimezone()
    return f"{JOURS[local.weekday()].capitalize()} {local.day}{'er' if local.day == 1 else ''}"


def periode(debut: datetime, fin: datetime) -> str:
    a, b = debut.astimezone(), fin.astimezone()
    if a.month == b.month:
        return f"du {JOURS[a.weekday()]} {a.day} au {JOURS[b.weekday()]} {b.day} {MOIS[b.month - 1]} {b.year}"
    return (f"du {JOURS[a.weekday()]} {a.day} {MOIS[a.month - 1]} au {JOURS[b.weekday()]} {b.day} "
            f"{MOIS[b.month - 1]} {b.year}")


def _pluriel(n: int, un: str, plusieurs: str) -> str:
    return f"{n} {un if n <= 1 else plusieurs}"


# ---------------------------------------------------------------- Ce que la semaine contient
def _phrase_dossier(detail: dict) -> str:
    """Une phrase : le jour, ce qui s'est passé, ce que Dédale ou un humain a fait."""
    moments = [m for m in (_dt(x.get("horodatage")) for x in detail.get("chaine") or []) if m]
    d = min(moments) if moments else _dt(detail.get("cree_a"))
    quand = jour(d) if d else "Cette semaine"
    quoi = notifications.quoi(detail)
    issue = notifications.issue(detail)
    return f"{quand}, {quoi[0].lower()}{quoi[1:].rstrip('.')} ; {issue[0].lower()}{issue[1:]}"


_ISSUES_METIER = {
    "accorde": "le responsable l'a confirmé.",
    "refuse": "le responsable l'a refusé et il n'a pas eu lieu.",
    None: "le responsable n'a pas encore décidé.",
}


def _validations(store, debut: datetime, fin: datetime) -> tuple[list[dict], int]:
    """Demandes de validation métier de la période (sans montant ni bénéficiaire) et nombre de
    gestes sensibles passés sans retenue."""
    from . import identites
    with store.lock:
        evs = list(store.evenements.values())
        sessions = dict(store.sessions)
    decisions = {(e.get("details") or {}).get("demande_id"): (e.get("details") or {}).get("verdict")
                 for e in evs if e.get("type") == "validation_decidee" and e.get("user_agent") == "dedale-relecteur"}
    sortie, passes = [], 0
    for e in evs:
        h = _dt(e.get("horodatage"))
        if h is None or not (debut <= h <= fin) or e.get("user_agent") != "dedale-relecteur":
            continue
        d = e.get("details") or {}
        if e.get("type") == "geste_verifie" and d.get("issue") in ("passe", "accorde"):
            passes += 1
        if e.get("type") != "validation_demandee":
            continue
        geste = notifications.GESTES.get(d.get("geste"), "un geste sensible")
        sess = sessions.get(e.get("session_id") or "")
        evs_sess = [x for x in evs if sess and x.get("id") in set(sess.evenement_ids)]
        service = identites.identite(e.get("session_id") or "", evs_sess).get("service")
        par = f" demandé par le service {service}" if service else ""
        verdict = decisions.get(d.get("demande_id"))
        sortie.append({"demande_id": d.get("demande_id"), "verdict": verdict,
                       "phrase": f"{jour(h)}, {geste}{par} a attendu la confirmation de son responsable ; "
                                 f"{_ISSUES_METIER.get(verdict, _ISSUES_METIER[None])}"})
    return sortie, passes


def _liste(elements: list[str]) -> str:
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " et " + elements[-1]


def _phrase_agent(fiche: dict, dossiers: int) -> str:
    """Une phrase par agent : ses dossiers de la semaine, ses droits en trop, et quoi faire."""
    libelle = str(fiche.get("libelle") or fiche.get("nom") or "un agent")
    sujet = libelle[0].upper() + libelle[1:]
    raisons = (fiche.get("risque") or {}).get("raisons") or []
    trop = next((r for r in raisons if r.get("code") == "droits_en_trop"), None)
    morceaux = []
    if dossiers:
        morceaux.append(f"a ouvert {_pluriel(dossiers, 'dossier', 'dossiers')} cette semaine")
    if trop:
        texte = str(trop.get("texte") or "").rstrip(".")
        nombre, _, detail = texte.partition(", dont ")
        droits = [d.strip() for d in re.split(r",\s*|\s+et\s+", detail) if d.strip()]
        reste = ", entre autres" if len(droits) > 3 else ""
        precision = f" ({_liste(droits[:3])}{reste})" if droits else ""
        morceaux.append(f"garde {nombre.replace(' en trop pour son travail', '')} dont il n'a pas besoin{precision}")
    if not morceaux:
        return f"{sujet} n'a jamais été testé face à un contenu piégé : lancez un test depuis la console."
    conseil = " : retirez-les dans la console, page Agents" if trop else ""
    return f"{sujet} {' et '.join(morceaux)}{conseil}."


_EFFETS = {
    "bloquer": ("a bloqué", "appel", "appels"),
    "retenir": ("a retenu", "appel pour un analyste", "appels pour un analyste"),
    "droit_retire": ("a arrêté", "tentative d'un agent privé de ce droit", "tentatives d'un agent privé de ce droit"),
    "alerter": ("a donné l'alerte sur", "appel", "appels"),
}


def _phrase_regle(regle: dict) -> str:
    verbe, un, plusieurs = _EFFETS.get(regle["effet"], _EFFETS["alerter"])
    nom = f"La règle n°{regle['numero']}" if regle.get("numero") else "Une règle de l'équipe sécurité"
    texte = f", « {regle['texte']} »," if regle.get("texte") else ""
    return f"{nom}{texte} {verbe} {_pluriel(regle['fois'], un, plusieurs)}."


def collecter(store, debut: datetime, fin: datetime) -> dict:
    """Les points du résumé, calculés sur l'état du backend (pseudonymisé)."""
    with store.lock:
        brut = list(store.incidents.values())
        sessions = list(store.sessions.values())
    details = []
    for inc in brut:
        if not (debut <= inc.cree_a <= fin):
            continue
        d = notifications.detail_complet(inc.id)
        if d is None or d.get("source") == "externe" and d.get("gravite") == "faible":
            continue
        details.append(d)
    details.sort(key=lambda d: d.get("cree_a") or "")
    # Un geste au signal de fraude ouvre un dossier : c'est une menace arrêtée, racontée avec son
    # geste. Un geste retenu sans fraude est réglé avec le responsable, hors de la console.
    menaces = [d for d in details if d.get("type") != "humain_signalement"
               and _RANG.get(d.get("gravite") or "moyenne", 2) >= 2]
    validations, passes = _validations(store, debut, fin)
    gestes_fraude = [d for d in details if notifications._est_geste(d)]
    signalements = [d for d in details if d.get("type") == "humain_signalement"]
    a_trancher = [d for d in details if d.get("statut") == "ouvert"
                  and notifications.regle_pour(d)[0] != "personne"]
    attente_metier = [v for v in validations if v["verdict"] is None]
    # Agents : le registre et ce que la passerelle a vu ; seuls ceux qui méritent un regard.
    par_agent: dict[str, int] = {}
    for s in sessions:
        if s.source == "interne" and s.agent:
            n = sum(1 for d in details if d.get("session_id") == s.id)
            par_agent[s.agent] = par_agent.get(s.agent, 0) + n
    agents = []
    for f in inventaire.lister(store):
        if not str(f.get("id") or "").startswith("orbis-"):
            continue  # l'agent des règles de Dédale n'est pas un agent de l'entreprise
        niveau = (f.get("risque") or {}).get("niveau")
        if niveau in ("eleve", "moyen") or par_agent.get(f["id"]):
            agents.append({"id": f["id"], "nom": f.get("nom"), "niveau": niveau,
                           "phrase": _phrase_agent(f, par_agent.get(f["id"], 0))})
    agents.sort(key=lambda a: {"eleve": 0, "moyen": 1}.get(a["niveau"], 2))
    # Règles du SOC déclenchées pendant la période.
    regles: dict[str, dict] = {}
    for s in sessions:
        for r in s.regles_declenchees:
            h = _dt(r.get("horodatage"))
            if h is None or not (debut <= h <= fin):
                continue
            cle = str(r.get("id") or r.get("numero"))
            entree = regles.setdefault(cle, {"numero": r.get("numero"), "texte": r.get("texte"),
                                             "effet": r.get("effet") or "alerter", "fois": 0})
            entree["fois"] += 1
    return {
        "debut": debut.isoformat(), "fin": fin.isoformat(), "periode": periode(debut, fin),
        "chiffres": {"menaces": len(menaces), "gestes": len(validations) + len(gestes_fraude) + passes,
                     "gestes_retenus": len(validations), "gestes_fraude": len(gestes_fraude),
                     "gestes_passes": passes, "a_trancher": len(a_trancher) + len(attente_metier),
                     "agents": len(agents), "signalements": len(signalements)},
        "menaces": [{"id": d["id"], "gravite": d.get("gravite"), "phrase": _phrase_dossier(d)}
                    for d in sorted(menaces, key=lambda d: -_RANG.get(d.get("gravite") or "", 2))],
        "gestes": validations,
        "gestes_passes": passes,
        "agents": agents,
        "regles": [{**r, "phrase": _phrase_regle(r)} for r in sorted(regles.values(), key=lambda r: -r["fois"])],
        "a_trancher": [d["id"] for d in a_trancher],
        "attente_metier": len(attente_metier),
        "signalements": len(signalements),
    }


# ---------------------------------------------------------------- Rendu HTML
def _point(couleur: str) -> str:
    return (f'<span style="display:inline-block;width:6px;height:6px;border-radius:3px;background:{couleur};'
            f'margin:0 8px 2px 0;vertical-align:middle"></span>')


def _section(titre: str, lignes: list[str], vide: str, couleur: str, reste: int = 0) -> str:
    corps = []
    if not lignes:
        corps.append(f'<p style="margin:0;color:{C["secondaire"]};font-size:14px;line-height:21px">{_e(vide)}</p>')
    for ligne in lignes:
        corps.append(f'<p style="margin:0 0 10px 0;font-size:14px;line-height:21px;color:{C["texte"]}">'
                     f'{_point(couleur)}{_e(ligne)}</p>')
    if reste > 0:
        corps.append(f'<p style="margin:0;font-size:13px;color:{C["faible"]}">'
                     f'Et {_pluriel(reste, "autre dossier", "autres dossiers")}, à lire dans la console.</p>')
    return (f'<tr><td style="padding:0 0 12px 0"><table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="background:{C["carte"]};border:1px solid {C["bord"]};border-radius:20px">'
            f'<tr><td style="padding:20px 24px">'
            f'<h2 style="margin:0 0 12px 0;font-size:15px;line-height:20px;font-weight:600;color:{C["texte"]}">'
            f'{_e(titre)}</h2>{"".join(corps)}</td></tr></table></td></tr>')


def _chiffre(valeur: int, libelle: str, couleur: str) -> str:
    return (f'<td width="25%" style="padding:16px 8px;text-align:center;vertical-align:top">'
            f'<div style="font-size:28px;line-height:32px;font-weight:600;color:{couleur};'
            f'font-variant-numeric:tabular-nums">{valeur}</div>'
            f'<div style="font-size:12px;line-height:16px;color:{C["secondaire"]};margin-top:4px">{_e(libelle)}</div></td>')


def phrase_ouverture(r: dict) -> str:
    c = r["chiffres"]
    if not (c["menaces"] or c["gestes_retenus"] or c["a_trancher"]):
        return "Semaine calme : sAIfe n'a rien arrêté et rien n'attend votre décision."
    morceaux = []
    if c["menaces"]:
        morceaux.append(f"sAIfe a relevé {_pluriel(c['menaces'], 'menace', 'menaces')}")
    if c["gestes_retenus"]:
        morceaux.append(f"fait confirmer {_pluriel(c['gestes_retenus'], 'geste sensible', 'gestes sensibles')} "
                        "par un responsable")
    phrase = (", ".join(morceaux[:-1]) + " et " + morceaux[-1]) if len(morceaux) > 1 else morceaux[0]
    if c["a_trancher"]:
        phrase += f". {_pluriel(c['a_trancher'], 'dossier attend', 'dossiers attendent')} encore une décision"
    else:
        phrase += ". Rien n'attend votre décision"
    return phrase + "."


def rendre(r: dict, lien_console: str) -> str:
    c = r["chiffres"]
    menaces = [m["phrase"] for m in r["menaces"]]
    gestes = [g["phrase"] for g in r["gestes"]]
    if r["gestes_passes"]:
        gestes.append(f"{_pluriel(r['gestes_passes'], 'autre geste sensible est passé', 'autres gestes sensibles sont passés')}"
                      " sans retenue.")
    agents = [a["phrase"] for a in r["agents"]]
    regles = [x["phrase"] for x in r["regles"]]
    morceaux = []
    if r["a_trancher"]:
        morceaux.append(f"{_pluriel(len(r['a_trancher']), 'dossier attend', 'dossiers attendent')} "
                        "une décision dans la console")
    if r["attente_metier"]:
        morceaux.append(f"{_pluriel(r['attente_metier'], 'geste attend', 'gestes attendent')} "
                        "celle d'un responsable")
    a_faire = (" et ".join(morceaux) + ".") if morceaux else "Rien n'attend votre décision."
    a_faire = a_faire[0].upper() + a_faire[1:]
    sections = "".join([
        _section("Les menaces, arrêtées ou à suivre", menaces[:_MAX_LIGNES], "Aucune menace cette semaine.", C["danger"],
                 len(menaces) - _MAX_LIGNES),
        _section("Les gestes retenus et leur issue", gestes[:_MAX_LIGNES],
                 "Aucun virement ni export n'a demandé de double validation.", C["attente"], len(gestes) - _MAX_LIGNES),
        _section("Les agents IA à surveiller", agents[:_MAX_LIGNES], "Aucun agent ne demande d'attention.",
                 C["attente"], len(agents) - _MAX_LIGNES),
        _section("Les règles qui ont joué", regles[:_MAX_LIGNES],
                 "Aucune règle de l'équipe sécurité n'a eu à intervenir.", C["regle"], len(regles) - _MAX_LIGNES),
    ])
    signalements = ""
    if r["signalements"]:
        signalements = (f'<p style="margin:12px 0 0 0;font-size:13px;line-height:19px;color:{C["secondaire"]}">'
                        f'{_e(_pluriel(r["signalements"], "salarié a signalé", "salariés ont signalé"))} un mail suspect. '
                        f'Merci à eux : c\'est le bon réflexe.</p>')
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>sAIfe, votre semaine</title>
</head>
<body style="margin:0;padding:0;background:{C['fond']};font-family:{C['police']};color:{C['texte']}">
<div style="display:none;max-height:0;overflow:hidden">{_e(phrase_ouverture(r))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{C['fond']}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="padding:0 4px 20px 4px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:15px;font-weight:400;letter-spacing:-0.01em">
<span style="display:inline-block;width:22px;height:22px;border-radius:6px;background:{C['texte']};vertical-align:middle;margin-right:8px"></span>s<b style="font-weight:700">AI</b>fe</td>
<td align="right" style="font-size:12px;color:{C['faible']}">Résumé du lundi</td>
</tr></table></td></tr>
<tr><td style="padding:0 4px 20px 4px">
<h1 style="margin:0 0 6px 0;font-size:24px;line-height:30px;font-weight:600;letter-spacing:-0.02em">Votre semaine avec sAIfe</h1>
<p style="margin:0 0 12px 0;font-size:13px;color:{C['secondaire']}">Orbis Pay · {_e(r['periode'])}</p>
<p style="margin:0;font-size:15px;line-height:23px">{_e(phrase_ouverture(r))}</p>
</td></tr>
<tr><td style="padding:0 0 12px 0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{C['carte']};border:1px solid {C['bord']};border-radius:20px"><tr>
{_chiffre(c['menaces'], 'menaces relevées', C['danger'] if c['menaces'] else C['texte'])}
{_chiffre(c['gestes'], 'gestes sensibles relus', C['texte'])}
{_chiffre(c['a_trancher'], 'dossiers à trancher', C['attente'] if c['a_trancher'] else C['regle'])}
{_chiffre(c['agents'], 'agents à surveiller', C['attente'] if c['agents'] else C['texte'])}
</tr></table></td></tr>
{sections}
<tr><td style="padding:8px 4px 0 4px">
<p style="margin:0 0 16px 0;font-size:14px;line-height:21px">{_e(a_faire)}</p>
<a href="{_e(lien_console)}" style="display:inline-block;background:{C['texte']};color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 20px;border-radius:9999px">Ouvrir la console</a>
{signalements}
<p style="margin:24px 0 0 0;font-size:12px;line-height:18px;color:{C['faible']}">sAIfe · Orbis Pay, entreprise fictive · trafic de démonstration. Aperçu du mail du lundi : il n'est pas envoyé. Aucun salarié n'y est nommé et aucun montant n'y figure en chiffre exact.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def generer(store, jours: int = 7, fin: datetime | None = None) -> dict:
    fin = fin or datetime.now(timezone.utc)
    debut = fin - timedelta(days=jours)
    return collecter(store, debut, fin)


def lien_console() -> str:
    return notifications.url_console() + "/"
