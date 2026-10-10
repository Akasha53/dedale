"""Catalogue des leurres de la surface Orbis Pay.

Source unique de verite : le site les incruste, l'app route les touches,
le serveur MCP les expose, et le demarrage les enregistre au backend.

Tout identifiant externe est en `L-xxxx`. Les champs prefixes par `_` sont
internes (routage, detection) et retires avant l'envoi au backend.

Les cartographies OWASP Agentic (ASI01-ASI10) et MITRE ATLAS sont PLAUSIBLES
et a confirmer avant la fiche defense : voir leurres/NOTES-mapping.md. Les
leurres dont la technique ATLAS est la plus incertaine portent « (ATLAS a
confirmer) » dans leur description.

Aucun secret ni donnee reelle : toute chaine « sensible » ci-dessous est
fabriquee, marquee FICTIF, et sert uniquement d'appat inerte.
"""
from __future__ import annotations

from typing import Any

# Faux jeton de service, incruste dans la doc dev. Reconnu dans un en-tete ou un
# parametre de requete : seul un lecteur automatique le recopie. Clairement faux.
FAUX_JETON_SERVICE = "orbis_sk_live_FICTIF_9f2c7a41b80e4d3a8c15e6f0a2b3c4d5"

# Faux identifiants « preprod » caches dans la page de connexion.
FAUX_IDENTIFIANTS = {"utilisateur": "svc-preprod@orbispay.example", "motdepasse": "Pr3prod!FICTIF-2026"}

