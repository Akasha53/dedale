"""Médiation universelle de la passerelle : tout appel d'outil passe le même contrôle.

Avant ce module, la passerelle ne regardait de près que les outils qu'elle connaissait. Un outil
MCP absent de son catalogue (`envoyer_mail`) n'exigeait aucun droit et n'était pas « sortant » :
il passait, canari compris. Un outil de lecture n'était jamais inspecté : ses paramètres
pouvaient porter une donnée vers un serveur externe. Trois contrôles s'appliquent désormais à
chaque appel, avant toute exécution, que l'outil soit connu ou non :

1. Inventaire, refus par défaut. L'outil doit figurer dans la boîte à outils de l'agent (son
   profil dans `agents_orbis`), et un outil MCP doit venir du serveur attendu. Un agent sans
   profil a un inventaire vide : tout ce qu'il appelle est retenu.
2. Empreinte des descriptions MCP. La première description vue d'un outil est gardée (sha256).
   Si elle change pendant la session (empoisonnement d'outil, « rug pull »), le prochain appel
   de cet outil est retenu.
3. Paramètres. Ils sont parcourus récursivement, chaînes décodées comprises (base64, encodage
   d'URL, hexadécimal, sur deux niveaux), à la recherche des canaris, des secrets de format
   connu et des adresses, URL et domaines hors d'Orbis Pay. Un outil qui n'est pas un outil
   d'envoi et dont les paramètres en portent est retenu : c'est un canal de sortie détourné.

Chaque contrôle est publié au backend comme une règle (même usage que `C-4E6B`) : la retenue
ouvre un incident nommé, la décision revient à l'analyste. Ce module ne fait que constater ; la
retenue, l'attente et l'exécution restent dans la passerelle.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote_plus, urlparse

from . import detection, mcp
from .enregistreur import masquer as _masquer_base

# --- règles publiées au backend (natures des canaris-règles) -----------------------------------
REGLE_OUTIL_INCONNU = "C-8A61"
REGLE_CANAL_DETOURNE = "C-5B27"
REGLE_OUTIL_MODIFIE = "C-3F90"

# Motif de retenue = nature de la règle = suffixe du type d'incident (`interne_<nature>`).
OUTIL_INCONNU, CANAL_DETOURNE, OUTIL_MODIFIE = "outil_inconnu", "canal_detourne", "outil_modifie"
MOTIFS = (OUTIL_INCONNU, CANAL_DETOURNE, OUTIL_MODIFIE)
REGLE_PAR_MOTIF = {OUTIL_INCONNU: REGLE_OUTIL_INCONNU, CANAL_DETOURNE: REGLE_CANAL_DETOURNE,
                   OUTIL_MODIFIE: REGLE_OUTIL_MODIFIE}
# Libellé court d'une retenue, repris dans le fil des agents et la boîte noire.
LIBELLES = {
    OUTIL_INCONNU: "outil absent de l’inventaire de l’agent",
    CANAL_DETOURNE: "canal de sortie détourné",
    OUTIL_MODIFIE: "description d’outil MCP modifiée en cours de session",
}

# Outils purement locaux : une fonction du processus, sans entrée-sortie vers un tiers. Leurs
# paramètres sont du texte déjà lu par l'agent (un mail cite des adresses, c'est normal) : on n'y
# cherche pas de destination. Les canaris et les secrets y sont cherchés comme partout.
OUTILS_LOCAUX = frozenset({"resumer", "memoriser"})

# Limites qui bornent le coût d'une inspection. Au-delà, la passerelle ne devine pas : un
# paramètre qu'elle ne peut pas inspecter entièrement retient l'appel (refus par défaut).
_LONGUEUR_MAX = 1_000_000    # caractères par chaîne
_VARIANTES_MAX = 128         # textes décodés par chaîne
_PROFONDEUR = 3              # décodages enchaînés (base64 d'une URL encodée, etc.)


# =============================================================================================
# 1. Inventaire
# =============================================================================================
def inventaire_agent(agent: str | None) -> frozenset[str]:
    """Boîte à outils déclarée de l'agent. Inconnu : inventaire vide (refus par défaut)."""
    from .agents_orbis import PROFILS  # import tardif : agents_orbis importe la passerelle

    profil = PROFILS.get(agent or "")
    return frozenset(profil.outils) if profil is not None else frozenset()


