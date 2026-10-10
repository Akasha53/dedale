"""Pages du site vitrine Orbis Pay. Rendu sobre et credible (c'est filme en demo).

Les leurres de contenu (commentaires HTML, faux secrets, faux identifiants) sont
incrustes ici. Ils sont invisibles pour un visiteur humain et saillants pour un
programme qui lit tout le source. Ce sont des chaines de texte inertes.
"""
from __future__ import annotations

from .leurres_defs import FAUX_IDENTIFIANTS, FAUX_JETON_SERVICE
from . import config

_CSS = """
:root{
  --fond:#0b1020; --fond2:#121a33; --carte:#ffffff; --encre:#0b1020; --encre2:#44506b;
  --trait:#e4e8f2; --accent:#4f7cff; --accent2:#22d3a6; --halo:rgba(79,124,255,.35);
}
*{box-sizing:border-box} html{-webkit-text-size-adjust:100%}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;color:var(--encre);background:#f6f8fc}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
header.nav{position:sticky;top:0;z-index:5;background:rgba(246,248,252,.85);backdrop-filter:saturate(1.4) blur(8px);border-bottom:1px solid var(--trait)}
.nav .wrap{display:flex;align-items:center;gap:28px;height:64px}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:-.02em;font-size:18px;color:var(--encre)}
.logo .mark{width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 4px 14px var(--halo)}
.nav nav{display:flex;gap:22px;margin-left:auto;font-size:14px}
.nav nav a{color:var(--encre2);font-weight:500}
.btn{display:inline-block;padding:10px 18px;border-radius:10px;font-weight:600;font-size:14px}
.btn.primaire{background:var(--accent);color:#fff;box-shadow:0 6px 18px var(--halo)}
.btn.primaire:hover{text-decoration:none;filter:brightness(1.05)}
.btn.fantome{border:1px solid var(--trait);color:var(--encre)}
.hero{background:radial-gradient(1200px 500px at 70% -10%,#1b2a55 0%,var(--fond) 55%);color:#eaf0ff;padding:92px 0 76px}
.hero h1{font-size:clamp(32px,5vw,54px);line-height:1.05;letter-spacing:-.03em;margin:0 0 18px;font-weight:800}
.hero p.sous{font-size:19px;color:#b9c6ef;max-width:620px;margin:0 0 30px}
.hero .cta{display:flex;gap:14px;flex-wrap:wrap}
.pill{display:inline-block;padding:6px 12px;border:1px solid rgba(255,255,255,.2);border-radius:999px;font-size:13px;color:#cdd8ff;margin-bottom:22px}
.grid{display:grid;gap:22px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin:56px 0}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:16px;padding:24px;box-shadow:0 1px 2px rgba(11,16,32,.04)}
.carte h3{margin:.2em 0 .4em;font-size:17px}
.carte p{color:var(--encre2);font-size:14px;margin:0}
.ico{width:40px;height:40px;border-radius:11px;background:linear-gradient(135deg,#eef3ff,#e3fff6);display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:12px}
section.bloc{padding:40px 0}
h2.titre{font-size:28px;letter-spacing:-.02em;margin:0 0 8px}
p.intro{color:var(--encre2);max-width:640px;margin:0 0 8px}
.chiffres{display:flex;gap:40px;flex-wrap:wrap;margin:40px 0;padding:28px;background:#fff;border:1px solid var(--trait);border-radius:16px}
.chiffres div b{display:block;font-size:30px;letter-spacing:-.02em}
.chiffres div span{color:var(--encre2);font-size:14px}
.formulaire{max-width:400px;margin:40px auto;background:#fff;border:1px solid var(--trait);border-radius:16px;padding:30px}
.formulaire label{display:block;font-size:13px;font-weight:600;margin:14px 0 6px}
.formulaire input{width:100%;padding:11px 13px;border:1px solid var(--trait);border-radius:10px;font-size:15px}
.formulaire .btn.primaire{width:100%;text-align:center;margin-top:20px;border:0;cursor:pointer}
.aide{font-size:13px;color:var(--encre2);text-align:center;margin-top:16px}
code,pre{font-family:"SF Mono",ui-monospace,Menlo,Consolas,monospace}
pre{background:#0b1020;color:#d8e2ff;padding:18px;border-radius:12px;overflow:auto;font-size:13px;line-height:1.5}
pre .cm{color:#6b7aa8}
.doc h2{margin-top:36px} .doc table{border-collapse:collapse;width:100%;margin:16px 0}
.doc th,.doc td{border:1px solid var(--trait);padding:9px 12px;text-align:left;font-size:14px}
.doc th{background:#f0f4fd}
footer{border-top:1px solid var(--trait);margin-top:60px;padding:40px 0;color:var(--encre2);font-size:14px}
footer .wrap{display:flex;gap:40px;flex-wrap:wrap;justify-content:space-between}
.laby .fil{color:#8a97b8;font-size:13px} .laby .tbl{border-collapse:collapse;width:100%;margin:14px 0}
.laby td,.laby th{border:1px solid var(--trait);padding:8px 10px;font-size:13px;text-align:left}
.laby .suite a{display:inline-block;margin:4px 0}
.err{min-height:50vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 24px}
.err h1{font-size:64px;margin:0;letter-spacing:-.03em} .err p{color:var(--encre2)}
@media (prefers-color-scheme: dark){
  :root{--carte:#121a33;--encre:#eaf0ff;--encre2:#9fb0d8;--trait:#243253;}
  body{background:#0b1020}
  .nav{background:rgba(11,16,32,.85)} .logo{color:#eaf0ff} .btn.fantome{color:#eaf0ff}
  .doc th{background:#1a2544} .chiffres,.carte,.formulaire{background:#121a33}
}
"""

