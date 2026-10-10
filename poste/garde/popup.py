"""La pop-up d'avertissement : rendu terminal et page HTML de démonstration.

Le texte affiché est une donnée inerte : il est échappé (HTML) et jamais
réexécuté. La page HTML montre la fenêtre par-dessus une maquette du poste du
salarié, pour une démo filmable sans dépendance.
"""

from __future__ import annotations

import html

from .detection import Verdict

_GRAVITE_COULEUR = {
    "faible": "#2e7d32",
    "moyenne": "#b26a00",
    "haute": "#c62828",
    "critique": "#7b1020",
}


# --- rendu terminal ------------------------------------------------------------

def rendu_terminal(verdict: Verdict, largeur: int = 68) -> str:
    """Encadré lisible pour la démo au terminal."""
    def lignes(texte: str) -> list[str]:
        out: list[str] = []
        for para in texte.split("\n"):
            mot_courant = ""
            for mot in para.split(" "):
                if len(mot_courant) + len(mot) + 1 > largeur - 4:
                    out.append(mot_courant)
                    mot_courant = mot
                else:
                    mot_courant = (mot_courant + " " + mot).strip()
            out.append(mot_courant)
        return out

    bord = "─" * (largeur - 2)
    haut = "┌" + bord + "┐"
    bas = "└" + bord + "┘"
    sep = "├" + bord + "┤"

    def ligne(txt: str) -> str:
        return "│ " + txt.ljust(largeur - 4) + " │"

    corps = [haut, ligne("⚠  DÉDALE — garde du corps du poste"),
             ligne("gravité : " + verdict.gravite + "   règle : " + verdict.regle), sep]
    for l in lignes(verdict.titre):
        corps.append(ligne(l))
    corps.append(ligne(""))
    for l in lignes(verdict.explication):
        corps.append(ligne(l))
    corps.append(ligne(""))
    corps.append(ligne(verdict.preuve))
    corps.append(sep)
    corps.append(ligne("[ Continuer quand même ]      [ Annuler (recommandé) ]"))
    corps.append(bas)
    return "\n".join(corps)


# --- page HTML -----------------------------------------------------------------

def _carte_html(verdict: Verdict, choix: str | None) -> str:
    coul = _GRAVITE_COULEUR.get(verdict.gravite, "#b26a00")
    etat = ""
    if choix == "annuler":
        etat = '<p class="etat ok">Le salarié a annulé — l\'incident a été évité.</p>'
    elif choix == "continuer":
        etat = '<p class="etat ko">Le salarié est passé outre — incident remonté au SOC.</p>'
    return f"""      <div class="popup" style="--grav:{coul}">
        <div class="entete"><span class="ico">⚠</span>
          <div><strong>DÉDALE — garde du corps</strong>
          <span class="meta">gravité {html.escape(verdict.gravite)} · règle {html.escape(verdict.regle)}</span></div>
        </div>
        <p class="titre">{html.escape(verdict.titre)}</p>
        <p class="expli">{html.escape(verdict.explication)}</p>
        <pre class="preuve">{html.escape(verdict.preuve)}</pre>
        <div class="boutons">
          <button class="continuer">Continuer quand même</button>
          <button class="annuler">Annuler</button>
        </div>
        {etat}
      </div>"""


def page_html(cartes: list[tuple[Verdict, str | None]], titre: str = "Dédale — poste du salarié") -> str:
    """Page autonome : la pop-up par-dessus une maquette d'écran. Tout est échappé."""
    popups = "\n".join(_carte_html(v, c) for v, c in cartes)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titre)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, system-ui, "Segoe UI", Roboto, sans-serif;
         background: #0f172a; color: #0f172a; }}
  .ecran {{ position: relative; min-height: 100vh; padding: 16px;
           background:
             radial-gradient(1200px 600px at 70% -10%, #1e293b, #0f172a);
           overflow: hidden; }}
  .barre {{ height: 34px; background: #e2e8f0; border-radius: 8px 8px 0 0;
           display: flex; align-items: center; gap: 8px; padding: 0 12px; max-width: 960px; margin: 24px auto 0; }}
  .barre span {{ width: 11px; height: 11px; border-radius: 50%; background: #cbd5e1; }}
  .fenetre {{ max-width: 960px; margin: 0 auto; background: #f8fafc; border-radius: 0 0 8px 8px;
             min-height: 420px; padding: 28px 32px; filter: blur(0.4px); }}
  .fenetre h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .fenetre p.sous {{ color: #64748b; margin: 0 0 20px; }}
  .champ {{ background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px;
           color: #94a3b8; margin-bottom: 12px; }}
  .popups {{ position: relative; max-width: 960px; margin: -360px auto 0;
            display: flex; flex-wrap: wrap; gap: 18px; justify-content: center; z-index: 5; padding: 0 8px 40px; }}
  .popup {{ width: 420px; background: #fff; border-radius: 14px; overflow: hidden;
           box-shadow: 0 24px 60px rgba(2,6,23,.55); border-top: 6px solid var(--grav); }}
  .entete {{ display: flex; gap: 12px; align-items: center; padding: 16px 18px 6px; }}
  .entete .ico {{ font-size: 26px; }}
  .entete .meta {{ display: block; color: #64748b; font-size: 12px; }}
  .titre {{ font-weight: 650; padding: 4px 18px 0; margin: 6px 0; font-size: 16px; }}
  .expli {{ padding: 0 18px; color: #334155; margin: 6px 0 12px; font-size: 14px; line-height: 1.45; }}
  .preuve {{ margin: 0 18px 14px; background: #f1f5f9; border-radius: 8px; padding: 10px 12px;
            font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12.5px; color: #475569;
            white-space: pre-wrap; word-break: break-word; }}
  .boutons {{ display: flex; gap: 10px; padding: 0 18px 16px; }}
  .boutons button {{ flex: 1; padding: 10px; border-radius: 9px; border: 0; font-size: 14px; cursor: default; }}
  .continuer {{ background: #e2e8f0; color: #334155; }}
  .annuler {{ background: var(--grav); color: #fff; font-weight: 600; }}
  .etat {{ margin: 0; padding: 10px 18px 16px; font-size: 13px; font-weight: 600; }}
  .etat.ok {{ color: #15803d; }}
  .etat.ko {{ color: #b91c1c; }}
  footer {{ text-align: center; color: #64748b; font-size: 12px; padding: 16px; }}
</style>
</head>
<body>
  <div class="ecran">
    <div class="barre"><span></span><span></span><span></span></div>
    <div class="fenetre">
      <h1>Orbis Pay — poste de Camille (démonstration)</h1>
      <p class="sous">Tout est fictif et local. Le garde du corps intercepte le geste avant qu'il n'aboutisse.</p>
      <div class="champ">Coller un message…</div>
      <div class="champ">À : …</div>
      <div class="champ">Joindre un fichier…</div>
    </div>
    <div class="popups">
{popups}
    </div>
    <footer>Dédale · avenant « humain, le maillon faible » · {html.escape(titre)}</footer>
  </div>
</body>
</html>"""
