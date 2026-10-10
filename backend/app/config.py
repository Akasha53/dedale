"""Configuration centrale. Tout est surchargeable par variable d'environnement."""

from __future__ import annotations

import os
from pathlib import Path

# Racine du dépôt : backend/app/config.py -> parents[2] = racine dédale.
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_DATA = RACINE / "data"

HOTE = os.environ.get("DEDALE_HOTE", "127.0.0.1")
PORT = int(os.environ.get("DEDALE_PORT", "8700"))

# Base SQLite. .gitignore exclut data/*.db : rien de persistant n'est commité.
CHEMIN_DB = Path(os.environ.get("DEDALE_DB", str(DOSSIER_DATA / "dedale.db")))

# Modèles (voir CONTRATS.md). Sans clé API, les tâches légères retombent sur un gabarit.
MODELE_LEGER = os.environ.get("DEDALE_MODELE_LEGER", "claude-haiku-5-5")
MODELE_AGENT = os.environ.get("DEDALE_MODELE_AGENT", "claude-sonnet-5-5")
CLE_API = os.environ.get("ANTHROPIC_API_KEY", "").strip()

# DEDALE_LLM=off coupe tout appel modèle (tests, démo sans réseau) : repli gabarit.
LLM_ACTIF = os.environ.get("DEDALE_LLM", "auto").lower() != "off"

# Seuils de classement (voir classement.py). Exposés ici pour rester lisibles.
SEUIL_AGENT_IA = float(os.environ.get("DEDALE_SEUIL_AGENT_IA", "0.40"))
SEUIL_SCRIPT = float(os.environ.get("DEDALE_SEUIL_SCRIPT", "0.20"))

# Repère Palisade : un agent IA cadence ses requêtes à ~1,7 s.
PALISADE_DELAI = 1.7

# Entreprise fictive (jamais de données réelles).
ENTITE = "Orbis Pay"
ENTITE_DOMAINE = "orbispay.example"


def assurer_dossiers() -> None:
    DOSSIER_DATA.mkdir(parents=True, exist_ok=True)
