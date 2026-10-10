"""Rapport d'incident en une page, HTML imprimable, pour un RSSI.

`rendre(detail, synthese, verification)` assemble ce que le backend sait déjà : la synthèse
par règles, la chronologie de la boîte noire, les décisions et leurs auteurs, l'état actuel
et le verdict du journal scellé. Tout texte dynamique est échappé ; une politique CSP stricte
n'autorise que la feuille de style intégrée et le script du bouton « Imprimer ».

Pas de PDF côté serveur : aucune bibliothèque PDF n'est installée dans le backend. La mise
en page A4 vise l'impression du navigateur (Imprimer, puis Enregistrer en PDF).
"""

from __future__ import annotations

import base64
import hashlib
import html
from datetime import datetime

# Ce qu'attend l'incident tant qu'aucune décision n'est prise (repris par alertes.py).
ATTENTE = {
    "interne": "L'agent est suspendu jusqu'à votre décision : reprendre, couper ou ignorer.",
    "externe": "La session est retenue dans le labyrinthe. Validez la riposte, coupez ou ignorez.",
    "humain": "Le poste du salarié n'est pas bloqué. Vérifiez puis close ou ignorez l'incident.",
    "physique": "Accès physique à un leurre. Vérifiez sur place puis close ou ignorez l'incident.",
}

_ACTIONS = {
    "valider_riposte": "Riposte validée",
    "couper": "Agent coupé",
    "reprendre": "Agent repris, sous surveillance",
    "ignorer": "Incident ignoré",
    "clore": "Incident clos",
}
_STATUTS = {
    "ouvert": "En attente d'une décision",
    "clos": "Clos",
    "ignore": "Ignoré",
    "surveille": "Sous surveillance",
}
_ETATS_AGENT = {
    "active": "actif",
    "suspendue": "suspendu, en attente de l'analyste",
    "coupee": "coupé",
}
_GRAVITES = {"critique": "Critique", "haute": "Haute", "moyenne": "Moyenne", "faible": "Faible"}

_MAX_LIGNES = 12

_SCRIPT = "document.getElementById('imprimer').addEventListener('click',function(){window.print()});"
_EMPREINTE_SCRIPT = base64.b64encode(hashlib.sha256(_SCRIPT.encode()).digest()).decode()
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    f"script-src 'sha256-{_EMPREINTE_SCRIPT}'; img-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _e(valeur) -> str:
    """Échappe pour le HTML. Les textes de la boîte noire sont déjà échappés une fois à
    l'ingestion : on les ramène au texte brut puis on échappe, jamais deux fois."""
    if valeur is None:
        return ""
    return html.escape(html.unescape(str(valeur)), quote=True)


def _dt(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError):
        return None


def _heure(iso) -> str:
    dt = _dt(iso)
    return dt.strftime("%H:%M:%S") if dt else "—"


def _date(iso) -> str:
    dt = _dt(iso)
    return dt.strftime("%d/%m/%Y à %H:%M") if dt else "—"


def _court(texte, n: int) -> str:
    t = html.unescape(str(texte or "")).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _n(nombre: int, singulier: str, pluriel: str) -> str:
    return f"{nombre} {singulier if nombre <= 1 else pluriel}"


def _sceau_lisible(sceau: str | None) -> str:
    if not sceau:
        return "—"
    return " ".join(sceau[i:i + 16] for i in range(0, len(sceau), 16))


# ---------------------------------------------------------------- Blocs
def _bloc_decision(detail: dict) -> str:
    decisions = detail.get("decisions") or []
    if not decisions:
        attente = ATTENTE.get(detail.get("source"), "Décision de l'analyste attendue.")
        return (
            '<p class="valeur">Aucune décision pour l\'instant</p>'
            f'<p class="note">{_e(attente)}</p>'
        )
    derniere = decisions[-1]
    lignes = [
        f'<p class="valeur">{_e(_ACTIONS.get(derniere.get("action"), derniere.get("action")))}</p>',
        f'<p class="note">par <strong>{_e(derniere.get("analyste") or "analyste inconnu")}</strong>, '
        f'le {_e(_date(derniere.get("horodatage")))}</p>',
    ]
    if len(decisions) > 1:
        avant = "; ".join(
            f"{_ACTIONS.get(d.get('action'), d.get('action'))} par {d.get('analyste') or '?'} "
            f"à {_heure(d.get('horodatage'))}"
            for d in decisions[:-1]
        )
        lignes.append(f'<p class="note">Avant : {_e(avant)}.</p>')
    return "".join(lignes)