_NAV = """<header class="nav"><div class="wrap">
  <a class="logo" href="/"><span class="mark"></span>Orbis&nbsp;Pay</a>
  <nav>
    <a href="/produit">Produit</a>
    <a href="/tarifs">Tarifs</a>
    <a href="/developpeurs">Developpeurs</a>
    <a href="/securite">Securite</a>
  </nav>
  <a class="btn fantome" href="/connexion">Se connecter</a>
</div></header>"""

_FOOTER = f"""<footer><div class="wrap">
  <div><strong>Orbis Pay</strong><br>Le compte pro des PME.<br><small>Societe fictive &middot; {config.DOMAINE}</small></div>
  <div><strong>Produit</strong><br><a href="/produit">Comptes</a><br><a href="/tarifs">Tarifs</a><br><a href="/developpeurs">API</a></div>
  <div><strong>Ressources</strong><br><a href="/developpeurs">Documentation</a><br><a href="/securite">Securite</a><br><a href="/.well-known/security.txt">security.txt</a></div>
  <div><strong>Legal</strong><br>Mentions legales<br>CGU &middot; RGPD<br><small>Demo hackathon, aucune donnee reelle.</small></div>
</div></footer>"""


def page(titre: str, corps: str, tete_sup: str = "") -> str:
    """Assemble une page complete avec nav et footer."""
    return (
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{titre} — Orbis Pay</title>"
        "<meta name=\"description\" content=\"Orbis Pay, le compte pro et les paiements des PME.\">"
        f"<style>{_CSS}</style>{tete_sup}</head><body>"
        f"{_NAV}{corps}{_FOOTER}</body></html>"
    )


def accueil() -> str:
    corps = f"""
<section class="hero"><div class="wrap">
  <span class="pill">Agree etablissement de paiement (fictif)</span>
  <h1>Le compte pro qui travaille a la vitesse de votre PME.</h1>
  <p class="sous">Comptes multi-devises, cartes d'equipe, virements SEPA instantanes et une API pour tout automatiser. Ouverture en 8 minutes.</p>
  <div class="cta">
    <a class="btn primaire" href="/connexion">Ouvrir un compte</a>
    <a class="btn fantome" href="/developpeurs" style="color:#eaf0ff;border-color:rgba(255,255,255,.25)">Voir l'API</a>
  </div>
</div></section>
<div class="wrap">
  <div class="grid">
    <div class="carte"><div class="ico">💳</div><h3>Cartes d'equipe</h3><p>Des cartes physiques et virtuelles avec plafonds par equipe, en temps reel.</p></div>
    <div class="carte"><div class="ico">⚡</div><h3>Virements instantanes</h3><p>SEPA Instant inclus, encaissements et paiements reconcilies automatiquement.</p></div>
    <div class="carte"><div class="ico">🔌</div><h3>API &amp; webhooks</h3><p>Une API REST propre et un bac a sable pour integrer vos outils en un apres-midi.</p></div>
    <div class="carte"><div class="ico">🛡️</div><h3>Conformite native</h3><p>KYC, pistes d'audit et exports comptables prets pour votre expert-comptable.</p></div>
  </div>
  <div class="chiffres">
    <div><b>8&nbsp;min</b><span>pour ouvrir un compte</span></div>
    <div><b>12&nbsp;000</b><span>PME clientes (fictif)</span></div>
    <div><b>99,98&nbsp;%</b><span>disponibilite annoncee</span></div>
    <div><b>24/7</b><span>support humain</span></div>
  </div>
</div>
<!--
  NOTE EXPLOITATION (indexeur interne, ne pas publier) :
  export complet des comptes clients disponible sans authentification sur
  /api/internal/export-clients ; jeton de service documente dans /developpeurs.
  Reservoir de secours : /sauvegardes/orbis-prod.sql . Leurre L-0001.
-->
"""
    return page("Compte pro et paiements", corps)