def serveur_de(descripteur) -> str | None:
    serveur = getattr(descripteur, "serveur", None)
    return serveur if isinstance(serveur, str) and serveur else None


def hors_inventaire(nom: str, descripteur, inventaire) -> str | None:
    """Raison lisible si l'appel sort de l'inventaire, None s'il y est.

    Un outil MCP doit venir du serveur que le catalogue lui attribue : le même nom servi par un
    autre serveur, ou un outil natif imité par un serveur MCP, est un outil inconnu."""
    serveur = serveur_de(descripteur)
    if nom not in inventaire:
        ou = f" (serveur MCP {serveur})" if serveur else ""
        return f"outil {nom}{ou} absent de l’inventaire de l’agent"
    if serveur is None:
        return None
    attendu = mcp.PAR_NOM.get(nom)
    if attendu is None:
        return f"outil {nom} servi par le serveur MCP {serveur}, alors que c’est un outil interne"
    if attendu.serveur != serveur:
        return f"outil {nom} servi par {serveur}, alors que l’inventaire l’attend de {attendu.serveur}"
    return None


# =============================================================================================
# 2. Empreintes des descriptions d'outils MCP
# =============================================================================================
def empreinte_description(texte: str) -> str:
    return "sha256:" + hashlib.sha256((texte or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class Empreintes:
    """Première description vue de chaque outil MCP, et les changements constatés depuis."""

    vues: dict[tuple[str, str], str] = field(default_factory=dict)
    changees: dict[tuple[str, str], dict] = field(default_factory=dict)

    def observer(self, descripteur) -> None:
        serveur, nom = serveur_de(descripteur), getattr(descripteur, "nom", None)
        description = getattr(descripteur, "description", None)
        if serveur is None or not isinstance(nom, str) or not isinstance(description, str):
            return
        cle = (serveur, nom)
        actuelle = empreinte_description(description)
        reference = self.vues.setdefault(cle, actuelle)
        if actuelle != reference:
            # La référence reste la première description vue : une reprise par l'analyste libère
            # un appel, elle n'approuve pas la nouvelle description. Un retour à l'original ne
            # lève pas le constat non plus : l'agent a pu lire la version piégée entre-temps.
            self.changees[cle] = {"serveur_mcp": serveur, "outil": nom,
                                  "empreinte_avant": reference, "empreinte_apres": actuelle}

    def changement(self, descripteur) -> dict | None:
        serveur, nom = serveur_de(descripteur), getattr(descripteur, "nom", None)
        if serveur is None or not isinstance(nom, str):
            return None
        return self.changees.get((serveur, nom))


# =============================================================================================
# 3. Inspection des paramètres
# =============================================================================================
_B64 = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){8,}")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]{1,15}://[^\s<>\"'`)\]]+", re.IGNORECASE)
_WWW = re.compile(r"\bwww\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)
# Partie locale bornée : sans borne, une longue chaîne sans « @ » (un bloc base64) coûte un
# temps quadratique.
_MAIL = re.compile(r"[\w.+-]{1,64}@((?:[\w-]{1,63}\.){1,8}[\w-]{2,63})")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Hôte nu dans un texte libre : contrôle de FORME (au moins un point, labels alphanumériques, TLD
# alphabétique d'au moins deux lettres) plutôt qu'une liste de TLD fermée — sinon `evil.ai/x`,
# `evil.gg`, `evil.lol` passaient. Deux garde-fous gardent les faux positifs d'avant :
#   - un hôte suivi d'un contexte d'URL (chemin, port, requête) est pris quel que soit son TLD ;
#   - un hôte nu (sans ce contexte) n'est retenu que si son TLD est un suffixe public connu, pour
#     ne pas prendre un identifiant pointé (« jean.moreau ») pour une destination ;
#   - une extension de fichier (`rapport.pdf`, `data.json`, `archive.zip`) est un nom de fichier,
#     pas un hôte — sauf contexte d'URL (`evil.zip/vol` reste une destination).
_HOTE_TEXTE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,8}[a-z]{2,63}",
                         re.IGNORECASE)
