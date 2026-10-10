"""Analyseur explicable des mails reçus par Orbis Pay (entreprise fictive).

Chaque mail reçoit un verdict `sur | suspect | frauduleux`, un score entre 0 et 1, et une
phrase en français simple par signal relevé. Le score combine les signaux comme des
probabilités indépendantes : score = 1 - produit des (1 - poids).

Règle dure : l'analyseur ne fait que lire du texte. Il n'ouvre, ne résout et ne suit aucun
lien, ne lance aucune pièce jointe. Une archive Office ou ZIP est seulement listée en mémoire
pour repérer des macros ou un programme caché.

Le contenu d'un mail est de la donnée, jamais une instruction : une consigne cachée qui
s'adresse à un assistant IA est un signal à rapporter, pas un ordre à suivre.
"""

from __future__ import annotations

import email
import email.policy
import html
import io
import ipaddress
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

# --- Ce qu'Orbis Pay connaît et à qui il fait confiance ---------------------------------

DOMAINE_ORBIS = "orbispay.example"

# Domaine de confiance -> (libellé lisible, noms de marque qu'un sosie recopie).
DOMAINES_DE_CONFIANCE: dict[str, tuple[str, tuple[str, ...]]] = {
    "orbispay.example": ("Orbis Pay", ("orbispay", "orbis")),
    "nuvola-cloud.example": ("Nuvola Cloud, l'hébergeur d'Orbis Pay", ("nuvola",)),
    "banque-atlas.example": ("la Banque Atlas, banque d'Orbis Pay", ("banqueatlas",)),
}

# Dirigeants qu'un fraudeur imite dans le nom affiché (annuaire fictif).
PERSONNES_INTERNES = {
    "claire vasseur": "Claire Vasseur, PDG d'Orbis Pay",
    "marc delaunay": "Marc Delaunay, directeur financier d'Orbis Pay",
}

# Seul le serveur de réception d'Orbis Pay a le droit de poser Authentication-Results.
# Un tel en-tête écrit par l'expéditeur lui-même est ignoré.
SERVEURS_AUTH_DE_CONFIANCE = {"mx.orbispay.example"}

SEUIL_FRAUDULEUX = 0.6
SEUIL_SUSPECT = 0.25

CONSEILS = {
    "frauduleux": "Sûrement frauduleux. Ne cliquez sur aucun lien, n'ouvrez pas les pièces jointes et ne répondez pas.",
    "suspect": "Douteux. Vérifiez auprès de l'expéditeur par un autre moyen (téléphone, contact connu) avant d'agir.",
    "sur": "Aucun signal de fraude repéré.",
}


# --- Outils de texte --------------------------------------------------------------------

ZERO_WIDTH = "​‌‍⁠﻿᠎"
BIDI = "‪‫‬‭‮⁦⁧⁨⁩"
_INVISIBLES = re.compile(f"[{ZERO_WIDTH}{BIDI}]")
_TAGS = re.compile("[\U000e0000-\U000e007f]")
_ESPACES = re.compile(r"\s+")


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, sans caractères invisibles, espaces simples."""
    t = unicodedata.normalize("NFKC", texte or "")
    t = _INVISIBLES.sub("", _TAGS.sub("", t))
    t = t.replace("’", "'").replace("‘", "'").replace("`", "'")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return _ESPACES.sub(" ", t.lower()).strip()


def citer(texte: str, limite: int = 70) -> str:
    """Extrait court et inerte d'un texte venu du mail, pour une phrase de raison."""
    t = unicodedata.normalize("NFKC", texte or "")
    t = _INVISIBLES.sub("", _TAGS.sub("", t))
    t = "".join(c for c in t if unicodedata.category(c)[0] != "C")
    t = _ESPACES.sub(" ", t).strip()
    return t if len(t) <= limite else t[: limite - 1].rstrip() + "…"


_TLD_DESARMES = r"(?:example|com|fr|net|org|io|ai|dev|app|eu|co|info|biz|xyz|ru|cn|top|online|site|shop)"
_HOTE_TEXTE = re.compile(rf"(?<![\w.\[-])((?:[a-z0-9-]+\.)+{_TLD_DESARMES})\b", re.IGNORECASE)
_SCHEMA = re.compile(r"\bhttp(s?)://", re.IGNORECASE)


