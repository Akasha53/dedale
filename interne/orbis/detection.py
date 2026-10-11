"""Détection en sortie : exfiltration EchoLeak et usage d'un faux secret canari.

La passerelle inspecte deux choses sur chaque sortie d'agent et chaque paramètre
d'appel d'outil :

1. Exfiltration de type EchoLeak : un lien ou une image markdown dont l'hôte est externe.
   C'est le vecteur classique où un agent détourné fait « fuiter » une donnée en la
   glissant dans l'URL d'un pixel que le rendu markdown va charger.
2. Usage d'un faux secret canari : la valeur d'un jeton canari apparaît dans la sortie.
3. Envoi vers l'extérieur : un outil sortant vise une adresse, une URL ou un domaine hors de
   la liste interne d'Orbis Pay, même sans lien ni canari dans le contenu.

Le repérage d'une consigne cachée dans un texte lu (`description_piegee`,
`consigne_cachee_dans`) passe par le désarmeur (`desarmeur.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from . import config, desarmeur

# Liens markdown : [texte](url) et images ![texte](url). On capture l'URL, avec ou sans schéma.
_MD_LIEN = re.compile(r"!?\[[^\]]*\]\(\s*(?P<url>[^)\s]+)")
# URL nue dans un texte, en secours : http(s)://, protocol-relative //hôte, www.hôte, ou un
# hôte.tld suivi d'un chemin. Le hôte nu exige un chemin (et un lookbehind qui l'isole d'un
# schéma ou d'une adresse mail) pour ne pas confondre une phrase ordinaire avec une destination.
_URL_FORMES = re.compile(
    r"https?://[^\s<>\"')\]]+"
    r"|(?<![\w./@:-])//(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>\"')\]]*)?"
    r"|(?<![\w./@:-])www\.(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>\"')\]]*)?"
    r"|(?<![\w./@:-])(?:[a-z0-9-]+\.)+[a-z]{2,}/[^\s<>\"')\]]*",
    re.IGNORECASE,
)

# Adresse IPv4 isolée (même motif que `mediation._IPV4`). Une destination peut être une IP nue,
# sans domaine ni schéma : `{"destinataire": "203.0.113.9"}`.
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

# Ancien motif de la détection par simple motif en français. Il vit désormais dans le désarmeur,
# où il n'est plus qu'un signal faible parmi d'autres ; le nom reste pour les appelants.
_MARQUEURS_CONSIGNE_OUTIL = desarmeur.MOTIF_HISTORIQUE_FR

# Règle de la passerelle (publiée au backend comme les canaris) : un outil sortant vise un
# destinataire, une URL ou un domaine hors de la liste interne d'Orbis Pay.
REGLE_ENVOI_EXTERNE = "C-4E6B"


@dataclass
class Trouvaille:
    """Une détection : type, détail lisible, et id de canari concerné s'il y en a un."""

    type: str  # "exfiltration_markdown" | "faux_secret" | "consigne_outil_mcp" | "envoi_externe"
    detail: str
    canari_id: str | None = None


def _hote(url: str) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    # Protocol-relative (//hôte/…) et URL sans schéma (hôte/…) : on pose un schéma pour urlparse.
    if u.startswith("//"):
        u = "http:" + u
    elif "://" not in u:
        u = "http://" + u
    try:
        n = urlparse(u)
        return (n.hostname or "").lower() or None
    except ValueError:
        return None


def _est_externe(hote: str | None) -> bool:
    if not hote:
        return False
    if hote in config.HOTES_INTERNES:
        return False
    # Adresse IPv4 : la boucle locale (127.0.0.0/8) est interne, le reste (hors plages de la
    # config, déjà filtrées ci-dessus) est externe. Pas de sous-domaine à considérer.
    if _IPV4.match(hote):
        return int(hote.split(".", 1)[0]) != 127
    # Sous-domaine d'un hôte interne (ex. a.orbispay.example) : interne.
    return not any(
        hote == h or hote.endswith("." + h) for h in config.HOTES_INTERNES
    )


