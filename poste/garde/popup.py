"""La pop-up d'avertissement : rendu terminal et page HTML de démonstration.

Le texte affiché est une donnée inerte : il est échappé (HTML) et jamais
réexécuté. La page HTML montre la fenêtre du garde du corps par-dessus deux
scènes du poste de Camille — un mail frauduleux ouvert, un lien piégé cliqué
en naviguant — pour une démo filmable sans dépendance.
"""

from __future__ import annotations

import html
from urllib.parse import urlsplit

from . import actions
from .detection import Verdict

_esc = html.escape

# Pastille de gravité (un point coloré) ; l'accent du système reste le cyan.
_GRAVITE_COULEUR = {
    "faible": "#34D399",
    "moyenne": "#FBBF24",
    "haute": "#FB923C",
    "critique": "#F87171",
}

_ICONE_BOUCLIER = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/>'
    '<path d="M9.5 12l1.8 1.8L15 10.3"/></svg>'
)


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

    corps = [haut, ligne("DÉDALE — garde du corps du poste"),
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


# --- fragments HTML ------------------------------------------------------------

def _hote(url: str) -> str:
    parts = urlsplit(url if "://" in (url or "") else "http://" + (url or ""))
    return (parts.hostname or url or "").lower()


def _popup_html(verdict: Verdict) -> str:
    """La fenêtre du garde du corps, en verre. Tout est échappé."""
    coul = _GRAVITE_COULEUR.get(verdict.gravite, "#FBBF24")
    return f"""<div class="garde" style="--grav:{coul}">
          <div class="garde-tete">
            <span class="garde-ico">{_ICONE_BOUCLIER}</span>
            <div class="garde-id">
              <span class="garde-nom">Dédale · garde du corps</span>
              <span class="garde-meta"><span class="dot"></span>gravité {_esc(verdict.gravite)} · {_esc(verdict.regle)}</span>
            </div>
          </div>
          <p class="garde-titre">{_esc(verdict.titre)}</p>
          <p class="garde-expli">{_esc(verdict.explication)}</p>
          <p class="garde-preuve">{_esc(verdict.preuve)}</p>
          <div class="garde-boutons">
            <button class="b-annuler">Annuler</button>
            <button class="b-continuer">Continuer quand même</button>
          </div>
        </div>"""


def _issues_html(choix: str | None) -> str:
    """Les deux issues du geste, celle qui s'est produite étant marquée."""
    fait_annuler = " est-arrive" if choix == "annuler" else ""
    fait_continuer = " est-arrive" if choix == "continuer" else ""
    return f"""<div class="issues">
          <div class="issue ok{fait_annuler}">
            <span class="issue-tag">Annuler</span>
            <p>Camille revient en arrière. Rien ne part, le geste est protégé.</p>
          </div>
          <div class="issue ko{fait_continuer}">
            <span class="issue-tag">Continuer</span>
            <p>Le geste passe. Un incident remonte au SOC avec son contexte.</p>
          </div>
        </div>"""


def _scene_mail(geste: actions.Geste, verdict: Verdict, choix: str | None) -> str:
    de_nom = _esc(geste.expediteur_affiche or geste.expediteur or "Expéditeur inconnu")
    de_adr = _esc(geste.expediteur or "")
    objet = _esc(geste.objet or "(sans objet)")
    lien = verdict.details.get("lien") or geste.lien or ""
    hote = _esc(_hote(lien)) if lien else "lien externe"
    return f"""<section class="scene">
      <div class="scene-tete">
        <span class="pastille">01 · mail reçu</span>
        <h2>Au moment où elle ouvre le mail</h2>
        <p class="scene-sous">Le garde du corps lit l'expéditeur et le lien avant qu'un seul clic ne parte.</p>
      </div>
      <div class="poste">
        <div class="app mail">
          <div class="chrome"><span class="feu r"></span><span class="feu o"></span><span class="feu v"></span>
            <span class="chrome-titre">Courrier — Boîte de réception</span></div>
          <div class="mail-corps">
            <aside class="mail-rail">
              <span class="rail-item actif">Réception <b>1</b></span>
              <span class="rail-item">Envoyés</span>
              <span class="rail-item">Brouillons</span>
              <span class="rail-item">Archives</span>
            </aside>
            <div class="mail-lecture">
              <p class="mail-objet">{objet}</p>
              <p class="mail-de"><b>{de_nom}</b> <span class="mail-adr">&lt;{de_adr}&gt;</span></p>
              <p class="mail-texte">Bonjour Camille, votre accès sera suspendu sous 24 h.
                 Pour le garder, confirmez vos identifiants.</p>
              <span class="mail-lien">Réactiver mon accès — {hote}</span>
            </div>
          </div>
        </div>
        <div class="voile">
          {_popup_html(verdict)}
        </div>
      </div>
      {_issues_html(choix)}
    </section>"""


def _scene_web(geste: actions.Geste, verdict: Verdict, choix: str | None) -> str:
    hote = _esc(verdict.details.get("hote") or _hote(geste.url))
    return f"""<section class="scene">
      <div class="scene-tete">
        <span class="pastille">02 · navigation web</span>
        <h2>Au moment où elle clique le lien</h2>
        <p class="scene-sous">Un résultat sponsorisé qui imite la page de connexion. Le garde du corps le voit avant la saisie.</p>
      </div>
      <div class="poste">
        <div class="app nav">
          <div class="chrome"><span class="feu r"></span><span class="feu o"></span><span class="feu v"></span>
            <span class="onglet">Connexion Orbis Pay</span></div>
          <div class="barre-url"><span class="cadenas">non sécurisé</span>
            <span class="url">http://{hote}/connexion</span></div>
          <div class="page-faux">
            <div class="faux-logo">Orbis Pay</div>
            <p class="faux-titre">Connexion à votre espace</p>
            <span class="faux-champ">Identifiant</span>
            <span class="faux-champ">Mot de passe</span>
            <span class="faux-cta">Se connecter</span>
          </div>
        </div>
        <div class="voile">
          {_popup_html(verdict)}
        </div>
      </div>
      {_issues_html(choix)}
    </section>"""


def _carte_secondaire(geste: actions.Geste, verdict: Verdict, choix: str | None) -> str:
    coul = _GRAVITE_COULEUR.get(verdict.gravite, "#FBBF24")
    contexte = _esc(verdict.details.get("contexte") or "geste risqué")
    issue = ("Annulé, geste protégé" if choix == "annuler"
             else "Passé outre, incident au SOC")
    issue_cl = "ok" if choix == "annuler" else "ko"
    return f"""<article class="carte" style="--grav:{coul}">
        <div class="carte-tete">
          <span class="carte-ctx">{contexte}</span>
          <span class="carte-grav"><span class="dot"></span>{_esc(verdict.gravite)}</span>
        </div>
        <p class="carte-geste">{_esc(geste.description)}</p>
        <p class="carte-titre">{_esc(verdict.titre)}</p>
        <p class="carte-issue {issue_cl}">{issue}</p>
      </article>"""


# --- page complète -------------------------------------------------------------

def page_html(cartes, titre: str = "Dédale — poste du salarié") -> str:
    """Page autonome : les deux scènes vedettes, puis les gestes de second plan.

    `cartes` : liste de (geste, verdict, choix) pour chaque geste averti.
    """
    mail = next((c for c in cartes if c[1].details.get("contexte") == "mail reçu"), None)
    web = next((c for c in cartes if c[1].details.get("contexte") == "navigation web"), None)
    vus = {id(c) for c in (mail, web) if c is not None}
    reste = [c for c in cartes if id(c) not in vus]

    scenes = ""
    if mail is not None:
        scenes += _scene_mail(*mail)
    if web is not None:
        scenes += _scene_web(*web)

    secondaires = ""
    if reste:
        cartes_html = "\n".join(_carte_secondaire(*c) for c in reste)
        secondaires = f"""<section class="second">
      <div class="scene-tete">
        <span class="pastille">au second plan</span>
        <h2>Les autres gestes qu'il surveille</h2>
        <p class="scene-sous">Secret collé, données clients vers l'extérieur, dépôt sur une IA non validée, pièce jointe piégée.</p>
      </div>
      <div class="grille">
{cartes_html}
      </div>
    </section>"""

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titre)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    color-scheme: dark;
    --bg0:#070B14; --bg1:#0A0E1A;
    --cyan:#22D3EE; --cyan-doux:rgba(34,211,238,.14);
    --ink:#E8EEF7; --muted:#8597AC;
    --surface:rgba(255,255,255,.035); --hair:rgba(255,255,255,.09);
    --ok:#34D399; --ko:#F87171;
    --dsp:"Space Grotesk", ui-sans-serif, system-ui, sans-serif;
    --txt:"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin:0; font-family:var(--txt); color:var(--ink);
    background:
      radial-gradient(900px 520px at 14% -8%, rgba(34,211,238,.10), transparent 60%),
      radial-gradient(760px 480px at 92% 6%, rgba(56,97,230,.12), transparent 62%),
      linear-gradient(180deg, var(--bg1) 0%, var(--bg0) 100%);
    background-attachment:fixed;
    -webkit-font-smoothing:antialiased; line-height:1.5;
  }}
  .enveloppe {{ max-width:1040px; margin:0 auto; padding:72px 24px 96px; }}

  header.hero {{ margin-bottom:64px; }}
  .pastille {{
    display:inline-flex; align-items:center; gap:8px;
    font-size:11px; letter-spacing:.22em; text-transform:uppercase;
    color:var(--cyan); background:var(--cyan-doux);
    border:1px solid rgba(34,211,238,.25); border-radius:999px; padding:6px 14px;
    font-weight:600;
  }}
  header.hero h1 {{
    font-family:var(--dsp); font-weight:700; font-size:clamp(32px,5vw,52px);
    letter-spacing:-.02em; line-height:1.04; margin:22px 0 14px; max-width:16ch;
  }}
  header.hero p {{ color:var(--muted); font-size:17px; max-width:56ch; margin:0; }}

  .scene {{ margin-bottom:72px; }}
  .scene-tete {{ margin-bottom:26px; }}
  .scene-tete h2 {{
    font-family:var(--dsp); font-weight:600; font-size:clamp(22px,3vw,30px);
    letter-spacing:-.01em; margin:16px 0 8px;
  }}
  .scene-sous {{ color:var(--muted); font-size:15px; margin:0; max-width:60ch; }}

  /* --- poste : coque double-bezel + scène + voile + pop-up --- */
  .poste {{
    position:relative; border-radius:30px; padding:10px;
    background:var(--surface); border:1px solid var(--hair);
    box-shadow:0 1px 0 rgba(255,255,255,.05) inset, 0 40px 80px -40px rgba(0,0,0,.8);
  }}
  .app {{
    position:relative; border-radius:22px; overflow:hidden;
    background:#0C1220; border:1px solid rgba(255,255,255,.06);
    box-shadow:inset 0 1px 1px rgba(255,255,255,.06);
  }}
  .chrome {{
    display:flex; align-items:center; gap:8px; padding:12px 16px;
    background:rgba(255,255,255,.03); border-bottom:1px solid var(--hair);
  }}
  .feu {{ width:11px; height:11px; border-radius:50%; background:#2A3447; }}
  .feu.r {{ background:#E6544A; }} .feu.o {{ background:#E6A23C; }} .feu.v {{ background:#3BB273; }}
  .chrome-titre, .onglet {{ color:var(--muted); font-size:13px; margin-left:8px; }}
  .onglet {{
    margin-left:14px; background:rgba(255,255,255,.05); color:var(--ink);
    padding:5px 14px; border-radius:9px 9px 0 0; font-size:12.5px;
  }}

  /* mail */
  .mail-corps {{ display:grid; grid-template-columns:168px 1fr; min-height:340px; }}
  .mail-rail {{ border-right:1px solid var(--hair); padding:14px 10px; display:flex; flex-direction:column; gap:4px; }}
  .rail-item {{ color:var(--muted); font-size:13px; padding:9px 12px; border-radius:9px; display:flex; justify-content:space-between; }}
  .rail-item.actif {{ background:rgba(34,211,238,.10); color:var(--ink); }}
  .rail-item b {{ color:var(--cyan); }}
  .mail-lecture {{ padding:22px 26px; }}
  .mail-objet {{ font-family:var(--dsp); font-weight:600; font-size:18px; margin:0 0 12px; }}
  .mail-de {{ font-size:13.5px; margin:0 0 20px; color:var(--ink); }}
  .mail-adr {{ color:var(--ko); }}
  .mail-texte {{ color:#C2CDDC; font-size:14.5px; margin:0 0 20px; max-width:46ch; }}
  .mail-lien {{
    display:inline-block; background:rgba(248,113,113,.12); color:#FCA5A5;
    border:1px solid rgba(248,113,113,.3); border-radius:10px; padding:10px 16px;
    font-size:13px; font-weight:500;
  }}

  /* navigateur */
  .barre-url {{ display:flex; align-items:center; gap:12px; padding:11px 16px; background:rgba(255,255,255,.02); border-bottom:1px solid var(--hair); }}
  .cadenas {{ font-size:11px; color:var(--ko); border:1px solid rgba(248,113,113,.35); border-radius:999px; padding:3px 10px; letter-spacing:.04em; }}
  .url {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:13px; color:#C2CDDC; }}
  .page-faux {{ min-height:316px; padding:40px 34px; display:flex; flex-direction:column; align-items:center; gap:14px; }}
  .faux-logo {{ font-family:var(--dsp); font-weight:700; font-size:22px; letter-spacing:-.01em; color:var(--ink); }}
  .faux-titre {{ color:var(--muted); font-size:14px; margin:0 0 6px; }}
  .faux-champ {{ width:min(320px,80%); color:var(--muted); font-size:13px; background:rgba(255,255,255,.04); border:1px solid var(--hair); border-radius:10px; padding:12px 14px; }}
  .faux-cta {{ width:min(320px,80%); text-align:center; background:rgba(34,211,238,.16); color:var(--cyan); border:1px solid rgba(34,211,238,.3); border-radius:10px; padding:12px; font-weight:600; font-size:14px; }}

  /* voile + pop-up du garde */
  .voile {{
    position:absolute; inset:10px; border-radius:22px;
    display:flex; align-items:flex-end; justify-content:flex-end; padding:22px;
    background:linear-gradient(115deg, rgba(6,10,20,.08), rgba(6,10,20,.46));
    backdrop-filter:blur(1.5px); -webkit-backdrop-filter:blur(1.5px);
  }}
  .garde {{
    width:min(384px,86%);
    background:linear-gradient(180deg, rgba(16,23,38,.92), rgba(10,15,26,.92));
    border:1px solid rgba(255,255,255,.14); border-radius:20px; overflow:hidden;
    box-shadow:0 30px 70px -20px rgba(0,0,0,.85), inset 0 1px 0 rgba(255,255,255,.08);
    border-top:2px solid var(--cyan);
    animation:surgir .5s cubic-bezier(.32,.72,0,1) both;
  }}
  @keyframes surgir {{ from {{ opacity:0; transform:translateY(14px) scale(.97); }} to {{ opacity:1; transform:none; }} }}
  .garde-tete {{ display:flex; gap:13px; align-items:center; padding:18px 20px 10px; }}
  .garde-ico {{ width:38px; height:38px; flex:none; color:var(--cyan); background:var(--cyan-doux); border:1px solid rgba(34,211,238,.28); border-radius:12px; display:flex; align-items:center; justify-content:center; }}
  .garde-ico svg {{ width:21px; height:21px; }}
  .garde-id {{ display:flex; flex-direction:column; gap:3px; }}
  .garde-nom {{ font-family:var(--dsp); font-weight:600; font-size:13.5px; letter-spacing:.01em; }}
  .garde-meta {{ color:var(--muted); font-size:11.5px; display:flex; align-items:center; gap:7px; }}
  .dot {{ width:7px; height:7px; border-radius:50%; background:var(--grav); box-shadow:0 0 8px var(--grav); }}
  .garde-titre {{ font-family:var(--dsp); font-weight:600; font-size:18px; letter-spacing:-.01em; padding:4px 20px 0; margin:6px 0 8px; }}
  .garde-expli {{ padding:0 20px; color:#C2CDDC; font-size:14px; margin:0 0 14px; }}
  .garde-preuve {{ margin:0 20px 16px; background:rgba(255,255,255,.04); border:1px solid var(--hair); border-radius:10px; padding:10px 13px; font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:12px; color:var(--muted); word-break:break-word; }}
  .garde-boutons {{ display:flex; gap:10px; padding:0 20px 20px; }}
  .garde-boutons button {{ flex:1; padding:11px; border-radius:11px; border:1px solid var(--hair); font-family:var(--txt); font-size:13.5px; font-weight:600; cursor:default; }}
  .b-annuler {{ background:var(--cyan); color:#04121A; border-color:transparent; }}
  .b-continuer {{ background:transparent; color:var(--muted); }}

  /* issues : les deux fins possibles */
  .issues {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:16px; }}
  .issue {{ border-radius:16px; padding:16px 18px; background:var(--surface); border:1px solid var(--hair); opacity:.62; transition:opacity .4s ease; }}
  .issue p {{ margin:8px 0 0; font-size:13.5px; color:#C2CDDC; }}
  .issue-tag {{ font-size:11px; letter-spacing:.14em; text-transform:uppercase; font-weight:600; }}
  .issue.ok .issue-tag {{ color:var(--ok); }}
  .issue.ko .issue-tag {{ color:var(--ko); }}
  .issue.est-arrive {{ opacity:1; }}
  .issue.ok.est-arrive {{ border-color:rgba(52,211,153,.4); box-shadow:0 0 0 1px rgba(52,211,153,.2); }}
  .issue.ko.est-arrive {{ border-color:rgba(248,113,113,.4); box-shadow:0 0 0 1px rgba(248,113,113,.2); }}
  .issue.est-arrive .issue-tag::after {{ content:" · ce qui s'est passé"; color:var(--muted); font-weight:400; letter-spacing:0; text-transform:none; }}

  /* second plan */
  .second {{ margin-top:16px; }}
  .grille {{ display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-top:26px; }}
  .carte {{ border-radius:18px; padding:20px; background:var(--surface); border:1px solid var(--hair); border-left:2px solid var(--grav); }}
  .carte-tete {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }}
  .carte-ctx {{ font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--cyan); font-weight:600; }}
  .carte-grav {{ display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted); }}
  .carte-geste {{ color:var(--muted); font-size:13px; margin:0 0 8px; }}
  .carte-titre {{ font-family:var(--dsp); font-weight:600; font-size:15.5px; margin:0 0 14px; }}
  .carte-issue {{ font-size:12.5px; font-weight:600; margin:0; }}
  .carte-issue.ok {{ color:var(--ok); }}
  .carte-issue.ko {{ color:var(--ko); }}

  footer {{ color:var(--muted); font-size:12.5px; border-top:1px solid var(--hair); margin-top:40px; padding-top:22px; }}

  @media (max-width:760px) {{
    .enveloppe {{ padding:48px 16px 64px; }}
    .mail-corps {{ grid-template-columns:1fr; }}
    .mail-rail {{ display:none; }}
    .issues, .grille {{ grid-template-columns:1fr; }}
    .voile {{ padding:12px; align-items:center; justify-content:center; }}
    .garde {{ width:min(380px,96%); }}
  }}
</style>
</head>
<body>
  <div class="enveloppe">
    <header class="hero">
      <span class="pastille">Dédale · garde du corps du poste</span>
      <h1>Camille est prévenue avant le clic de trop.</h1>
      <p>Une appli discrète tourne sur son poste. Elle lit le mail qui arrive et le lien qu'elle s'apprête à ouvrir, puis prévient au bon moment. Tout est fictif, local et inerte.</p>
    </header>
{scenes}
{secondaires}
    <footer>Dédale · pilier humain, le maillon faible · {_esc(titre)}. Rien ne quitte le poste : chaque avertissement et chaque choix part à la console, preuve neutralisée.</footer>
  </div>
</body>
</html>"""