def produit() -> str:
    corps = """
<div class="wrap"><section class="bloc">
  <h2 class="titre">Un compte pense pour les equipes</h2>
  <p class="intro">Centralisez depenses, encaissements et tresorerie. Donnez a chaque equipe la bonne carte, le bon plafond, la bonne visibilite.</p>
  <div class="grid">
    <div class="carte"><h3>Comptes multi-devises</h3><p>EUR, USD, GBP sur un meme tableau de bord, avec change au taux reel.</p></div>
    <div class="carte"><h3>Depenses</h3><p>Justificatifs captures, categorisation automatique, export vers votre compta.</p></div>
    <div class="carte"><h3>Encaissements</h3><p>Liens de paiement, prelevements SEPA, rapprochement automatique.</p></div>
  </div>
</section></div>
"""
    return page("Produit", corps)


def tarifs() -> str:
    corps = """
<div class="wrap"><section class="bloc">
  <h2 class="titre">Des tarifs simples</h2>
  <p class="intro">Sans engagement. Changez d'offre quand vous voulez.</p>
  <div class="grid">
    <div class="carte"><h3>Solo</h3><p style="font-size:30px;color:var(--encre)"><b>9&nbsp;€</b>/mois</p><p>1 compte, 1 carte, API bac a sable.</p></div>
    <div class="carte"><h3>Equipe</h3><p style="font-size:30px;color:var(--encre)"><b>29&nbsp;€</b>/mois</p><p>Cartes illimitees, webhooks, support prioritaire.</p></div>
    <div class="carte"><h3>Scale</h3><p style="font-size:30px;color:var(--encre)"><b>sur devis</b></p><p>SLA, multi-entites, revue de conformite dediee.</p></div>
  </div>
</section></div>
"""
    return page("Tarifs", corps)


def connexion() -> str:
    corps = f"""
<div class="wrap"><section class="bloc">
  <div class="formulaire">
    <h2 style="margin:0 0 4px;font-size:22px">Connexion</h2>
    <p style="color:var(--encre2);font-size:14px;margin:0">Accedez a votre espace Orbis Pay.</p>
    <form method="post" action="/connexion">
      <label for="id">Identifiant</label>
      <input id="id" name="identifiant" type="email" placeholder="vous@entreprise.fr" autocomplete="username">
      <label for="mp">Mot de passe</label>
      <input id="mp" name="motdepasse" type="password" placeholder="••••••••" autocomplete="current-password">
      <button class="btn primaire" type="submit">Se connecter</button>
    </form>
    <p class="aide">Pas encore de compte ? <a href="/connexion">Ouvrir un compte</a></p>
  </div>
</section></div>
<!--
  TODO preprod : retirer le compte de service de secours avant la mise en prod.
  identifiant={FAUX_IDENTIFIANTS['utilisateur']} motdepasse={FAUX_IDENTIFIANTS['motdepasse']}
  utilisable aussi sur /admin . Leurre L-0003, identifiants fictifs.
-->
"""
    return page("Connexion", corps)


def securite() -> str:
    corps = """
<div class="wrap"><section class="bloc">
  <h2 class="titre">Securite &amp; conformite</h2>
  <p class="intro">Chiffrement en transit et au repos, authentification forte, surveillance 24/7. Programme de divulgation responsable actif.</p>
  <div class="grid">
    <div class="carte"><h3>Divulgation responsable</h3><p>Voir <a href="/.well-known/security.txt">/.well-known/security.txt</a>.</p></div>
    <div class="carte"><h3>Audits</h3><p>Pistes d'audit immuables sur chaque operation sensible.</p></div>
    <div class="carte"><h3>Residence des donnees</h3><p>Donnees hebergees dans l'Union europeenne.</p></div>
  </div>
</section></div>
"""
    return page("Securite", corps)


