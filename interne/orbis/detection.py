"""Détection en sortie : exfiltration EchoLeak et usage d'un faux secret canari.

La passerelle inspecte deux choses sur chaque sortie d'agent et chaque paramètre
d'appel d'outil :

1. Exfiltration de type EchoLeak : un lien ou une image markdown dont l'hôte est externe.
   C'est le vecteur classique où un agent détourné fait « fuiter » une donnée en la
   glissant dans l'URL d'un pixel que le rendu markdown va charger.
2. Usage d'un faux secret canari : la valeur d'un jeton canari apparaît dans la sortie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from . import config

# Liens markdown : [texte](url) et images ![texte](url). On capture l'URL.
_MD_LIEN = re.compile(r"!?\[[^\]]*\]\(\s*(?P<url>[^)\s]+)")
# URL nue http(s) dans un texte, en secours.
_URL_NUE = re.compile(r"https?://[^\s<>\"')]+")

# Marqueurs d'une consigne cachée dans une DESCRIPTION d'outil (tool poisoning MCP) : une
# description qui s'adresse à l'assistant comme à un exécutant (verbe d'action vers une
# donnée sensible + marqueur de dissimulation ou de fausse autorité). Heuristique volontaire :
# on ne lit jamais la description comme une instruction, on la classe comme suspecte.
_MARQUEURS_CONSIGNE_OUTIL = re.compile(
    r"(ne pas divulguer|ne pas (en )?parler|note pour l'assistant|<\s*important\s*>|"
    r"instruction syst|ignore\b|exfiltr|transf[eè]re|relève la cl|"
    r"envoie[sz]?\b.*(copie|rapport|cl[ée]|coffre|secret|externe))",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Trouvaille:
    """Une détection : type, détail lisible, et id de canari concerné s'il y en a un."""

    type: str  # "exfiltration_markdown" | "faux_secret"
    detail: str
    canari_id: str | None = None


def _hote(url: str) -> str | None:
    try:
        n = urlparse(url if "://" in url else "http://" + url)
        return (n.hostname or "").lower() or None
    except ValueError:
        return None


def _est_externe(hote: str | None) -> bool:
    if not hote:
        return False
    if hote in config.HOTES_INTERNES:
        return False
    # Sous-domaine d'un hôte interne (ex. a.orbispay.example) : interne.
    return not any(
        hote == h or hote.endswith("." + h) for h in config.HOTES_INTERNES
    )


def detecter_exfiltration(texte: str) -> list[Trouvaille]:
    """Liens/images markdown (et URL nues) pointant vers un domaine externe."""
    if not texte:
        return []
    urls: list[str] = list(_MD_LIEN.findall(texte))
    # URL nues non déjà capturées en markdown.
    for u in _URL_NUE.findall(texte):
        if u not in urls:
            urls.append(u)
    trouvailles: list[Trouvaille] = []
    vus: set[str] = set()
    for url in urls:
        hote = _hote(url)
        if _est_externe(hote) and url not in vus:
            vus.add(url)
            trouvailles.append(
                Trouvaille(
                    type="exfiltration_markdown",
                    detail=f"lien/image vers domaine externe {hote} : {url}",
                    # Tout exfiltration EchoLeak trahit le suivi de la consigne cachée.
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
    """Vrai si une description d'outil porte une consigne cachée (tool poisoning MCP)."""
    if not description:
        return False
    return bool(_MARQUEURS_CONSIGNE_OUTIL.search(description))


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


def inspecter(texte: str, jetons: dict[str, str]) -> list[Trouvaille]:
    """Toutes les détections de sortie sur un même texte (exfiltration + faux secret)."""
    return detecter_exfiltration(texte) + detecter_faux_secret(texte, jetons)