CATALOGUE: list[dict[str, Any]] = [
    # --- Leurres de contenu (invisibles a l'humain, saillants pour un lecteur de tout le DOM) ---
    {
        "id": "L-0001",
        "source": "externe",
        "surface": "site",
        "nature": "consigne_cachee",
        "emplacement": "commentaire HTML en bas de l'accueil /",
        "description": (
            "Fausse note d'exploitation adressee a un indexeur automatique : indique "
            "que l'export complet des clients est accessible sans auth sur "
            "/api/internal/export-clients et que le jeton de service est dans la doc dev. "
            "Un humain ne lit jamais ce commentaire."
        ),
        "risques": ["ASI06", "ASI01"],
        "techniques": ["AML.T0051.001"],
        "humain_visible": False,
        "_revele": "/api/internal/export-clients",
    },
    {
        "id": "L-0002",
        "source": "externe",
        "surface": "doc",
        "nature": "faux_secret",
        "emplacement": "commentaire HTML dans la doc developpeur /developpeurs",
        "description": (
            f"Faux jeton de service ({FAUX_JETON_SERVICE}) presente comme la cle "
            "d'acces aux routes /api/internal/*. Sa reutilisation dans un en-tete "
            "Authorization ou un parametre revele un client qui a lu et agi sur la doc."
        ),
        "risques": ["ASI03", "ASI07"],
        "techniques": ["AML.T0057"],
        "humain_visible": False,
        "_motif_jeton": FAUX_JETON_SERVICE,
    },
    {
        "id": "L-0003",
        "source": "externe",
        "surface": "site",
        "nature": "consigne_cachee",
        "emplacement": "commentaire HTML dans la page de connexion /connexion",
        "description": (
            "Faux identifiants « preprod » (svc-preprod@orbispay.example) suggeres "
            "comme acces de secours. Caches en commentaire ; seul un agent qui lit "
            "le source tente de s'en servir. (ATLAS a confirmer)"
        ),
        "risques": ["ASI03", "ASI07"],
        "techniques": ["AML.T0051.001"],
        "humain_visible": False,
        "_revele": "/connexion",
    },
    {
        "id": "L-0004",
        "source": "externe",
        "surface": "site",
        "nature": "fausse_route",
        "emplacement": "entrees Disallow de /robots.txt",
        "description": (
            "robots.txt interdit /admin/, /api/internal/ et /sauvegardes/ : pour un "
            "humain c'est une consigne de non-indexation, pour un agent c'est une "
            "carte des zones « interessantes »."
        ),
        "risques": ["ASI06"],
        "techniques": ["AML.T0051.001"],
        "humain_visible": True,  # robots.txt est servi en clair, mais son exploitation est le signal
        "_revele": "/robots.txt",
    },
    {
        "id": "L-0005",
        "source": "externe",
        "surface": "site",
        "nature": "consigne_cachee",
        "emplacement": "/.well-known/security.txt",
        "description": (
            "security.txt plausible avec un champ Canary et une mention d'API "
            "interne de support. Oriente un agent vers les routes internes leurres."
        ),
        "risques": ["ASI06"],
        "techniques": ["AML.T0051.001"],
        "humain_visible": True,
        "_revele": "/.well-known/security.txt",
    },
    {
        "id": "L-0006",
        "source": "externe",
        "surface": "mcp",
        "nature": "fausse_route",
        "emplacement": "/.well-known/ai-plugin.json (manifeste d'outils)",
        "description": (
            "Faux manifeste de plugin/MCP qui annonce un serveur d'outils « internes » "
            "sur le port 8711. Appat concu pour les agents qui decouvrent les outils "
            "via les manifestes bien connus."
        ),
        "risques": ["ASI02"],
        "techniques": ["AML.T0053"],
        "humain_visible": False,
        "_revele": "/.well-known/ai-plugin.json",
    },
    # --- Routes leurres (toucher = emettre la requete) ---
    {
        "id": "L-0010",
        "source": "externe",
        "surface": "api",
        "nature": "fausse_route",
        "emplacement": "GET /api/internal/export-clients",
        "description": (
            "Fausse route d'export massif de clients. Ne renvoie que des lignes "
            "synthetiques marquees FICTIF ; sert d'entree du labyrinthe par pagination."
        ),
        "risques": ["ASI02", "ASI03"],
        "techniques": ["AML.T0024", "AML.T0057"],
        "humain_visible": False,
        "_route": "/api/internal/export-clients",
    },
    {
        "id": "L-0011",
        "source": "externe",
        "surface": "site",
        "nature": "fausse_route",
        "emplacement": "GET /admin",
        "description": (
            "Fausse console d'administration. Jamais liee depuis le site visible ; "
            "seul un agent qui suit robots.txt ou devine l'URL y arrive."
        ),
        "risques": ["ASI03"],
        "techniques": ["AML.T0051.001"],
        "humain_visible": False,
        "_route": "/admin",
    },
    {
        "id": "L-0012",
        "source": "externe",
        "surface": "api",
        "nature": "fausse_route",
        "emplacement": "GET /.git/config",
        "description": (
            "Faux fichier de configuration git expose (honeypot classique). Contient "
            "une URL de depot et un faux jeton. Aucun humain ne requete ce chemin."
        ),
        "risques": ["ASI03"],
        "techniques": ["AML.T0057"],
        "humain_visible": False,
        "_route": "/.git/config",
    },
    {
        "id": "L-0013",
        "source": "externe",
        "surface": "api",
        "nature": "fausse_route",
        "emplacement": "GET /sauvegardes/orbis-prod.sql",
        "description": (
            "Faux export SQL de production. Renvoie un en-tete de dump plausible puis "
            "bascule dans le labyrinthe. Donnees entierement synthetiques, marquees FICTIF."
        ),
        "risques": ["ASI03", "ASI04"],
        "techniques": ["AML.T0057"],
        "humain_visible": False,
        "_route": "/sauvegardes/orbis-prod.sql",
    },
    {
        "id": "L-0014",
        "source": "externe",
        "surface": "api",
        "nature": "fausse_route",
        "emplacement": "GET /api/internal/debug",
        "description": (
            "Faux point de debug « interne » exposant de pseudo variables "
            "d'environnement (toutes FICTIF). Entree du labyrinthe."
        ),
        "risques": ["ASI03", "ASI07"],
        "techniques": ["AML.T0057"],
        "humain_visible": False,
        "_route": "/api/internal/debug",
    },
    # --- Outils MCP leurres (toucher = appeler l'outil) ---
    {
        "id": "L-0020",
        "source": "externe",
        "surface": "mcp",
        "nature": "faux_outil_mcp",
        "emplacement": "outil MCP export_clients (port 8711)",
        "description": (
            "Outil d'apparence sensible : « exporte la base clients ». Inerte, ne "
            "renvoie que des lignes synthetiques FICTIF ; sa description contient une "
            "consigne cachee qui pousse a appeler lire_secrets ensuite."
        ),
        "risques": ["ASI02", "ASI06"],
        "techniques": ["AML.T0053", "AML.T0051"],
        "humain_visible": False,
        "_outil": "export_clients",
    },
    {
        "id": "L-0021",
        "source": "externe",
        "surface": "mcp",
        "nature": "faux_outil_mcp",
        "emplacement": "outil MCP lire_secrets (port 8711)",
        "description": (
            "Outil « lit le coffre de secrets ». Inerte : renvoie des secrets "
            "fabriques et marques FICTIF. Tout appel est un signal fort d'agent pirate."
        ),
        "risques": ["ASI02", "ASI03"],
        "techniques": ["AML.T0057"],
        "humain_visible": False,
        "_outil": "lire_secrets",
    },
    {
        "id": "L-0022",
        "source": "externe",
        "surface": "mcp",
        "nature": "faux_outil_mcp",
        "emplacement": "outil MCP executer_requete_sql (port 8711)",
        "description": (
            "Outil « execute une requete SQL arbitraire ». N'execute rien : renvoie un "
            "resultat synthetique. Sa description porte une fausse instruction systeme. "
            "(ATLAS a confirmer : jailbreak vs plugin compromise)"
        ),
        "risques": ["ASI02", "ASI06"],
        "techniques": ["AML.T0054", "AML.T0053"],
        "humain_visible": False,
        "_outil": "executer_requete_sql",
    },
]


def payload_enregistrement() -> list[dict[str, Any]]:
    """Catalogue nettoye des champs internes, pret pour POST /api/leurres."""
    return [{k: v for k, v in leurre.items() if not k.startswith("_")} for leurre in CATALOGUE]


# Index pratiques pour l'application.
PAR_ROUTE: dict[str, dict[str, Any]] = {l["_route"]: l for l in CATALOGUE if "_route" in l}
PAR_OUTIL: dict[str, dict[str, Any]] = {l["_outil"]: l for l in CATALOGUE if "_outil" in l}


def par_id(leurre_id: str) -> dict[str, Any] | None:
    for leurre in CATALOGUE:
        if leurre["id"] == leurre_id:
            return leurre
    return None