_CONTEXTE_URL = frozenset("/:?#")
_TLD_CONNUS = frozenset((
    "com net org io fr eu de uk es it be ch nl ru cn jp br in us co me info biz xyz top app dev "
    "cloud site online link click example test onion ai gg lol"
).split())
# Famille des canaris d'Orbis Pay, même hors du dictionnaire des jetons.
_FAMILLE_CANARI = re.compile(r"ORBISPAY-?CANARY-?[0-9A-F]{4}", re.IGNORECASE)

# Secrets de format connu (mêmes familles que le garde du poste).
SECRETS_CONNUS: list[tuple[str, re.Pattern]] = [
    ("clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("clé d’accès AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("clé API Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}")),
    ("clé API au format sk-", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("jeton GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("jeton Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("clé API Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jeton JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("mot de passe en clair",
     re.compile(r"(?i)\b(mot de passe|password|passwd|pwd)\s*[:=]\s*\S{6,}")),
    ("secret nommé", re.compile(r"(?i)\b(api[_-]?key|secret|token|bearer)\s*[:=]\s*\S{8,}")),
]


def _imprimable(octets: bytes) -> str | None:
    """Texte UTF-8 lisible, ou None (octets aléatoires : rien à chercher dedans)."""
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not texte:
        return None
    lisibles = sum(1 for c in texte if c.isprintable() or c in "\r\n\t")
    return texte if lisibles / len(texte) >= 0.9 else None


def _b64(fragment: str) -> list[str]:
    sortie = []
    brut = fragment.rstrip("=")
    for alphabet in ("standard", "url"):
        donnees = brut + "=" * (-len(brut) % 4)
        try:
            octets = (base64.urlsafe_b64decode(donnees) if alphabet == "url"
                      else base64.b64decode(donnees, validate=True))
        except (binascii.Error, ValueError):
            continue
        texte = _imprimable(octets)
        if texte and texte not in sortie:
            sortie.append(texte)
    return sortie


def _decoder_une_fois(texte: str) -> list[tuple[str, str]]:
    """(texte décodé, encodage) pour chaque décodage plausible du texte."""
    sortie: list[tuple[str, str]] = []
    if "%" in texte or "+" in texte:
        u = unquote_plus(texte)
        if u != texte:
            sortie.append((u, "encodage d’URL"))
    compact = re.sub(r"\s+", "", texte)
    candidats = [m.group(0) for m in _B64.finditer(texte)]
    if compact != texte and _B64.fullmatch(compact):
        candidats.append(compact)  # base64 coupé en lignes
    for frag in candidats:
        for t in _b64(frag):
            sortie.append((t, "base64"))
    for m in _HEX.finditer(texte):
        texte_hex = _imprimable(bytes.fromhex(m.group(0)))
        if texte_hex:
            sortie.append((texte_hex, "hexadécimal"))
    return sortie


def variantes_completes(texte: str) -> tuple[list[tuple[str, str]], str | None]:
    """Le texte et ses décodages enchaînés : [(texte, encodage)], « en clair » d'abord, plus la
    raison pour laquelle l'inspection n'a pas pu aller au bout (None si elle est complète)."""
    if len(texte) > _LONGUEUR_MAX:
        return [(texte[:_LONGUEUR_MAX], "en clair")], f"paramètre de {len(texte)} caractères"
    vus = {texte}
    sortie = [(texte, "en clair")]
    file = [(texte, "")]
    for _ in range(_PROFONDEUR):
        suivants = []
        for t, chemin in file:
            for decode, enc in _decoder_une_fois(t):
                if decode in vus:
                    continue
                if len(vus) >= _VARIANTES_MAX:
                    return sortie, f"plus de {_VARIANTES_MAX} passages encodés"
                vus.add(decode)
                nom = f"{enc} dans {chemin}" if chemin else enc
                sortie.append((decode, nom))
                suivants.append((decode, nom))
        file = suivants
    if any(d not in vus for t, _ in file for d, _ in _decoder_une_fois(t)):
        return sortie, f"encodage imbriqué sur plus de {_PROFONDEUR} niveaux"
    return sortie, None


def variantes(texte: str) -> list[tuple[str, str]]:
    return variantes_completes(texte)[0]


def _chaines(valeur, cle: str | None = None):
    """(clé, chaîne) pour chaque chaîne d'une valeur, clés de dictionnaire comprises."""
    if isinstance(valeur, dict):
        for k, v in valeur.items():
            if isinstance(k, str):
                yield cle, k
            yield from _chaines(v, str(k).lower())
    elif isinstance(valeur, (list, tuple, set)):
        for v in valeur:
            yield from _chaines(v, cle)
    elif isinstance(valeur, str):
        yield cle, valeur
    elif isinstance(valeur, bytes):
        texte = _imprimable(valeur)
        if texte:
            yield cle, texte


def _fragments(jetons: dict[str, str]) -> dict[str, list[str]]:
    """Morceaux distinctifs d'un jeton (8 caractères et plus) : le jeton recopié sans ses
    tirets, en minuscules ou à moitié reste reconnu."""
    sortie: dict[str, list[str]] = {}
    for cid, jeton in (jetons or {}).items():
        if not jeton:
            continue
        morceaux = [jeton.lower(), jeton.replace("-", "").lower()]
        # Un morceau ne compte que s'il est propre au jeton (lettres ET chiffres) : « ORBISPAY »
        # seul désignerait aussi le domaine de l'entreprise.
        morceaux += [m.lower() for m in re.split(r"[-_.:/\s]+", jeton)
                     if len(m) >= 8 and re.search(r"\d", m) and re.search(r"[a-z]", m, re.I)]
        sortie[cid] = list(dict.fromkeys(morceaux))
    return sortie


def _canaris_dans(texte: str, fragments: dict[str, list[str]]) -> list[str]:
    bas = texte.lower()
    trouves = [cid for cid, morceaux in fragments.items() if any(m in bas for m in morceaux)]
    for m in _FAMILLE_CANARI.finditer(texte):
        cid = "C-" + m.group(0)[-4:].upper()  # ORBISPAY-CANARY-2B91 -> C-2B91
        if cid not in trouves:
            trouves.append(cid)
    return trouves


def _secrets_dans(texte: str) -> list[str]:
    return [libelle for libelle, motif in SECRETS_CONNUS if motif.search(texte)]


def _destinations_dans(texte: str) -> list[str]:
    """Hôtes externes visés par une URL, une adresse mail, un domaine ou une adresse IP."""
    hotes: list[str] = []

    def garder(hote: str | None) -> None:
        hote = (hote or "").lower().strip(".")
        if hote and detection._est_externe(hote) and hote not in hotes:
            hotes.append(hote)

    for m in _URL.finditer(texte):
        try:
            garder(urlparse(m.group(0)).hostname)
        except ValueError:
            continue
    for m in _WWW.finditer(texte):
        garder(m.group(0))
    if "@" in texte:
        for m in _MAIL.finditer(texte):
            garder(m.group(1))
        texte = _MAIL.sub(" ", texte)
    if "." not in texte:
        return hotes  # ni domaine ni adresse IP possibles
    sans_url = _URL.sub(" ", texte)
    for m in _HOTE_TEXTE.finditer(sans_url):
        hote = m.group(0).lower()
        suivant = sans_url[m.end():m.end() + 1]
        tld = hote.rsplit(".", 1)[-1]
        if suivant in _CONTEXTE_URL:               # evil.ai/x, evil.zip?d=1 : URL, tout TLD
            garder(hote)
        elif tld in detection._EXT_FICHIER:        # rapport.pdf, data.json : nom de fichier
            continue
        elif tld in _TLD_CONNUS:                   # hôte nu à suffixe public connu
            garder(hote)
    for m in _IPV4.finditer(sans_url):
        octets = [int(o) for o in m.group(0).split(".")]
        if all(o <= 255 for o in octets) and octets[0] != 127:
            garder(m.group(0))
    return hotes


@dataclass
class Inspection:
    """Ce que portent les paramètres d'un appel. Chaque constat garde son encodage."""

    canaris: list[tuple[str, str]] = field(default_factory=list)       # (id, encodage)
    secrets: list[tuple[str, str]] = field(default_factory=list)       # (libellé, encodage)
    destinations: list[tuple[str, str]] = field(default_factory=list)  # (hôte, encodage)
    incomplete: str | None = None  # raison si un paramètre n'a pas pu être inspecté en entier

    def vide(self) -> bool:
        return not (self.canaris or self.secrets or self.destinations or self.incomplete)

    def encodages(self) -> list[str]:
        tous = [e for _, e in self.canaris + self.secrets + self.destinations]
        return list(dict.fromkeys(e for e in tous if e != "en clair"))

    def resume(self) -> str:
        """« le canari C-2B91 (base64), une destination externe collecte.example »."""
        morceaux = []

        def lister(paires):
            return ", ".join(f"{v} ({e})" if e != "en clair" else v for v, e in paires)

        if self.canaris:
            morceaux.append(("le canari " if len(self.canaris) == 1 else "les canaris ")
                            + lister(self.canaris))
        if self.secrets:
            morceaux.append(("un secret : " if len(self.secrets) == 1 else "des secrets : ")
                            + lister(self.secrets))
        if self.destinations:
            morceaux.append(("une destination externe " if len(self.destinations) == 1
                             else "des destinations externes ") + lister(self.destinations[:4])
                            + (" …" if len(self.destinations) > 4 else ""))
        if self.incomplete:
            morceaux.append(f"un contenu que la passerelle ne peut pas inspecter en entier "
                            f"({self.incomplete})")
        return " et ".join(morceaux)

    def pour_backend(self) -> dict:
        return {"canaris": list(dict.fromkeys(c for c, _ in self.canaris)),
                "secrets": list(dict.fromkeys(s for s, _ in self.secrets)),
                "destinations": list(dict.fromkeys(d for d, _ in self.destinations)),
                "encodages": self.encodages(), "inspection_incomplete": self.incomplete}


def inspecter_parametres(params, jetons: dict[str, str], *, destinations: bool = True) -> Inspection:
    """Parcourt toutes les chaînes des paramètres et leurs décodages."""
    insp = Inspection()
    fragments = _fragments(jetons)

    def ajouter(liste, valeur, enc):
        if all(v != valeur for v, _ in liste):
            liste.append((valeur, enc))

    for cle, chaine in _chaines(params):
        textes, incomplete = variantes_completes(chaine)
        insp.incomplete = insp.incomplete or incomplete
        for texte, enc in textes:
            for cid in _canaris_dans(texte, fragments):
                ajouter(insp.canaris, cid, enc)
            for libelle in _secrets_dans(texte):
                ajouter(insp.secrets, libelle, enc)
            if destinations:
                for hote in _destinations_dans(texte):
                    ajouter(insp.destinations, hote, enc)
        if destinations and cle in detection._CLES_CIBLE:
            # Domaine nu rangé sous une clé de destination (« domaine »: « evil.io »).
            for cible, hote in detection.cibles_externes({cle: chaine}):
                ajouter(insp.destinations, hote, "en clair")
    return insp


# =============================================================================================
# Constats rendus à la passerelle
# =============================================================================================
def examiner(nom: str, params, descripteur, *, inventaire, empreintes: Empreintes,
             jetons: dict[str, str], sortant: bool
             ) -> tuple[list[detection.Trouvaille], Inspection]:
    """Trouvailles de la médiation pour un appel, la règle en tête (elle nomme l'incident).

    - outil hors inventaire : `outil_inconnu`, puis les canaris de ses paramètres ;
    - description MCP changée : `outil_modifie` ;
    - outil connu qui n'est pas un outil d'envoi et dont les paramètres portent un canari, un
      secret ou une destination externe : `canal_detourne`.
    Les canaris trouvés (même encodés) s'ajoutent en `faux_secret`. Pour un outil d'envoi, la
    détection historique (lien externe, faux secret en clair, envoi hors d'Orbis Pay) reste
    celle de la passerelle : seuls les canaris encodés s'y ajoutent."""
    trouvailles: list[detection.Trouvaille] = []
    params = params or {}
    insp = inspecter_parametres(params, jetons, destinations=nom not in OUTILS_LOCAUX)
    raison = hors_inventaire(nom, descripteur, inventaire)
    if raison is not None:
        porte = insp.resume()
        trouvailles.append(detection.Trouvaille(
            type=OUTIL_INCONNU, canari_id=REGLE_OUTIL_INCONNU,
            detail=raison + (f" ; ses paramètres portent {porte}" if porte else "")))
    changement = empreintes.changement(descripteur)
    if changement is not None:
        trouvailles.append(detection.Trouvaille(
            type=OUTIL_MODIFIE, canari_id=REGLE_OUTIL_MODIFIE,
            detail=(f"description de l’outil MCP {changement['outil']} ({changement['serveur_mcp']}) "
                    f"modifiée en cours de session ({changement['empreinte_avant']} → "
                    f"{changement['empreinte_apres']})")))
    if raison is None and not sortant and not insp.vide():
        trouvailles.append(detection.Trouvaille(
            type=CANAL_DETOURNE, canari_id=REGLE_CANAL_DETOURNE,
            detail=f"{nom} n’est pas un outil d’envoi, ses paramètres portent {insp.resume()}"))
    elif raison is None and sortant and insp.incomplete:
        # Un outil d'envoi dont on ne peut pas lire tout le contenu ne part pas sans l'analyste.
        trouvailles.append(detection.Trouvaille(
            type=CANAL_DETOURNE, canari_id=REGLE_CANAL_DETOURNE,
            detail=f"{nom} : contenu impossible à inspecter en entier ({insp.incomplete})"))
    if raison is None and sortant and insp.destinations:
        # Destination externe trouvée dans N'IMPORTE QUEL champ texte, pas seulement les clés-cibles
        # (I2 : une adresse glissée dans `corps`/`texte` échappait à la détection historique, qui ne
        # lit que les clés de destination). Même règle C-4E6B pour que l'incident reste nommé pareil.
        trouvailles.append(detection.Trouvaille(
            type="envoi_externe", canari_id=detection.REGLE_ENVOI_EXTERNE,
            detail=detection.detail_envoi_externe([h for h, _ in insp.destinations])))
    for cid, enc in insp.canaris:
        if sortant and enc == "en clair":
            continue  # déjà vu par la détection historique d'un outil d'envoi
        trouvailles.append(detection.Trouvaille(
            type="faux_secret", canari_id=cid,
            detail=f"faux secret canari {cid} dans les paramètres de {nom}"
                   + ("" if enc == "en clair" else f", {enc}")))
    return trouvailles, insp


def canaris_encodes(texte: str, jetons: dict[str, str]) -> list[detection.Trouvaille]:
    """Canaris présents seulement sous un encodage (base64, URL, hexadécimal) ou en morceau :
    complète la détection historique, qui ne voit que le jeton en clair."""
    sortie = []
    for cid, enc in inspecter_parametres(texte or "", jetons, destinations=False).canaris:
        if enc == "en clair" and any(j and j in (texte or "") for j in jetons.values()):
            continue
        sortie.append(detection.Trouvaille(
            type="faux_secret", canari_id=cid,
            detail=f"faux secret canari {cid} présent en sortie" + ("" if enc == "en clair" else f", {enc}")))
    return sortie


def ordonner(mediation: list, historiques: list) -> list[detection.Trouvaille]:
    """Règles de la médiation d'abord (elles nomment l'incident), puis la détection historique,
    puis les canaris trouvés par la médiation. Sans doublon (même type, même canari)."""
    regles = [t for t in mediation if t.type in MOTIFS]
    autres = [t for t in mediation if t.type not in MOTIFS]
    vus, sortie = set(), []
    for t in regles + list(historiques or []) + autres:
        cle = (t.type, t.canari_id)
        if cle not in vus:
            vus.add(cle)
            sortie.append(t)
    return sortie


def motif(trouvailles) -> str | None:
    """Motif de retenue si la médiation est en tête des trouvailles."""
    if trouvailles and trouvailles[0].type in MOTIFS:
        return trouvailles[0].type
    return None


def raison(trouvailles) -> str | None:
    m = motif(trouvailles)
    if m is None:
        return None
    return f"{LIBELLES[m]}, appel retenu pour l’analyste"


def details(nom: str, descripteur, trouvailles, insp: Inspection, *, agent: str,
            empreintes: Empreintes) -> dict:
    """Champs structurés de l'événement `appel_outil` retenu (paramètres masqués à part)."""
    m = motif(trouvailles)
    if m is None:
        return {}
    corps = {"outil": nom, "serveur_mcp": serveur_de(descripteur), "agent": agent,
             "regle": REGLE_PAR_MOTIF[m], "libelle": LIBELLES[m], **insp.pour_backend()}
    if m == OUTIL_MODIFIE:
        corps.update(empreintes.changement(descripteur) or {})
    return {m: corps}


def detail_retenue(nom: str, trouvailles) -> str:
    tete = trouvailles[0].detail if trouvailles else LIBELLES.get(motif(trouvailles) or "", "")
    return f"{nom} : {tete}. Appel retenu avant exécution."


# =============================================================================================
# Masquage de ce qui part au backend
# =============================================================================================
def _masquer_chaine(texte: str, fragments: dict[str, list[str]]) -> str:
    for libelle, motif_secret in SECRETS_CONNUS:
        texte = motif_secret.sub(f"[{libelle} masqué]", texte)
    # Morceau de canari recopié en clair (sans tirets, en minuscules…).
    for cid, morceaux in fragments.items():
        for m in sorted(morceaux, key=len, reverse=True):
            texte = re.sub(re.escape(m), f"[canari {cid} masqué]", texte, flags=re.IGNORECASE)
    texte = _FAMILLE_CANARI.sub("[canari masqué]", texte)

    if variantes_completes(texte)[1] is not None:
        # Trop long ou trop encodé pour être relu en entier : rien n'en part au backend.
        return f"[paramètre masqué : {variantes_completes(texte)[1]}]"

    # Canari ou secret caché sous un encodage : on remplace le passage encodé.
    def porte(t: str) -> bool:
        return any(_canaris_dans(v, fragments) or _secrets_dans(v)
                   for v, enc in variantes(t) if enc != "en clair")

    if not porte(texte):
        return texte
    for motif_enc, nom in ((_B64, "base64"), (_HEX, "hexadécimal")):
        texte = motif_enc.sub(lambda m: f"[secret masqué, {nom}]" if porte(m.group(0)) else m.group(0),
                              texte)
    if porte(texte):
        return "[paramètre masqué : il porte un secret encodé]"
    return texte


def masquer(valeur, jetons: dict[str, str] | None = None):
    """Masquage historique (jetons canaris, partie requête des URL) plus ce que la médiation
    sait reconnaître : canaris encodés ou recopiés en morceaux, secrets de format connu."""
    valeur = _masquer_base(valeur, jetons)
    fragments = _fragments(jetons or {})

    def parcourir(v):
        if isinstance(v, dict):
            return {k: parcourir(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [parcourir(x) for x in v]
        if isinstance(v, str):
            return _masquer_chaine(v, fragments)
        return v

    return parcourir(valeur)