def desarmer(texte: str, limite: int = 20000) -> str:
    """Texte lisible et inerte : liens en hxxp(s)://, domaines et adresses en [.].

    Le résultat est du texte brut à afficher tel quel, jamais du HTML.
    """
    t = unicodedata.normalize("NFKC", texte or "")
    t = _TAGS.sub("", t)
    t = "".join(c for c in t if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf"))
    t = _SCHEMA.sub(lambda m: f"hxxp{m.group(1)}://", t)
    t = _HOTE_TEXTE.sub(lambda m: m.group(1).replace(".", "[.]"), t)
    return t if len(t) <= limite else t[:limite].rstrip() + " […]"


# --- Domaines ---------------------------------------------------------------------------

_SUFFIXES_DOUBLES = {"co.uk", "com.au", "co.jp", "gouv.fr", "com.br", "co.nz"}


def normaliser_domaine(domaine: str) -> str:
    d = (domaine or "").strip().strip(".").lower()
    if "xn--" in d:
        try:
            d = d.encode("ascii").decode("idna")
        except (UnicodeError, ValueError):
            pass
    return d


def domaine_enregistrable(domaine: str) -> str:
    """orbispay-verification.example pour mx.orbispay-verification.example."""
    d = normaliser_domaine(domaine)
    morceaux = d.split(".")
    if len(morceaux) >= 3 and ".".join(morceaux[-2:]) in _SUFFIXES_DOUBLES:
        return ".".join(morceaux[-3:])
    return ".".join(morceaux[-2:])


def domaine_de(adresse: str) -> str:
    return normaliser_domaine(adresse.rsplit("@", 1)[1]) if "@" in (adresse or "") else ""


def domaine_de_confiance(domaine: str) -> str | None:
    """Le domaine de confiance dont `domaine` fait partie (lui-même ou un sous-domaine)."""
    d = normaliser_domaine(domaine)
    for conf in DOMAINES_DE_CONFIANCE:
        if d == conf or d.endswith("." + conf):
            return conf
    return None


def est_interne(domaine: str) -> bool:
    return domaine_de_confiance(domaine) == DOMAINE_ORBIS


_CONFUSABLES = str.maketrans({
    "0": "o", "1": "l", "i": "l", "|": "l", "3": "e", "5": "s", "4": "a", "7": "t",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "l",
    "ј": "j", "ѕ": "s", "ԁ": "d", "ı": "l", "ο": "o", "α": "a", "ρ": "p", "ν": "v",
    "κ": "k", "τ": "t", "ɡ": "g", "ⅼ": "l",
})


def squelette(nom: str) -> str:
    """Forme qui confond les caractères qui se ressemblent (0/o, 1/l/i, cyrillique, rn/m)."""
    t = "".join(c for c in unicodedata.normalize("NFKD", nom.lower()) if not unicodedata.combining(c))
    t = t.translate(_CONFUSABLES)
    return t.replace("rn", "m").replace("vv", "w")


def distance(a: str, b: str) -> int:
    """Distance d'édition avec transposition (deux lettres inversées comptent pour une)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cout = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cout)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


@dataclass
class Sosie:
    domaine: str        # le domaine suspect, tel qu'il apparaît
    imite: str          # le domaine de confiance imité
    nature: str         # marque_ajoutee | faute | homoglyphe | extension | sous_domaine
    detail: str = ""    # la marque recopiée, ou le vrai domaine derrière le préfixe


def chercher_sosie(domaine: str) -> Sosie | None:
    d = normaliser_domaine(domaine)
    if not d or "." not in d or domaine_de_confiance(d):
        return None
    try:
        ipaddress.ip_address(d)
        return None
    except ValueError:
        pass
    reg = domaine_enregistrable(d)
    nom = reg.rsplit(".", 1)[0]
    compact = squelette(nom).replace("-", "")
    for conf, (_, marques) in DOMAINES_DE_CONFIANCE.items():
        nom_conf = conf.rsplit(".", 1)[0]
        compact_conf = squelette(nom_conf).replace("-", "")
        if nom == nom_conf:
            return Sosie(d, conf, "extension")
        if compact == compact_conf:
            return Sosie(d, conf, "homoglyphe")
        seuil = 2 if len(compact_conf) >= 8 else 1
        if len(compact_conf) >= 5 and distance(compact, compact_conf) <= seuil:
            return Sosie(d, conf, "faute")
        for marque in marques:
            if squelette(marque) in compact:
                return Sosie(d, conf, "marque_ajoutee", marque)
        # orbispay.example.connexion-securisee.example : le nom de confiance en préfixe.
        prefixe = d[: -len(reg)].rstrip(".")
        if prefixe and (conf in prefixe or any(squelette(m) in squelette(prefixe).replace("-", "") for m in marques)):
            return Sosie(d, conf, "sous_domaine", reg)
    return None


def phrase_sosie(debut: str, s: Sosie) -> str:
    """Raison lisible. `debut` dit d'où vient le domaine : « L'expéditeur écrit depuis »…"""
    libelle = DOMAINES_DE_CONFIANCE[s.imite][0]
    if s.nature == "marque_ajoutee":
        return (f"{debut} {s.domaine}. Ce domaine reprend le nom « {s.detail} » "
                f"mais n'appartient pas à {libelle}, dont le domaine est {s.imite}.")
    if s.nature == "faute":
        return f"{debut} {s.domaine}, à une ou deux lettres près de {s.imite} ({libelle})."
    if s.nature == "homoglyphe":
        return f"{debut} {s.domaine}, qui imite {s.imite} ({libelle}) avec des caractères qui se ressemblent."
    if s.nature == "extension":
        return f"{debut} {s.domaine} : le nom est celui de {s.imite}, mais l'extension a changé."
    return f"{debut} {s.domaine}. « {s.imite} » n'y est qu'un début d'adresse, le vrai domaine est {s.detail}."


# --- Lecture du mail --------------------------------------------------------------------

@dataclass
class PieceJointe:
    nom: str
    type: str
    taille: int
    contenu: bytes = b""


@dataclass
class Lien:
    destination: str
    texte: str = ""
    origine: str = "html"      # html | texte


@dataclass
class TexteCache:
    texte: str
    technique: str


@dataclass
class MailLu:
    de_nom: str = ""
    de_adresse: str = ""
    repondre_a: list[str] = field(default_factory=list)
    a: list[str] = field(default_factory=list)
    objet: str = ""
    date: str | None = None
    message_id: str = ""
    texte: str = ""
    html: str = ""
    pieces: list[PieceJointe] = field(default_factory=list)
    auth_results: list[str] = field(default_factory=list)
    texte_visible: str = ""
    caches: list[TexteCache] = field(default_factory=list)
    commentaires: list[str] = field(default_factory=list)
    liens: list[Lien] = field(default_factory=list)

    @property
    def de_domaine(self) -> str:
        return domaine_de(self.de_adresse)

    @property
    def lisible(self) -> str:
        """Ce qu'un humain lit : la partie texte, sinon le texte visible du HTML."""
        return self.texte if self.texte.strip() else self.texte_visible


_BALISES_VIDES = {"br", "img", "meta", "link", "input", "hr", "area", "base", "col", "embed",
                  "source", "track", "wbr", "param"}
_BALISES_MUETTES = {"style", "script", "head", "title", "noscript", "template"}
_BLANCS = {"#fff", "#ffffff", "white", "rgb(255,255,255)", "rgba(255,255,255,1)", "#fefefe", "#fdfdfd"}


def _couleur_blanche(c: str) -> bool:
    c = c.strip().lower().replace(" ", "").replace("!important", "")
    if c in _BLANCS:
        return True
    m = re.fullmatch(r"#([0-9a-f]{6})", c)
    return bool(m) and all(int(m.group(1)[i:i + 2], 16) >= 0xF0 for i in (0, 2, 4))


def _technique_cachee(style: str, fond_herite: str | None) -> tuple[str | None, str | None]:
    """(technique qui cache l'élément ou None, couleur de fond posée par l'élément)."""
    s = (style or "").lower().replace(" ", "").replace("\n", "")
    fond = None
    m = re.search(r"background(?:-color)?:([^;]+)", s)
    if m:
        fond = m.group(1).split()[0] if m.group(1) else None
    if re.search(r"display:none", s):
        return "masqué par display:none", fond
    if "visibility:hidden" in s:
        return "masqué par visibility:hidden", fond
    if re.search(r"opacity:0(?:\.0+)?(?:;|$|!)", s):
        return "rendu transparent (opacity:0)", fond
    m = re.search(r"(?:^|;)color:([^;]+)", s)
    if m:
        couleur = m.group(1)
        fond_effectif = fond or fond_herite
        if _couleur_blanche(couleur) and (fond_effectif is None or _couleur_blanche(fond_effectif)):
            return "écrit en blanc sur fond blanc", fond
        if fond_effectif and couleur.replace("!important", "") == fond_effectif.replace("!important", ""):
            return "écrit dans la couleur du fond", fond
    m = re.search(r"font-size:(\d+(?:\.\d+)?)(px|pt|em|rem|%)?", s)
    if m:
        taille, unite = float(m.group(1)), m.group(2) or "px"
        if (unite in ("px", "pt") and taille <= 2) or (unite in ("em", "rem") and taille <= 0.2) or (
            unite == "%" and taille <= 20):
            return "écrit en police quasi nulle", fond
    if re.search(r"(?:^|;)(?:max-)?height:0(?:px)?(?:;|$)", s) and "overflow:hidden" in s:
        return "placé dans un bloc de hauteur nulle", fond
    if re.search(r"(?:left|top|text-indent|margin-left):-\d{3,}", s):
        return "repoussé hors de l'écran", fond
    return None, fond


class _LecteurHTML(HTMLParser):
    """Sépare le texte visible du texte caché, et relève les liens avec leur texte."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pile: list[tuple[str, str | None, str | None]] = []  # (balise, technique, fond)
        self.visible: list[str] = []
        self.caches: list[TexteCache] = []
        self.commentaires: list[str] = []
        self.liens: list[Lien] = []
        self._lien: tuple[str, list[str]] | None = None
        self._muet = 0

    def _technique_active(self) -> str | None:
        return next((t for _, t, _ in reversed(self.pile) if t), None)

    def _fond_actif(self) -> str | None:
        return next((f for _, _, f in reversed(self.pile) if f), None)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in _BALISES_MUETTES:
            self._muet += 1
            self.pile.append((tag, None, None))
            return
        if tag == "a" and a.get("href"):
            self._lien = (a["href"].strip(), [])
        if tag in ("br", "p", "div", "tr", "li"):
            self._ajouter("\n")
        if tag in _BALISES_VIDES:
            return
        fond_attribut = a.get("bgcolor", "").strip().lower() or None
        technique, fond = _technique_cachee(a.get("style", ""), fond_attribut or self._fond_actif())
        if "hidden" in a and technique is None:
            technique = "masqué par l'attribut hidden"
        fond = fond or fond_attribut
        self.pile.append((tag, technique, fond))

    def handle_startendtag(self, tag, attrs):
        if tag == "a":
            return
        self.handle_starttag(tag, attrs)
        if tag not in _BALISES_VIDES and self.pile and self.pile[-1][0] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "a" and self._lien is not None:
            href, morceaux = self._lien
            self.liens.append(Lien(href, _ESPACES.sub(" ", "".join(morceaux)).strip(), "html"))
            self._lien = None
        if not any(t == tag for t, _, _ in self.pile):
            return
        while self.pile:
            t, _, _ = self.pile.pop()
            if t in _BALISES_MUETTES:
                self._muet -= 1
            if t == tag:
                break
        if tag in ("p", "div", "tr", "li", "table", "h1", "h2", "h3"):
            self._ajouter("\n")

    def _ajouter(self, texte: str) -> None:
        technique = self._technique_active()
        if technique:
            if self.caches and self.caches[-1].technique == technique:
                self.caches[-1].texte += texte
            else:
                self.caches.append(TexteCache(texte, technique))
        else:
            self.visible.append(texte)

    def handle_data(self, data):
        if self._muet:
            return
        if self._lien is not None:
            self._lien[1].append(data)
        self._ajouter(data)

    def handle_comment(self, data):
        if data.strip() and not data.strip().lower().startswith("[if"):
            self.commentaires.append(data.strip())


def _texte_part(part) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeError, KeyError, AssertionError):
        brut = part.get_payload(decode=True) or b""
        return brut.decode("utf-8", errors="replace")


def lire(brut: bytes) -> MailLu:
    """Lit un mail brut (RFC 5322). Rien n'est exécuté, rien n'est téléchargé."""
    msg = email.message_from_bytes(brut, policy=email.policy.default)
    m = MailLu()

    def entete(nom: str) -> str:
        try:
            v = msg.get(nom)
            return str(v) if v is not None else ""
        except (ValueError, TypeError, IndexError):
            return ""

    adresses = getaddresses([entete("From")])
    if adresses:
        m.de_nom, m.de_adresse = adresses[0][0].strip(), adresses[0][1].strip().lower()
    m.repondre_a = [a.lower() for _, a in getaddresses([entete("Reply-To")]) if a]
    m.a = [a.lower() for _, a in getaddresses([entete("To"), entete("Cc")]) if a]
    m.objet = entete("Subject")
    m.message_id = entete("Message-ID")
    try:
        d = parsedate_to_datetime(entete("Date")) if entete("Date") else None
        m.date = d.isoformat() if d else None
    except (TypeError, ValueError, IndexError):
        m.date = None
    m.auth_results = [str(v) for v in (msg.get_all("Authentication-Results") or [])]

    for part in msg.walk():
        if part.is_multipart():
            continue
        nom = part.get_filename()
        dispo = part.get_content_disposition()
        ctype = part.get_content_type()
        if nom or dispo == "attachment":
            contenu = part.get_payload(decode=True) or b""
            m.pieces.append(PieceJointe(nom or "(sans nom)", ctype, len(contenu), contenu))
        elif ctype == "text/plain" and not m.texte:
            m.texte = _texte_part(part)
        elif ctype == "text/html" and not m.html:
            m.html = _texte_part(part)

    if m.html:
        lecteur = _LecteurHTML()
        try:
            lecteur.feed(m.html)
            lecteur.close()
        except (AssertionError, ValueError):
            pass
        m.texte_visible = re.sub(r"\n\s*\n+", "\n\n", "".join(lecteur.visible)).strip()
        m.caches = [c for c in lecteur.caches if c.texte.strip()]
        for c in m.caches:
            c.texte = _ESPACES.sub(" ", c.texte).strip()
        m.commentaires = lecteur.commentaires
        m.liens = lecteur.liens
    vus = {l.destination for l in m.liens}
    for url in re.findall(r"https?://[^\s<>\"')\]]+", m.texte or ""):
        url = url.rstrip(".,;:!?")
        if url not in vus:
            vus.add(url)
            m.liens.append(Lien(url, "", "texte"))
    return m


# --- Signaux ----------------------------------------------------------------------------

@dataclass
class Signal:
    code: str
    poids: float
    raison: str
    preuve: str = ""

    def json(self) -> dict:
        return {"code": self.code, "poids": self.poids, "raison": self.raison, "preuve": self.preuve}


def hote_de(url: str) -> str:
    try:
        return normaliser_domaine(urlsplit(url).hostname or "")
    except ValueError:
        return ""


_DOMAINE_AFFICHE = re.compile(r"^(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/:?#]\S*)?$", re.I)


def signaux_expediteur(m: MailLu) -> list[Signal]:
    signaux: list[Signal] = []
    sosie = chercher_sosie(m.de_domaine)
    if sosie:
        signaux.append(Signal("sosie_domaine", 0.6, phrase_sosie("L'expéditeur écrit depuis", sosie), sosie.domaine))

    nom = normaliser(m.de_nom)
    if m.de_adresse and not est_interne(m.de_domaine) and not sosie:
        personne = next((v for k, v in PERSONNES_INTERNES.items() if k in nom), None)
        if personne:
            signaux.append(Signal(
                "nom_affiche_trompeur", 0.4,
                f"Le nom affiché est celui de {personne}, mais l'adresse réelle est {m.de_adresse}, "
                f"hors du domaine {DOMAINE_ORBIS}.", m.de_adresse))
        elif re.search(r"orbis\s?pay|orbispay", nom):
            signaux.append(Signal(
                "nom_affiche_trompeur", 0.4,
                f"Le nom affiché, « {citer(m.de_nom, 50)} », se présente comme Orbis Pay, mais l'adresse "
                f"réelle est {m.de_adresse}, hors du domaine {DOMAINE_ORBIS}.", m.de_adresse))
    adresse_dans_nom = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", m.de_nom or "")
    if adresse_dans_nom and adresse_dans_nom.group(0).lower() != m.de_adresse:
        signaux.append(Signal(
            "nom_affiche_trompeur", 0.4,
            f"Le nom affiché contient l'adresse {citer(adresse_dans_nom.group(0), 60)}, "
            f"alors que le mail vient de {m.de_adresse}.", m.de_adresse))

    for adresse in m.repondre_a:
        dom = domaine_de(adresse)
        if not dom or domaine_enregistrable(dom) == domaine_enregistrable(m.de_domaine):
            continue
        s = chercher_sosie(dom)
        if s:
            if not sosie or s.domaine != sosie.domaine:
                signaux.append(Signal("sosie_domaine", 0.5, phrase_sosie("Les réponses partent vers", s), s.domaine))
        elif not est_interne(dom):
            signaux.append(Signal(
                "reponse_detournee", 0.25,
                f"Les réponses partent vers {adresse}, pas vers l'adresse de l'expéditeur ({m.de_adresse}).",
                adresse))
        break
    return signaux


def signaux_liens(m: MailLu, deja: set[str]) -> list[Signal]:
    signaux: list[Signal] = []
    sosies_vus = set(deja)
    for lien in m.liens:
        if not re.match(r"^https?://", lien.destination, re.I):
            continue
        hote = hote_de(lien.destination)
        if not hote:
            continue
        try:
            infos = urlsplit(lien.destination)
            a_identifiant = infos.username is not None
        except ValueError:
            a_identifiant = False
        if a_identifiant:
            leurre = lien.destination.split("://", 1)[1].split("@", 1)[0]
            signaux.append(Signal(
                "lien_menteur", 0.5,
                f"Le lien commence par « {citer(leurre, 40)} » mais mène en réalité à {hote} : "
                "le navigateur ignore tout ce qui précède le @.", hote))
        else:
            affiche = _DOMAINE_AFFICHE.match(normaliser(lien.texte)) if lien.texte else None
            if affiche:
                dom_affiche = normaliser_domaine(affiche.group(1))
                if domaine_enregistrable(dom_affiche) != domaine_enregistrable(hote):
                    signaux.append(Signal(
                        "lien_menteur", 0.6,
                        f"Le lien affiche {dom_affiche} mais mène à {hote}.", hote))
        try:
            ipaddress.ip_address(hote.strip("[]"))
            signaux.append(Signal(
                "lien_menteur", 0.35,
                f"Un lien mène à une adresse IP brute ({hote}) au lieu d'un nom de domaine.", hote))
            continue
        except ValueError:
            pass
        s = chercher_sosie(hote)
        if s and s.domaine not in sosies_vus:
            sosies_vus.add(s.domaine)
            signaux.append(Signal("sosie_domaine", 0.5, phrase_sosie("Un lien du mail mène à", s), s.domaine))
    return signaux


_EXECUTABLES = {".exe", ".scr", ".com", ".bat", ".cmd", ".pif", ".vbs", ".vbe", ".js", ".jse", ".wsf",
                ".wsh", ".ps1", ".msi", ".msp", ".hta", ".jar", ".lnk", ".cpl", ".reg", ".iso", ".img",
                ".vhd", ".dll", ".app", ".command", ".sh", ".apk", ".dmg", ".pkg"}
_MACROS = {".docm", ".dotm", ".xlsm", ".xltm", ".xlam", ".pptm", ".potm", ".ppam", ".ppsm", ".sldm"}
_OFFICE_ZIP = {".docx", ".xlsx", ".pptx"} | _MACROS
_LEURRES_EXT = {".pdf": "un PDF", ".doc": "un document Word", ".docx": "un document Word",
                ".xls": "un tableur Excel", ".xlsx": "un tableur Excel", ".jpg": "une image",
                ".jpeg": "une image", ".png": "une image", ".txt": "un fichier texte", ".zip": "une archive"}
_DEMANDE_MACRO = re.compile(r"activ(?:ez|er) (?:les macros|le contenu|la modification)|enable (?:content|macros|editing)")


def _extensions(nom: str) -> list[str]:
    morceaux = nom.lower().split(".")
    return ["." + x.strip() for x in morceaux[1:]] if len(morceaux) > 1 else []


def _noms_zip(contenu: bytes) -> list[str]:
    if not contenu.startswith(b"PK") or len(contenu) > 20_000_000:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(contenu)) as z:
            return [n.lower() for n in z.namelist()[:2000]]
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
        return []


def signaux_pieces(m: MailLu) -> list[Signal]:
    signaux: list[Signal] = []
    demande_macro = bool(_DEMANDE_MACRO.search(normaliser(m.objet + " " + m.lisible)))
    for p in m.pieces:
        nom_brut = p.nom
        nom = citer(nom_brut, 80)
        if any(c in nom_brut for c in BIDI):
            vrai = _INVISIBLES.sub("", nom_brut)
            signaux.append(Signal(
                "piece_jointe_dangereuse", 0.7,
                f"Le nom de la pièce jointe contient un caractère qui inverse le sens d'affichage : "
                f"le vrai nom se termine par {_extensions(vrai)[-1] if _extensions(vrai) else 'une autre extension'}.",
                nom))
            continue
        exts = _extensions(nom_brut)
        derniere = exts[-1] if exts else ""
        if derniere in _EXECUTABLES:
            avant = exts[-2] if len(exts) >= 2 else ""
            if avant in _LEURRES_EXT:
                raison = (f"La pièce jointe {nom} se fait passer pour {_LEURRES_EXT[avant]}, "
                          f"mais c'est un programme ({derniere}) qui s'exécute à l'ouverture.")
                signaux.append(Signal("piece_jointe_dangereuse", 0.7, raison, nom))
            else:
                signaux.append(Signal(
                    "piece_jointe_dangereuse", 0.6,
                    f"La pièce jointe {nom} est un programme ({derniere}) : l'ouvrir lance du code sur le poste.",
                    nom))
            continue
        noms = _noms_zip(p.contenu) if derniere in _OFFICE_ZIP | {".zip"} else []
        macro = derniere in _MACROS or any(n.endswith("vbaproject.bin") for n in noms)
        if macro:
            raison = (f"La pièce jointe {nom} contient des macros, du code qui s'exécute "
                      "si l'on clique sur « Activer le contenu »")
            raison += ", et le mail demande justement de les activer." if demande_macro else "."
            signaux.append(Signal("piece_jointe_dangereuse", 0.65 if demande_macro else 0.5, raison, nom))
            continue
        if derniere == ".zip":
            caches = [n for n in noms if any(n.endswith(e) for e in _EXECUTABLES)]
            if caches:
                signaux.append(Signal(
                    "piece_jointe_dangereuse", 0.6,
                    f"L'archive {nom} contient un programme ({citer(caches[0].rsplit('/', 1)[-1], 50)}).",
                    nom))
    return signaux


# Pression : urgence ou secret. Chaque motif porte le libellé cité dans la raison.
_URGENCE = [
    (r"\burgent(?:e|s)?\b|\burgence\b", None),
    (r"\bimmediat(?:ement|e)?\b", "immédiatement"),
    (r"\bsans delai\b", "sans délai"),
    (r"\baujourd'hui meme\b|\bavant ce soir\b|\bavant (?:la fin de (?:la )?journee|\d{1,2} ?h(?:\d{2})?)\b", "aujourd'hui"),
    (r"\bdans l'heure\b|\bau plus vite\b|\bdans les plus brefs delais\b", "au plus vite"),
    (r"\bsous (?:24|48|72) ?h(?:eures)?\b|\bwithin 24 hours\b", None),
    (r"\bdern(?:ier|iere) (?:rappel|relance|avertissement)\b", "dernier rappel"),
    (r"\b(?:sera|seront|va etre|vont etre) (?:suspendu|bloque|desactive|ferme|supprime)e?s?\b|\baccount (?:will be )?suspended\b", "compte bientôt bloqué"),
    (r"\bstrictement confidentiel(?:le)?s?\b|\bdiscretion (?:absolue|totale)\b|\bn'en parle[sz]? a personne\b|\bne pas en parler\b|\bentre nous\b", "strictement confidentiel"),
    (r"\bimmediately\b|\basap\b", "immediately"),
]
_ARGENT = [
    (r"\bvirement\b|\bwire transfer\b", "virement"),
    (r"\biban\b|\brib\b|\bbic\b|\bcoordonnees bancaires\b", "coordonnées bancaires"),
    (r"\bcartes? cadeaux?\b|\bgift cards?\b", "cartes cadeaux"),
    (r"\bregler\b|\breglement\b|\bpaiement\b|\bpayment\b|\btransfert de fonds\b", "paiement"),
    (r"\bbitcoin\b|\bcrypto(?:monnaie)?s?\b", "cryptomonnaie"),
]
_CHANGEMENT_BANCAIRE = re.compile(
    r"\bnouv(?:eau|el|elles?) (?:rib|iban|coordonnees bancaires|compte bancaire|banque)\b"
    r"|\bchangement de (?:rib|banque|coordonnees bancaires|compte bancaire)\b"
    r"|\b(?:modifier|mettre a jour|mise a jour de|changer) (?:votre |vos |son |ses |notre |nos |le |les )?(?:rib|iban|coordonnees bancaires)\b")
_IDENTIFIANTS = [
    (r"\bmot de passe\b|\bpassword\b", "mot de passe"),
    (r"\bidentifiants?\b|\bcredentials\b", "identifiants"),
    (r"\b(?:verifiez|confirmez|validez|reactivez) (?:votre|vos) (?:compte|identite|acces)\b|\bverify your account\b", "vérifier le compte"),
    (r"\bcode (?:de verification|recu par sms)\b", "code de vérification"),
]
_MONTANT = re.compile(r"\b\d{1,3}(?:[ .]\d{3})*(?:,\d{2})?\s?(?:€|eur\b|euros\b)")


def _trouves(motifs: list[tuple[str, str | None]], texte: str) -> list[str]:
    """Libellés des motifs présents. Sans libellé, on cite le passage trouvé (déjà sans accent)."""
    vus: list[str] = []
    for motif, libelle in motifs:
        trouve = re.search(motif, texte)
        if trouve:
            l = libelle or trouve.group(0)
            if l not in vus:
                vus.append(l)
    return vus


def _liste(libelles: list[str], n: int = 2) -> str:
    return ", ".join(f"« {l} »" for l in libelles[:n])


def signaux_pression(m: MailLu, fraude_president: bool) -> list[Signal]:
    texte = normaliser(m.objet + "\n" + m.lisible)
    urgence = _trouves(_URGENCE, texte)
    argent = _trouves(_ARGENT, texte)
    montant = _MONTANT.search(texte)
    if montant:
        argent = [montant.group(0).strip()] + argent
    identifiants = _trouves(_IDENTIFIANTS, texte)
    signaux: list[Signal] = []
    if urgence and argent:
        schema = ("C'est le schéma de la fraude au président." if fraude_president
                  else "Les fraudes au virement prennent souvent cette forme.")
        signaux.append(Signal(
            "urgence_argent", 0.45,
            f"Le mail presse ({_liste(urgence)}) et demande de l'argent ({_liste(argent)}). {schema}",
            ", ".join(urgence + argent)))
    if urgence and identifiants:
        signaux.append(Signal(
            "urgence_identifiants", 0.4,
            f"Le mail presse ({_liste(urgence)}) et réclame vos accès ({_liste(identifiants)}). "
            "Un service sérieux ne demande jamais un mot de passe par mail.",
            ", ".join(urgence + identifiants)))
    changement = _CHANGEMENT_BANCAIRE.search(texte)
    if changement:
        signaux.append(Signal(
            "changement_bancaire", 0.35,
            "Le mail demande de modifier des coordonnées bancaires. Un changement de RIB se vérifie "
            "par téléphone, auprès d'un contact déjà connu.",
            changement.group(0)))
    return signaux


# Consignes adressées à un modèle, en plusieurs langues (texte normalisé, sans accents).
_INJECTIONS = [
    (r"ignore[rz]? (?:toutes |tout )?(?:les |tes |vos |ces )?(?:instructions|consignes|regles)(?: \w+)? (?:precedentes|anterieures|ci-dessus|d'avant)", "ignore les instructions précédentes"),
    (r"oublie[rz]? (?:toutes )?(?:les |tes |vos )?(?:instructions|consignes|regles)", "oublie tes consignes"),
    (r"ne tiens? (?:plus |pas )?compte (?:des|de tes) (?:instructions|consignes)", "ne tiens plus compte des consignes"),
    (r"\b(?:tu es|vous etes) (?:maintenant|desormais) (?:un|une|le|la)\b", "tu es maintenant"),
    (r"n'en (?:parle|informe)[sz]? (?:pas|jamais|surtout pas) (?:a )?l'utilisateur|sans (?:en )?(?:informer|prevenir) l'utilisateur", "n'en parle pas à l'utilisateur"),
    (r"ignore (?:all |any )?(?:of )?(?:the |your )?(?:previous|prior|above|earlier) (?:instructions|prompts|directions|messages)", "ignore previous instructions"),
    (r"disregard (?:all |any )?(?:the |your )?(?:previous|prior|above) ", "disregard previous instructions"),
    (r"forget (?:all |your |the )?(?:previous |prior )?instructions", "forget your instructions"),
    (r"\byou are now (?:a|an|the)\b", "you are now"),
    (r"do not (?:tell|inform|mention (?:this |it )?to) the user", "do not tell the user"),
    (r"\b(?:system|developer) prompt\b", "system prompt"),
    (r"ignora (?:todas )?(?:las )?instrucciones (?:anteriores|previas)", "ignora las instrucciones anteriores"),
    (r"olvida (?:tus|las) instrucciones", "olvida tus instrucciones"),
    (r"ignoriere (?:alle )?(?:vorherigen|bisherigen|obigen) (?:anweisungen|instruktionen)", "ignoriere alle vorherigen Anweisungen"),
    (r"vergiss (?:alle )?(?:deine |vorherigen )?anweisungen", "vergiss deine Anweisungen"),
    (r"ignora (?:tutte )?le istruzioni precedenti", "ignora le istruzioni precedenti"),
    (r"ignor[ae] (?:todas )?as instrucoes anteriores", "ignore as instruções anteriores"),
]
_DESTINATAIRE_IA = re.compile(r"\b(?:assistant|agent|ia|ai|llm|chatbot|copilot|modele|model|gpt|claude)\b")
_IMPERATIF = re.compile(
    r"\b(?:transfere[rz]?|envoie[rz]?|envoyez|forward|send|exporte[rz]?|copie[rz]?|reponds|repondez|execute[rz]?"
    r"|appelle[rz]?|clique[rz]?|supprime[rz]?|ajoute[rz]?|ignore[rz]?|oublie[rz]?|resume[rz]?|partage[rz]?|transmets|transmettez)\b")


def chercher_injection(texte: str) -> str | None:
    t = normaliser(texte)
    for motif, libelle in _INJECTIONS:
        if re.search(motif, t):
            return libelle
    return None


def signaux_instruction_cachee(m: MailLu) -> list[Signal]:
    signaux: list[Signal] = []
    for cache in m.caches:
        injection = chercher_injection(cache.texte)
        t = normaliser(cache.texte)
        if injection or (_DESTINATAIRE_IA.search(t) and _IMPERATIF.search(t)):
            quoi = f"la phrase « {injection} »" if injection else "des ordres adressés à un assistant IA"
            signaux.append(Signal(
                "instruction_cachee", 0.7,
                f"Le mail contient un passage invisible, {cache.technique}, avec {quoi}. Un humain ne le "
                "voit pas, mais un assistant IA qui lit le mail le prendrait pour une consigne.",
                citer(cache.texte, 120)))
            return signaux
    for commentaire in m.commentaires:
        injection = chercher_injection(commentaire)
        if injection:
            signaux.append(Signal(
                "instruction_cachee", 0.7,
                f"Un commentaire invisible du code HTML contient la phrase « {injection} », "
                "destinée à un assistant IA qui lirait le mail.", citer(commentaire, 120)))
            return signaux

    brut = "\n".join([m.objet, m.texte, m.html, *[p.nom for p in m.pieces]])
    tags = "".join(chr(ord(c) - 0xE0000) for c in _TAGS.findall(brut) if 0x20 <= ord(c) - 0xE0000 <= 0x7E)
    if tags.strip():
        injection = chercher_injection(tags)
        precision = f", dont la phrase « {injection} »" if injection else ""
        signaux.append(Signal(
            "instruction_cachee", 0.7 if injection else 0.5,
            "Le mail contient un message écrit en caractères invisibles (« balises Unicode »)"
            f"{precision}. Un humain ne voit rien, un assistant IA le lit.", citer(tags, 120)))
        return signaux

    injection = chercher_injection(m.objet + "\n" + m.lisible)
    if injection:
        signaux.append(Signal(
            "instruction_cachee", 0.6,
            f"Le texte du mail contient la phrase « {injection} », une consigne destinée à détourner "
            "un assistant IA qui lirait le mail.", injection))
        return signaux

    n_invisibles = len(_INVISIBLES.findall(m.objet + m.texte + m.html))
    if n_invisibles >= 3:
        signaux.append(Signal(
            "caracteres_invisibles", 0.35,
            f"Le mail contient {n_invisibles} caractères invisibles glissés dans le texte. "
            "Ils servent à cacher des mots aux filtres sans changer ce que l'on voit.", str(n_invisibles)))
    longueur_cachee = sum(len(c.texte) for c in m.caches)
    if longueur_cachee > 300:
        signaux.append(Signal(
            "texte_cache", 0.15,
            f"Le mail contient {longueur_cachee} caractères de texte invisible à l'écran.", str(longueur_cachee)))
    return signaux


def signaux_authentification(m: MailLu) -> list[Signal]:
    resultats: dict[str, str] = {}
    serveur_vu = ""
    for valeur in m.auth_results:
        v = " ".join(valeur.split())
        serveur = v.split(";", 1)[0].strip().lower()
        if serveur not in SERVEURS_AUTH_DE_CONFIANCE:
            continue
        serveur_vu = serveur
        for meca in ("spf", "dkim", "dmarc"):
            r = re.search(rf"\b{meca}\s*=\s*([a-z]+)", v, re.I)
            if r:
                resultats[meca] = r.group(1).lower()
    echecs = [meca.upper() for meca in ("spf", "dkim", "dmarc")
              if resultats.get(meca) in ("fail", "softfail", "permerror")]
    if not echecs:
        return []
    poids = 0.5 if "DMARC" in echecs else 0.3
    return [Signal(
        "authentification_echec", poids,
        f"Le contrôle d'origine noté par {serveur_vu} est en échec ({', '.join(echecs)}) : "
        f"le serveur qui a envoyé ce mail n'est pas autorisé à écrire au nom de {m.de_domaine or 'cet expéditeur'}.",
        ", ".join(f"{k}={v}" for k, v in resultats.items()))]


# --- Verdict ----------------------------------------------------------------------------

def combiner(signaux: list[Signal]) -> float:
    reste = 1.0
    for s in signaux:
        reste *= 1.0 - max(0.0, min(1.0, s.poids))
    return round(1.0 - reste, 2)


def classer(score: float) -> str:
    if score >= SEUIL_FRAUDULEUX:
        return "frauduleux"
    if score >= SEUIL_SUSPECT:
        return "suspect"
    return "sur"


def signaux_du_mail(m: MailLu) -> list[Signal]:
    signaux = signaux_expediteur(m)
    deja = {s.preuve for s in signaux if s.code == "sosie_domaine"}
    signaux += signaux_liens(m, deja)
    signaux += signaux_pieces(m)
    president = any(s.code == "nom_affiche_trompeur" and ("PDG" in s.raison or "directeur" in s.raison)
                    for s in signaux)
    signaux += signaux_pression(m, president)
    signaux += signaux_instruction_cachee(m)
    signaux += signaux_authentification(m)
    # Un même signal ne compte qu'une fois (deux liens identiques, par exemple).
    uniques: dict[tuple[str, str], Signal] = {}
    for s in signaux:
        uniques.setdefault((s.code, s.raison), s)
    return sorted(uniques.values(), key=lambda s: -s.poids)


TITRES = {
    "sosie_domaine": "domaine qui en imite un autre",
    "nom_affiche_trompeur": "expéditeur déguisé",
    "lien_menteur": "lien trompeur",
    "piece_jointe_dangereuse": "pièce jointe dangereuse",
    "urgence_argent": "demande d'argent pressante",
    "urgence_identifiants": "demande d'identifiants",
    "changement_bancaire": "changement de RIB",
    "instruction_cachee": "consigne cachée pour un assistant IA",
    "caracteres_invisibles": "caractères invisibles",
    "texte_cache": "texte invisible",
    "authentification_echec": "origine non vérifiée",
    "reponse_detournee": "réponses détournées",
}


def _gravite(verdict: str, score: float) -> str:
    if verdict == "frauduleux":
        return "critique" if score >= 0.9 else "haute"
    return "moyenne" if verdict == "suspect" else "faible"


def analyser(m: MailLu, *, id: str = "", recu_a: str | None = None) -> dict:
    """Verdict explicable d'un mail déjà lu."""
    signaux = signaux_du_mail(m)
    score = combiner(signaux)
    verdict = classer(score)
    suspects = {s.preuve for s in signaux if s.code in ("lien_menteur", "sosie_domaine")}
    lien_reel = next((l.destination for l in m.liens if hote_de(l.destination) in suspects), None)
    titre = None
    if signaux and verdict != "sur":
        quoi = TITRES.get(signaux[0].code, "signal de fraude")
        if any("schéma de la fraude au président" in s.raison for s in signaux):
            quoi = "fraude au président"
        titre = ("Mail frauduleux : " if verdict == "frauduleux" else "Mail douteux : ") + quoi
    return {
        "id": id,
        "message_id": m.message_id,
        "recu_a": recu_a or m.date or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "de": {"nom": citer(m.de_nom, 80), "adresse": m.de_adresse, "domaine": m.de_domaine},
        "a": m.a,
        "objet": citer(m.objet, 160),
        "verdict": verdict,
        "frauduleux": verdict == "frauduleux",
        "score": score,
        "gravite": _gravite(verdict, score),
        "titre_alerte": titre,
        "conseil": CONSEILS[verdict],
        "geste": "virement" if any(s.code in ("urgence_argent", "changement_bancaire") for s in signaux) else None,
        "lien_reel": desarmer(lien_reel, 300) if lien_reel else None,
        "raison_principale": signaux[0].raison if signaux else None,
        "raisons": [s.raison for s in signaux],
        "signaux": [s.json() for s in signaux],
        "pieces_jointes": [{"nom": citer(p.nom, 80), "type": p.type, "taille": p.taille} for p in m.pieces],
    }


def analyser_brut(brut: bytes, *, id: str = "", recu_a: str | None = None) -> dict:
    return analyser(lire(brut), id=id, recu_a=recu_a)


def detail(m: MailLu, verdict: dict) -> dict:
    """Le mail complet, désarmé : liens en hxxps://, domaines en [.], aucun HTML."""
    menteurs = {s["preuve"] for s in verdict["signaux"] if s["code"] in ("lien_menteur", "sosie_domaine")}
    liens = []
    for l in m.liens:
        hote = hote_de(l.destination)
        liens.append({
            "texte": desarmer(citer(l.texte, 200)),
            "destination": desarmer(l.destination, 500),
            "domaine": desarmer(hote),
            "suspect": bool(hote) and hote in menteurs,
        })
    return {
        "id": verdict["id"],
        "message_id": desarmer(m.message_id, 300),
        "recu_a": verdict["recu_a"],
        "date": m.date,
        "de": {"nom": desarmer(citer(m.de_nom, 120)), "adresse": desarmer(m.de_adresse),
               "domaine": desarmer(m.de_domaine)},
        "a": [desarmer(x) for x in m.a],
        "repondre_a": [desarmer(x) for x in m.repondre_a],
        "objet": desarmer(citer(m.objet, 300)),
        "texte": desarmer(m.lisible),
        "texte_cache": [{"technique": c.technique, "texte": desarmer(citer(c.texte, 2000))} for c in m.caches],
        "liens": liens,
        "pieces_jointes": [{"nom": desarmer(citer(p.nom, 120)), "type": p.type, "taille": p.taille}
                           for p in m.pieces],
        "authentification": [desarmer(" ".join(v.split()), 500) for v in m.auth_results],
        "verdict": verdict,
    }


def inerte(texte: str, limite: int = 400) -> str:
    """Forme sûre pour un autre service : sans caractère invisible, HTML échappé, bornée."""
    return html.escape(citer(texte, limite), quote=True)