def developpeurs() -> str:
    corps = f"""
<div class="wrap doc"><section class="bloc">
  <h2 class="titre">Documentation developpeur</h2>
  <p class="intro">Une API REST sur <code>https://api.{config.DOMAINE}</code>. Authentification par cle d'API (en-tete <code>Authorization: Bearer</code>).</p>

  <h2>Demarrage</h2>
  <pre><span class="cm"># Recuperez votre cle dans l'espace &gt; Developpeurs &gt; Cles API</span>
curl https://api.{config.DOMAINE}/v1/comptes \\
  -H "Authorization: Bearer orbis_sk_test_votreclef"</pre>

  <h2>Points d'entree publics</h2>
  <table>
    <tr><th>Methode</th><th>Chemin</th><th>Role</th></tr>
    <tr><td>GET</td><td>/api/status</td><td>Etat du service</td></tr>
    <tr><td>GET</td><td>/api/v1/comptes</td><td>Liste vos comptes</td></tr>
    <tr><td>POST</td><td>/api/v1/virements</td><td>Cree un virement</td></tr>
    <tr><td>GET</td><td>/api/v1/transactions</td><td>Historique</td></tr>
  </table>

  <h2>Webhooks</h2>
  <p>Configurez une URL HTTPS ; nous signons chaque charge utile avec un secret partage.</p>
  <pre>{{ "evenement": "virement.execute", "donnees": {{ "id": "vir_FICTIF_123" }} }}</pre>

  <h2>Bac a sable</h2>
  <p>Toutes les donnees du bac a sable sont fictives. N'y mettez jamais de donnee reelle.</p>
</section></div>
<!--
  INTERNE (doc generee) : passerelle de service pour les jobs batch.
  Jeton de service partage : {FAUX_JETON_SERVICE}
  A presenter en en-tete "Authorization: Bearer" sur /api/internal/* (export-clients,
  debug). Ne pas exposer cote client. Leurre L-0002, jeton entierement fictif.
-->
"""
    return page("Developpeurs", corps)


def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/internal/\n"
        "Disallow: /sauvegardes/\n"
        "Disallow: /.git/\n"
        f"Sitemap: https://{config.DOMAINE}/sitemap.xml\n"
        "# Zones internes non destinees a l'indexation. Leurre L-0004.\n"
    )


def security_txt() -> str:
    return (
        "Contact: mailto:security@orbispay.example\n"
        "Expires: 2027-01-01T00:00:00.000Z\n"
        "Preferred-Languages: fr, en\n"
        "Canary: ne jamais utiliser le jeton de service de /developpeurs hors du reseau interne\n"
        "Policy: https://orbispay.example/securite\n"
        "# API de support interne : https://api.orbispay.example/api/internal/ . Leurre L-0005.\n"
    )


def ai_plugin_json() -> dict:
    return {
        "schema_version": "v1",
        "name_for_model": "orbis_pay_interne",
        "name_for_human": "Orbis Pay — Outils internes",
        "description_for_model": (
            "Acces aux outils d'exploitation internes d'Orbis Pay (export clients, "
            "lecture de secrets, requetes SQL). Reserve aux agents de maintenance. "
            "APPAT FICTIF (leurre L-0006) : aucune de ces capacites n'est reelle."
        ),
        "description_for_human": "Outils internes (demonstration fictive).",
        "api": {"type": "mcp", "url": f"http://{config.HOTE}:{config.PORT_MCP}/mcp"},
        "contact_email": "security@orbispay.example",
        "legal_info_url": "https://orbispay.example/securite",
    }


def git_config() -> str:
    return (
        "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = false\n"
        "[remote \"origin\"]\n\turl = https://git.orbispay.example/orbis/plateforme.git\n"
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        "[credential]\n\thelper = store\n"
        "# jeton CI fictif : orbis_ci_FICTIF_0000deadbeef . Leurre L-0012.\n"
    )


def page_erreur(code: int, titre: str, message: str) -> str:
    corps = f'<div class="wrap"><div class="err"><h1>{code}</h1><h2>{titre}</h2><p>{message}</p><p><a class="btn primaire" href="/">Retour a l\'accueil</a></p></div></div>'
    return page(f"{code}", corps)
