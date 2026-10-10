"""Les règles de détection du garde du corps.

Chaque règle est explicite et explicable : elle dit en clair pourquoi le geste
est risqué. La preuve (secret, destinataire, lien) est renvoyée NEUTRALISÉE :
tronquée et préfixée, jamais réutilisable. Le texte observé n'est jamais
réexécuté ni réinterprété comme une consigne, seulement inspecté.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import actions, config


@dataclass
class Verdict:
    risque: bool
    incident: str | None = None   # humain_secret | humain_mail_externe | humain_upload_ia | humain_phishing
    regle: str = ""               # code court de la règle déclenchée
    titre: str = ""               # phrase de la pop-up (« attends, tu vas… »)
    explication: str = ""         # pourquoi, en clair
    gravite: str = "moyenne"      # faible | moyenne | haute | critique
    preuve: str = ""              # extrait neutralisé, inerte
    details: dict = field(default_factory=dict)


# --- neutralisation ------------------------------------------------------------

def neutraliser(texte: str, garder: int = 6) -> str:
    """Rend une preuve inerte : on garde un court repère et on masque le reste."""
    texte = (texte or "").replace("\n", " ").replace("\r", " ").strip()
    if len(texte) <= garder:
        visible = texte
    else:
        visible = texte[:garder] + "…"
    return "[preuve, neutralisée] " + visible


# --- secrets -------------------------------------------------------------------

# (code de règle, libellé, motif). Ordre du plus spécifique au plus général.
_MOTIFS_SECRET: list[tuple[str, str, re.Pattern]] = [
    ("SECRET_CLE_PRIVEE", "clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("SECRET_AWS", "clé d'accès AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SECRET_ANTHROPIC", "clé API Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}")),
    ("SECRET_OPENAI", "clé API (format sk-)", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("SECRET_GITHUB", "jeton GitHub", re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("SECRET_SLACK", "jeton Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("SECRET_GOOGLE", "clé API Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("SECRET_MDP", "mot de passe en clair",
     re.compile(r"(?i)(mot de passe|motdepasse|password|passwd|pwd)\s*[:=]\s*\S{6,}")),
    ("SECRET_GENERIQUE", "secret / jeton nommé",
     re.compile(r"(?i)(api[_-]?key|secret|token|bearer)\s*[:=]\s*\S{8,}")),
]


def _cherche_secret(texte: str) -> tuple[str, str, str] | None:
    for code, libelle, motif in _MOTIFS_SECRET:
        m = motif.search(texte or "")
        if m:
            return code, libelle, m.group(0)
    return None


def _est_interne(domaine: str) -> bool:
    d = (domaine or "").lower().strip()
    if not d:
        return False
    return d == config.DOMAINE_ENTREPRISE or d.endswith("." + config.DOMAINE_ENTREPRISE)


def _est_autorise(domaine: str) -> bool:
    d = (domaine or "").lower().strip()
    return _est_interne(d) or d in config.DOMAINES_AUTORISES


# --- destinataires de mail -----------------------------------------------------

def _domaine_mail(adresse: str) -> str:
    adresse = (adresse or "").strip().lower()
    return adresse.rsplit("@", 1)[-1] if "@" in adresse else ""


_MOTS_SENSIBLES = re.compile(
    r"(?i)(client|iban|rib|export|base de donn|salaire|paie|contrat|dossier|"
    r"confidentiel|carte bancaire|num[ée]ro de carte)"
)
_IBAN = re.compile(r"\bFR\d{2}[0-9A-Z ]{20,30}\b")


def _contenu_sensible(g: actions.Geste) -> str | None:
    """Renvoie un repère de ce qui est sensible, ou None."""
    for p in g.pieces:
        if _MOTS_SENSIBLES.search(p):
            return "pièce « " + p + " »"
    m = _IBAN.search(g.corps)
    if m:
        return "IBAN dans le corps"
    if _MOTS_SENSIBLES.search(g.corps) or _MOTS_SENSIBLES.search(g.objet):
        return "données sensibles dans le mail"
    return None


# --- liens de phishing ---------------------------------------------------------

_TLD_SUSPECTS = {".ru", ".zip", ".top", ".xyz", ".help", ".click", ".country"}
_IP_LITTERALE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _analyse_lien(url: str) -> tuple[str, str] | None:
    """Renvoie (code, raison) si le lien est suspect, sinon None."""
    parts = urlsplit(url if "://" in (url or "") else "http://" + (url or ""))
    hote = (parts.hostname or "").lower()
    if not hote:
        return None
    if _est_interne(hote):
        return None
    # ruse « userinfo » : https://orbispay.example@site-mechant.ru/
    if "@" in (parts.netloc or ""):
        return "PHISHING_USERINFO", "le lien se fait passer pour orbispay.example avant un « @ » qui renvoie ailleurs"
    if hote in config.PHISHING_CONNUS:
        return "PHISHING_LISTE", "domaine déjà connu comme piège"
    if _IP_LITTERALE.match(hote):
        return "PHISHING_IP", "le lien pointe vers une adresse IP nue, pas un vrai site"
    if hote.startswith("xn--") or ".xn--" in hote:
        return "PHISHING_PUNYCODE", "domaine en punycode, souvent une imitation visuelle"
    # sosie : contient « orbispay » sans être le vrai domaine
    if "orbispay" in hote and not _est_interne(hote):
        return "PHISHING_SOSIE", "imite le nom orbispay sans en être le vrai domaine"
    for tld in _TLD_SUSPECTS:
        if hote.endswith(tld):
            return "PHISHING_TLD", "extension de domaine inhabituelle (" + tld + ")"
    return None


# --- mail reçu : phishing à l'ouverture -----------------------------------------

# Tournures d'un mail qui pousse à agir dans l'urgence sur ses identifiants.
_APPAT_MAIL = re.compile(
    r"(?i)(v[ée]rifi|confirm|r[ée]activ|r[ée]initialis|suspend|bloqu|"
    r"expire|d[ée]sactiv|identifiant|mot de passe|cliqu|connect|"
    r"sous 24|dans les 24|imm[ée]diat|derni[eè]re? (chance|relance))"
)
_URL_DANS_CORPS = re.compile(r"https?://[^\s\"'<>]+")


def _lien_du_mail(g: actions.Geste) -> str:
    if g.lien:
        return g.lien
    m = _URL_DANS_CORPS.search(g.corps or "")
    return m.group(0) if m else ""


def _mail_recu_suspect(g: actions.Geste) -> tuple[str, str, str] | None:
    """Renvoie (code, raison, lien) si le mail reçu est du phishing, sinon None.

    On lit l'expéditeur et le lien du corps au moment où Camille ouvre le mail,
    avant tout clic. Un expéditeur interne et sans lien piégé ne déclenche rien.
    """
    exp_domaine = _domaine_mail(g.expediteur)
    lien = _lien_du_mail(g)

    # 1) Le lien du corps est lui-même un piège (liste noire, sosie, IP, TLD…).
    if lien:
        verdict_lien = _analyse_lien(lien)
        if verdict_lien:
            return verdict_lien[0], verdict_lien[1], lien

    # 2) L'expéditeur imite Orbis Pay sans en être le vrai domaine.
    if exp_domaine:
        if exp_domaine in config.PHISHING_CONNUS:
            return "MAIL_EXPEDITEUR_CONNU", "l'expéditeur est un domaine déjà repéré comme piège", lien
        if "orbispay" in exp_domaine and not _est_interne(exp_domaine):
            return "MAIL_EXPEDITEUR_SOSIE", "l'adresse imite orbispay.example sans en être le vrai domaine", lien

    # 3) Le nom affiché se réclame d'Orbis ou d'une banque, l'adresse part ailleurs.
    nom = (g.expediteur_affiche or "").lower()
    if exp_domaine and not _est_interne(exp_domaine) and re.search(r"(orbis|s[ée]curit|banque|support|rh|paie)", nom):
        return "MAIL_NOM_USURPE", "le nom affiché se fait passer pour Orbis Pay, l'adresse réelle est externe", lien

    # 4) Appât aux identifiants depuis un expéditeur externe.
    if exp_domaine and not _est_interne(exp_domaine) and _APPAT_MAIL.search((g.objet or "") + " " + (g.corps or "")):
        return "MAIL_APPAT", "mail externe qui réclame tes identifiants dans l'urgence", lien

    return None


def _extension(nom: str) -> str:
    nom = (nom or "").lower()
    i = nom.rfind(".")
    return nom[i:] if i >= 0 else ""


def _piece_piegee(nom: str, externe: bool) -> tuple[str, str] | None:
    nom_bas = (nom or "").lower()
    ext = _extension(nom_bas)
    # double extension : facture.pdf.exe
    sans_ext = nom_bas[: -len(ext)] if ext else nom_bas
    if _extension(sans_ext) in {".pdf", ".doc", ".xls", ".jpg", ".txt", ".csv"} and ext in config.EXTENSIONS_PIEGEES:
        return "PIECE_DOUBLE_EXT", "double extension : un exécutable déguisé en document"
    if ext in config.EXTENSIONS_PIEGEES:
        return "PIECE_EXECUTABLE", "fichier exécutable (" + ext + "), pas un document"
    if ext in config.EXTENSIONS_MACRO and externe:
        return "PIECE_MACRO", "document à macros reçu de l'extérieur (" + ext + ")"
    return None


# --- règle maîtresse -----------------------------------------------------------

def evaluer(g: actions.Geste) -> Verdict:
    """Décide si le geste est risqué. Un seul verdict par geste."""
    # --- geste vedette : Camille ouvre un mail reçu qui est frauduleux ---
    if g.nature == actions.OUVRIR_MAIL:
        trouve = _mail_recu_suspect(g)
        if trouve:
            code, raison, lien = trouve
            de = g.expediteur_affiche or g.expediteur or "un expéditeur inconnu"
            preuve = neutraliser((g.expediteur or de) + (" · " + lien if lien else ""), garder=40)
            return Verdict(
                risque=True,
                incident="humain_phishing",
                regle=code,
                titre="Ce mail est sûrement frauduleux.",
                explication="Il se présente comme Orbis Pay, mais " + raison
                            + ". Ne clique sur rien et ne réponds pas : signale-le à la sécurité.",
                gravite="haute",
                preuve=preuve,
                details={"contexte": "mail reçu", "raison": raison,
                         "expediteur": g.expediteur, "expediteur_affiche": g.expediteur_affiche,
                         "objet": g.objet, "lien": lien},
            )
        return Verdict(risque=False)

    if g.nature == actions.COLLER_TEXTE:
        trouve = _cherche_secret(g.texte)
        if trouve and not _est_interne(g.domaine):
            code, libelle, brut = trouve
            cible = g.cible or g.domaine or "une surface externe"
            return Verdict(
                risque=True,
                incident="humain_secret",
                regle=code,
                titre="Ne colle pas " + libelle + " dans " + cible + ".",
                explication="Un " + libelle + " a été repéré dans ce que tu colles, et "
                            + cible + " est hors du périmètre de l'entreprise. "
                            "Une fois collé, le secret est exposé.",
                gravite="haute",
                # Un secret ne laisse rien fuir : ni valeur, ni préfixe exploitable.
                preuve="[preuve, neutralisée] " + libelle + ", " + str(len(brut)) + " caractères",
                details={"contexte": "copier-coller", "cible": cible, "domaine": g.domaine,
                         "categorie_secret": libelle},
            )
        return Verdict(risque=False)

    if g.nature == actions.ENVOYER_MAIL:
        externes = [a for a in g.destinataires if not _est_interne(_domaine_mail(a))]
        sensible = _contenu_sensible(g)
        if externes and sensible:
            return Verdict(
                risque=True,
                incident="humain_mail_externe",
                regle="MAIL_EXTERNE_SENSIBLE",
                titre="Ce mail part à l'extérieur avec des données sensibles.",
                explication="Destinataire(s) hors de " + config.DOMAINE_ENTREPRISE + " : "
                            + ", ".join(externes) + ". Le mail contient " + sensible + ".",
                gravite="haute",
                preuve=neutraliser(", ".join(externes) + " | " + sensible, garder=24),
                details={"contexte": "mail sortant", "destinataires_externes": externes,
                         "indice": sensible, "pieces": g.pieces},
            )
        return Verdict(risque=False)

    if g.nature == actions.DEPOSER_FICHIER:
        if g.confidentiel and not _est_autorise(g.domaine):
            cible = g.cible or g.domaine or "un service non autorisé"
            return Verdict(
                risque=True,
                incident="humain_upload_ia",
                regle="UPLOAD_IA_NON_AUTORISEE",
                titre="Ce fichier confidentiel ne doit pas aller sur " + cible + ".",
                explication="« " + g.fichier + " » est confidentiel et " + cible
                            + " ne fait pas partie des outils validés par la DSI. "
                            "Le document sort de l'entreprise et peut servir à entraîner un modèle.",
                gravite="haute",
                preuve=neutraliser(g.fichier + " → " + (g.domaine or cible), garder=28),
                details={"contexte": "dépôt de fichier", "fichier": g.fichier,
                         "cible": cible, "domaine": g.domaine},
            )
        return Verdict(risque=False)

    if g.nature == actions.CLIQUER_LIEN:
        verdict_lien = _analyse_lien(g.url)
        if verdict_lien:
            code, raison = verdict_lien
            return Verdict(
                risque=True,
                incident="humain_phishing",
                regle=code,
                titre="Ce lien n'est pas le vrai site d'Orbis Pay.",
                explication="En clair : " + raison + ". N'entre pas tes identifiants sur cette page.",
                gravite="haute",
                preuve=neutraliser(g.url, garder=40),
                details={"contexte": "navigation web", "url": neutraliser(g.url, garder=80),
                         "hote": urlsplit(g.url if "://" in (g.url or "") else "http://" + (g.url or "")).hostname or "",
                         "raison": raison},
            )
        return Verdict(risque=False)

    if g.nature == actions.OUVRIR_PIECE:
        verdict_piece = _piece_piegee(g.fichier, g.expediteur_externe)
        if verdict_piece:
            code, raison = verdict_piece
            return Verdict(
                risque=True,
                incident="humain_phishing",
                regle=code,
                titre="N'ouvre pas cette pièce jointe.",
                explication="En clair : " + raison + ". L'ouvrir peut installer un logiciel malveillant sur ton poste.",
                gravite="critique" if "EXT" in code else "haute",
                preuve=neutraliser(g.fichier, garder=40),
                details={"contexte": "pièce jointe", "fichier": g.fichier, "raison": raison,
                         "expediteur_externe": g.expediteur_externe},
            )
        return Verdict(risque=False)

    return Verdict(risque=False)