def _bloc_etat(detail: dict) -> str:
    statut = _STATUTS.get(detail.get("statut"), detail.get("statut"))
    lignes = [f'<p class="valeur">{_e(statut)}</p>']
    if detail.get("source") in ("humain", "physique"):
        lignes.append('<p class="note">Poste du salarié : jamais bloqué par sAIfe.</p>')
    elif detail.get("etat"):
        lignes.append(f'<p class="note">Agent : {_e(_ETATS_AGENT.get(detail["etat"], detail["etat"]))}.</p>')
    for c in detail.get("correctifs") or []:
        lignes.append(
            f'<p class="note">Droit {_e(c.get("code"))} retiré par {_e(c.get("analyste"))} '
            f'à {_e(_heure(c.get("horodatage")))}.</p>'
        )
    return "".join(lignes)


def _bloc_integrite(verif: dict) -> tuple[str, str]:
    statut = verif.get("statut")
    if statut == "intacte":
        classe, titre = "ok", "Journal intact"
        note = (
            f"{_n(verif.get('maillons_verifies', 0), 'maillon', 'maillons')}, leurs événements sources et "
            f"{_n(verif.get('decisions_verifiees', 0), 'décision', 'décisions')} recalculés depuis la "
            f"base le {_date(verif.get('verifie_a'))}. Aucune différence."
        )
        if verif.get("evenements_anterieurs"):
            note += (" " + _n(verif["evenements_anterieurs"], "événement source est antérieur",
                              "événements sources sont antérieurs") + " au scellement.")
    elif statut == "alteree":
        classe = "alerte"
        titre = "Journal " + str(verif.get("verdict", "altéré")).replace("altérée", "altéré")
        note = (
            f"{_court(verif.get('raison'), 160)}. Ce qui suit ce point n'est plus garanti : "
            "comparer avec la sauvegarde ou un rapport imprimé avant."
        )
    elif statut == "anterieure_au_scellement":
        classe, titre = "neutre", "Antérieur au scellement"
        note = "Incident écrit avant la mise en place du scellement : rien à recalculer."
    else:
        classe, titre = "neutre", "Pas encore vérifiable"
        note = "L'incident n'est pas encore écrit dans le journal. Rouvrir le rapport dans un instant."
    corps = (
        f'<p class="valeur"><span class="point {classe}"></span>{_e(titre)}</p>'
        f'<p class="note">{_e(note)}</p>'
        f'<p class="sceau" title="Sceau SHA-256 de l\'incident">{_e(_sceau_lisible(verif.get("sceau")))}</p>'
    )
    return classe, corps


def _chronologie(chaine: list[dict]) -> str:
    etapes = sorted(chaine or [], key=lambda e: e.get("ordre", 0))
    if not etapes:
        return '<p class="note">Aucun maillon enregistré.</p>'
    if len(etapes) > _MAX_LIGNES:
        # Une page : les cinq premiers maillons, une ligne de coupe, puis les derniers.
        visibles = etapes[:5] + [None] + etapes[-(_MAX_LIGNES - 6):]
        coupe = len(etapes) - (len(visibles) - 1)
    else:
        visibles, coupe = etapes, 0
    lignes = []
    for e in visibles:
        if e is None:
            lignes.append(
                f'<tr class="ellipse"><td></td><td colspan="2">{coupe} maillons intermédiaires, '
                "visibles dans la console</td></tr>"
            )
            continue
        rang = (e.get("sceau") or {}).get("rang") or (e.get("ordre", 0) + 1)
        lignes.append(
            "<tr>"
            f'<td class="heure">{_e(_heure(e.get("horodatage")))}</td>'
            f'<td class="etape"><span class="rang">{_e(rang)}</span>{_e(e.get("titre") or e.get("etape"))}</td>'
            f'<td>{_e(_court(e.get("detail") or e.get("resume"), 170))}</td>'
            "</tr>"
        )
    return (
        '<table class="chrono"><thead><tr><th>Heure</th><th>Étape</th><th>Ce qui s\'est passé</th>'
        f'</tr></thead><tbody>{"".join(lignes)}</tbody></table>'
    )


def _annexe(detail: dict, verif: dict) -> str:
    chaine = detail.get("chaine") or []
    techniques = sorted({t.get("id") for e in chaine for t in (e.get("techniques") or []) if t.get("id")})
    risques = sorted({r.get("id") for e in chaine for r in (e.get("risques") or []) if r.get("id")})
    evenements = [e.get("evenement_id") for e in chaine if e.get("evenement_id") is not None]
    score = detail.get("score")
    lignes = [
        ("Incident", f"{detail.get('id')} · type {detail.get('type')}"),
        ("Session", detail.get("session_id")),
        ("Classement", f"{detail.get('classement')} (score {score:.2f})" if isinstance(score, (int, float))
         else detail.get("classement")),
        ("Leurres touchés", ", ".join(detail.get("leurres_touches") or []) or "aucun"),
        ("Techniques ATT&CK", ", ".join(techniques) or "aucune"),
        ("Risques OWASP", ", ".join(risques) or "aucun"),
        ("Événements sources", f"{len(evenements)} (n° {min(evenements)} à {max(evenements)})"
         if evenements else "aucun"),
        ("Scellement", f"{verif.get('algorithme', 'SHA-256')}, chaîne par maillon, "
         "sceau d'incident sur en-tête, boîte noire et décisions"),
        ("Vérification", "GET /api/incidents/{id}/verification ; uv run python -m app.verifier_journal"),
    ]
    return "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in lignes)