def detecter_exfiltration(texte: str, *, avec_mail: bool = False) -> list[Trouvaille]:
    """Liens/images markdown et URL nues (avec ou sans schéma) pointant vers un domaine externe.

    `avec_mail` ajoute l'adresse mail nue (`local@hôte.tld`) comme vecteur : c'est une destination
    de sortie. On ne l'active que sur une sortie d'agent ou des paramètres d'outil sortant
    (via `inspecter`), pas sur un contenu lu : un mail reçu cite légitimement une adresse externe."""
    if not texte:
        return []
    urls: list[str] = list(_MD_LIEN.findall(texte))
    # Formes nues non déjà capturées en markdown : http(s)://, //hôte, www.hôte, hôte.tld/chemin.
    for u in _URL_FORMES.findall(texte):
        if u not in urls:
            urls.append(u)
    trouvailles: list[Trouvaille] = []
    vus: set[str] = set()
    for url in urls:
        hote = _hote_cible(url)
        if hote and _est_externe(hote) and url not in vus:
            vus.add(url)
            trouvailles.append(
                Trouvaille(
                    type="exfiltration_markdown",
                    detail=f"lien/image vers domaine externe {hote} : {url}",
                    # Tout exfiltration EchoLeak trahit le suivi de la consigne cachée.
                    canari_id="C-7A3F",
                )
            )
    if avec_mail and "@" in texte:
        for m in _MAIL.finditer(texte):
            hote = m.group(1).lower()
            if _est_externe(hote) and m.group(0) not in vus:
                vus.add(m.group(0))
                trouvailles.append(
                    Trouvaille(
                        type="exfiltration_markdown",
                        detail=f"adresse mail vers domaine externe {hote} : {m.group(0)}",
                        canari_id="C-7A3F",
                    )
                )
    return trouvailles


def detecter_faux_secret(texte: str, jetons: dict[str, str]) -> list[Trouvaille]:
    """Un jeton canari présent dans le texte = faux secret utilisé."""
    if not texte:
        return []
    trouvailles: list[Trouvaille] = []
    for canari_id, jeton in jetons.items():
        if jeton and jeton in texte:
            trouvailles.append(
                Trouvaille(
                    type="faux_secret",
                    detail=f"faux secret canari {canari_id} présent en sortie",
                    canari_id=canari_id,
                )
            )
    return trouvailles


def description_piegee(description: str) -> bool:
    """Vrai si un texte porte une consigne destinée à l'agent (tool poisoning MCP, injection).

    Délègue au désarmeur : techniques de dissimulation (HTML, CSS, Unicode invisible) et formules
    d'injection en six langues. L'ancien motif en français n'y est plus qu'un signal faible : il
    compte dans un passage caché ou à côté d'un signal fort, jamais seul."""
    if not description:
        return False
    return desarmeur.consigne_detectee(description)


def signaux_consigne(texte: str) -> list[str]:
    """Techniques et formules relevées par le désarmeur, pour expliquer une détection."""
    return desarmeur.nettoyer(texte or "").signaux


def consigne_cachee_dans(texte: str) -> bool:
    """Vrai si un texte LU (transcription d'appel, entrée de chatbot, entrée de mémoire) porte
    une consigne cachée. Deux indices : un marqueur de consigne (ex. « note pour l'assistant »,
    « ne pas divulguer ») OU la présence d'un lien/pixel vers un domaine externe — un contenu
    interne sain n'en contient pas. Sert à ATTRIBUER une exfiltration à sa source piégée ; le
    texte n'est jamais lu comme une instruction, seulement classé comme suspect."""
    if not texte:
        return False
    if description_piegee(texte):
        return True
    return bool(detecter_exfiltration(texte))


def detecter_consigne_outil(description: str, canari_id: str | None) -> list[Trouvaille]:
    """Consigne malveillante cachée dans la description d'un outil MCP.

    On ne renvoie QUE le constat (la description est piégée) ; le texte de la consigne n'est
    pas réinjecté dans le détail. Le canari associé permet au backend de nommer l'incident.
    """
    if description_piegee(description):
        return [
            Trouvaille(
                type="consigne_outil_mcp",
                detail="description d'outil MCP porteuse d'une consigne cachée (tool poisoning)",
                canari_id=canari_id,
            )
        ]
    return []


def inspecter(texte: str, jetons: dict[str, str], *, avec_mail: bool = False) -> list[Trouvaille]:
    """Toutes les détections de sortie sur un même texte (exfiltration + faux secret).

    `avec_mail` ajoute l'adresse mail nue comme vecteur d'exfiltration. On ne l'active que sur la
    sortie texte finale de l'agent : dans les paramètres d'un outil sortant, un destinataire
    externe est déjà couvert par l'« envoi externe » (C-4E6B), et le compter en plus comme une
    exfiltration EchoLeak (C-7A3F) nommerait mal un simple envoi au mauvais destinataire."""
    return detecter_exfiltration(texte, avec_mail=avec_mail) + detecter_faux_secret(texte, jetons)


