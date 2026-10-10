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
    if g.nature == actions.COLLER_TEXTE:
        trouve = _cherche_secret(g.texte)
        if trouve and not _est_interne(g.domaine):
            code, libelle, brut = trouve
            cible = g.cible or g.domaine or "une surface externe"
            return Verdict(
                risque=True,
                incident="humain_secret",
                regle=code,
                titre="Attends — tu es sur le point de coller " + libelle + " dans " + cible + ".",
                explication="Un " + libelle + " a été repéré dans ce que tu colles, et "
                            + cible + " est hors du périmètre de l'entreprise. "
                            "Une fois collé, le secret est exposé.",
                gravite="haute",
                # Un secret ne laisse rien fuir : ni valeur, ni préfixe exploitable.
                preuve="[preuve, neutralisée] " + libelle + ", " + str(len(brut)) + " caractères",
                details={"cible": cible, "domaine": g.domaine, "categorie_secret": libelle},
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
                titre="Attends — ce mail part à l'extérieur avec des données sensibles.",
                explication="Destinataire(s) hors de " + config.DOMAINE_ENTREPRISE + " : "
                            + ", ".join(externes) + ". Le mail contient " + sensible + ".",
                gravite="haute",
                preuve=neutraliser(", ".join(externes) + " | " + sensible, garder=24),
                details={"destinataires_externes": externes, "indice": sensible,
                         "pieces": g.pieces},
            )
        return Verdict(risque=False)

    if g.nature == actions.DEPOSER_FICHIER:
        if g.confidentiel and not _est_autorise(g.domaine):
            cible = g.cible or g.domaine or "un service non autorisé"
            return Verdict(
                risque=True,
                incident="humain_upload_ia",
                regle="UPLOAD_IA_NON_AUTORISEE",
                titre="Attends — tu déposes un fichier confidentiel sur " + cible + ".",
                explication="« " + g.fichier + " » est confidentiel et " + cible
                            + " ne fait pas partie des outils validés par la DSI. "
                            "Le document sort de l'entreprise et peut servir à entraîner un modèle.",
                gravite="haute",
                preuve=neutraliser(g.fichier + " → " + (g.domaine or cible), garder=28),
                details={"fichier": g.fichier, "cible": cible, "domaine": g.domaine},
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
                titre="Attends — ce lien n'est pas celui d'Orbis Pay.",
                explication="Raison : " + raison + ". Ne saisis surtout pas tes identifiants.",
                gravite="haute",
                preuve=neutraliser(g.url, garder=40),
                details={"url": neutraliser(g.url, garder=80), "raison": raison},
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
                titre="Attends — cette pièce jointe est dangereuse.",
                explication="Raison : " + raison + ". Ouvrir ce fichier peut installer un logiciel malveillant.",
                gravite="critique" if "EXT" in code else "haute",
                preuve=neutraliser(g.fichier, garder=40),
                details={"fichier": g.fichier, "raison": raison,
                         "expediteur_externe": g.expediteur_externe},
            )
        return Verdict(risque=False)

    return Verdict(risque=False)