# ---------------------------------------------------------------- Page
_STYLE = """
:root{--fond:#f4f5f7;--plateau:#eceef1;--feuille:#fff;--encre:#0b1220;--doux:#424b57;
--faible:#5b6474;--trait:rgba(15,23,42,.09);--ok:#15803d;--alerte:#b42318;--ambre:#b45309;
--neutre:#64748b;--sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--fond);color:var(--encre);font:14px/1.5 var(--sans);
-webkit-font-smoothing:antialiased;padding:40px 16px 64px}
.plateau{max-width:210mm;margin:0 auto;padding:8px;border-radius:30px;background:var(--plateau);
box-shadow:0 0 0 1px rgba(15,23,42,.05)}
.feuille{background:var(--feuille);border-radius:22px;padding:44px 48px 36px;
box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 24px 56px -28px rgba(15,23,42,.18)}
.barre{display:flex;justify-content:flex-end;max-width:210mm;margin:0 auto 14px}
button{font:500 13px/1 var(--sans);color:var(--encre);background:var(--feuille);border:0;
border-radius:999px;padding:10px 10px 10px 18px;display:inline-flex;align-items:center;gap:10px;
box-shadow:0 0 0 1px var(--trait),0 6px 18px -10px rgba(15,23,42,.25);cursor:pointer;
transition:transform .5s cubic-bezier(.32,.72,0,1)}
button:active{transform:scale(.98)}
button span{width:24px;height:24px;border-radius:999px;background:var(--fond);display:grid;
place-items:center;font-size:12px;transition:transform .5s cubic-bezier(.32,.72,0,1)}
button:hover span{transform:translateY(1px)}
header{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.surtitre{color:var(--faible);font-size:13px}
h1{font-size:23px;line-height:1.25;font-weight:650;letter-spacing:-.01em;margin:4px 0 6px}
.meta{color:var(--doux);font-size:13px}
.pastilles{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0}
.pastille{font-size:12px;font-weight:550;border-radius:999px;padding:4px 12px;background:var(--fond);
color:var(--doux);white-space:nowrap}
.pastille.critique{background:#fdecea;color:var(--alerte)}
.pastille.haute{background:#fdf1e4;color:var(--ambre)}
h2{font-size:13px;font-weight:600;color:var(--faible);margin:0 0 8px}
section{margin-top:26px}
.recit{font-size:15.5px;line-height:1.55;color:var(--encre)}
.cartes{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.carte{background:var(--fond);border-radius:18px;padding:16px 18px}
.carte .valeur{font-weight:600;font-size:14.5px;display:flex;align-items:center;gap:8px}
.note{color:var(--doux);font-size:12.5px;margin-top:4px}
.point{width:8px;height:8px;border-radius:999px;background:var(--neutre);flex-shrink:0}
.point.ok{background:var(--ok)}.point.alerte{background:var(--alerte)}
.carte.alerte{background:#fdecea}
.sceau{font-family:var(--mono);font-size:10.5px;color:var(--faible);margin-top:8px;
word-break:break-all;line-height:1.45}
table.chrono{width:100%;border-collapse:collapse;font-size:12.5px}
.chrono th{text-align:left;font-weight:550;color:var(--faible);padding:0 10px 6px 0}
.chrono td{padding:7px 10px 7px 0;border-top:1px solid var(--trait);vertical-align:top;color:var(--doux)}
.chrono td.heure{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--faible);width:64px}
.chrono td.etape{white-space:nowrap;color:var(--encre);font-weight:550;width:150px}
.rang{display:inline-block;min-width:20px;color:var(--faible);font-weight:500}
.ellipse td{color:var(--faible);font-style:italic}
.limites p{color:var(--doux);font-size:12.5px;margin-top:4px}
.annexe{margin-top:26px;padding-top:14px;border-top:1px solid var(--trait)}
.annexe h2{font-size:11.5px}
.annexe dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;font-size:11px;color:var(--faible)}
.annexe dt{font-weight:550}
.annexe dd{word-break:break-word}
@media (max-width:720px){body{padding:16px 12px 40px}.feuille{padding:26px 20px}
header{flex-direction:column}.pastilles{flex-direction:row;align-items:flex-start}
.cartes{grid-template-columns:1fr}.chrono td.etape{white-space:normal;width:auto}}
@media (min-width:721px){.annexe dl{grid-template-columns:max-content 1fr max-content 1fr}}
@page{size:A4;margin:10mm 12mm}
@media print{body{background:#fff;padding:0;font-size:10.5px;line-height:1.4}.barre{display:none}
.plateau{max-width:none;padding:0;background:none;box-shadow:none;border-radius:0}
.feuille{padding:0;box-shadow:none;border-radius:0}
h1{font-size:18px;margin:2px 0 3px}.surtitre,.meta{font-size:10.5px}h2{font-size:10.5px;margin-bottom:5px}
section{margin-top:12px}.recit{font-size:11.5px;line-height:1.45}
.cartes{gap:8px}.carte{border:1px solid var(--trait);background:#fff;border-radius:12px;padding:9px 12px}
.carte.alerte{background:#fff;border-color:var(--alerte)}.carte .valeur{font-size:12px}
.note{font-size:10px;margin-top:2px}.sceau{font-size:8.5px;margin-top:5px}
table.chrono{font-size:10px}.chrono td{padding:4px 8px 4px 0}.chrono th{padding-bottom:3px}
.chrono td.heure{width:52px}.chrono td.etape{white-space:normal;width:150px}
.chrono tr{break-inside:avoid}.limites p{font-size:9.5px;margin-top:2px}
.annexe{margin-top:12px;padding-top:8px}.annexe h2{font-size:9.5px}
.annexe dl{grid-template-columns:max-content 1fr max-content 1fr;font-size:8.5px;gap:1px 10px}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def rendre(detail: dict, synthese: dict | None, verification: dict) -> str:
    iid = detail.get("id")
    gravite = detail.get("gravite") or "moyenne"
    recit = (synthese or {}).get("texte") or detail.get("resume") or "Synthèse indisponible."
    classe_integrite, integrite = _bloc_integrite(verification)
    source = detail.get("source")
    perimetre = {
        "interne": "Agent IA interne",
        "externe": "Surface exposée",
        "humain": "Poste d'un salarié",
        "physique": "Accès physique",
    }.get(source, "Incident")
    ouvert = _date(detail.get("ouvert_le") or detail.get("cree_a"))
    edite = _date(verification.get("verifie_a"))
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport {_e(iid)}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="barre"><button id="imprimer" type="button">Imprimer ou enregistrer en PDF<span>↓</span></button></div>
<div class="plateau"><main class="feuille">
<header>
  <div>
    <p class="surtitre">Rapport d'incident {_e(iid)} · {_e(perimetre)}</p>
    <h1>{_e(detail.get("titre"))}</h1>
    <p class="meta">Ouvert le {_e(ouvert)} · Orbis Pay, entreprise fictive · édité le {_e(edite)}</p>
  </div>
  <div class="pastilles">
    <span class="pastille {_e(gravite)}">Gravité {_e(_GRAVITES.get(gravite, gravite).lower())}</span>
    <span class="pastille">{_e(_STATUTS.get(detail.get("statut"), detail.get("statut")))}</span>
  </div>
</header>

<section>
  <h2>Ce qui s'est passé</h2>
  <p class="recit">{_e(recit)}</p>
</section>

<section class="cartes">
  <div class="carte"><h2>Décision humaine</h2>{_bloc_decision(detail)}</div>
  <div class="carte"><h2>État actuel</h2>{_bloc_etat(detail)}</div>
  <div class="carte {_e(classe_integrite)}"><h2>Intégrité du journal</h2>{integrite}</div>
</section>

<section>
  <h2>Chronologie (heures locales)</h2>
  {_chronologie(detail.get("chaine") or [])}
</section>

<section class="limites">
  <h2>Limites</h2>
  <p>Trafic de démonstration. Orbis Pay est une entreprise fictive ; les sessions viennent du banc
  de mesure ou du scénario de démonstration, sans donnée réelle.</p>
  <p>La synthèse est écrite par des règles à partir des maillons ci-dessus, sans modèle de langage.
  Elle ne décrit que ce que sAIfe a observé.</p>
  <p>Le sceau prouve que le journal n'a pas changé depuis son écriture par sAIfe. Une nouvelle
  décision ou un nouvel événement le fait évoluer. Une base entièrement réécrite, sceaux recalculés
  compris, ne se repère qu'en comparant avec un sceau imprimé avant, comme celui de ce rapport.</p>
</section>

<section class="annexe">
  <h2>Annexe technique</h2>
  <dl>{_annexe(detail, verification)}</dl>
</section>
</main></div>
<script>{_SCRIPT}</script>
</body>
</html>
"""