# --- envoi vers l'extérieur ---------------------------------------------------------------
# Paramètres d'un outil sortant qui désignent où part la donnée.
_CLES_CIBLE = {"destinataire", "destinataires", "a", "to", "cc", "cci", "bcc", "copie", "url",
               "lien", "webhook", "endpoint", "domaine", "hote", "adresse", "email", "mail",
               "courriel", "site", "uri"}
_MAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[\w-]+)")
_DOMAINE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.IGNORECASE)
# Un nom de fichier (rapport.md, data.json) n'est pas un hôte : son « TLD » est une extension.
_EXT_FICHIER = {
    "md", "txt", "json", "csv", "pdf", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico",
    "py", "js", "ts", "tsx", "jsx", "html", "htm", "xml", "yml", "yaml", "toml", "ini",
    "cfg", "conf", "env", "log", "lock", "zip", "tar", "gz", "doc", "docx", "xls", "xlsx",
    "ppt", "pptx", "sh", "bat", "exe", "bin", "dat", "db", "sqlite",
}


def _hote_cible(morceau: str) -> str | None:
    """Hôte d'un jeton isolé — URL à schéma ou non, protocol-relative, hôte nu, www. ou adresse
    mail nue — ou None si ce n'est pas un hôte. Écarte les chemins de fichiers locaux (./x, /tmp/x,
    ~/x), les versions (3.14) et les noms de fichiers ; exige un TLD alphabétique plausible."""
    m = (morceau or "").strip().strip("<>\"'()[]")
    if not m:
        return None
    if m.startswith("//") or "://" in m:          # protocol-relative (//hôte) ou URL à schéma
        return _hote(m)
    if m.startswith((".", "/", "~", "\\")):        # chemin de fichier local
        return None
    if "@" in m:                                    # adresse mail nue : local@hôte.tld
        mm = _MAIL.search(m)
        return mm.group(1).lower() if mm else None
    autorite = re.split(r"[/?#]", m, maxsplit=1)[0]  # hôte nu, avec ou sans chemin
    ip = autorite.split(":", 1)[0]                   # IPv4 littérale, port éventuel écarté
    if _IPV4.match(ip):
        octets = [int(o) for o in ip.split(".")]
        return ip if all(o <= 255 for o in octets) else None
    if not _DOMAINE.match(autorite):
        return None
    if autorite.rsplit(".", 1)[-1].lower() in _EXT_FICHIER:
        return None
    return _hote(autorite)


def _cibles(valeur, cle: str | None = None) -> list[str]:
    """Chaînes rangées sous une clé de destination, à toute profondeur."""
    if isinstance(valeur, dict):
        return [c for k, v in valeur.items() for c in _cibles(v, str(k).lower())]
    if isinstance(valeur, (list, tuple)):
        return [c for v in valeur for c in _cibles(v, cle)]
    if isinstance(valeur, str) and cle in _CLES_CIBLE:
        return [valeur]
    return []


def cibles_externes(params: dict) -> list[tuple[str, str]]:
    """(cible, hôte) pour chaque adresse, URL ou domaine hors de la liste interne. Un nom sans
    adresse (« Jean Moreau ») n'est pas résolu : il reste dans l'annuaire interne."""
    trouvees: list[tuple[str, str]] = []
    for brut in _cibles(params or {}):
        for morceau in re.split(r"[,;\s]+", brut.strip()):
            if not morceau:
                continue
            hote = _hote_cible(morceau)
            if hote and _est_externe(hote) and (morceau, hote) not in trouvees:
                trouvees.append((morceau, hote))
    return trouvees


def detail_envoi_externe(noms: list[str]) -> str:
    """Détail lisible d'un envoi externe, à partir des cibles ou des hôtes visés. Partagé avec la
    médiation pour que l'incident C-4E6B soit nommé et décrit de la même façon où qu'il naisse."""
    internes = ", ".join(sorted(h for h in config.HOTES_INTERNES if "." in h and not h[0].isdigit()))
    tete = ", ".join(noms[:3]) + (" …" if len(noms) > 3 else "")
    return f"envoi vers {tete}, hors des domaines d’Orbis Pay ({internes})"


def detecter_envoi_externe(params: dict) -> list[Trouvaille]:
    """Un outil sortant vise l'extérieur : une trouvaille, même sans lien ni canari dans le contenu."""
    cibles = cibles_externes(params)
    if not cibles:
        return []
    return [Trouvaille(
        type="envoi_externe",
        detail=detail_envoi_externe([c for c, _ in cibles]),
        canari_id=REGLE_ENVOI_EXTERNE,
    )]
