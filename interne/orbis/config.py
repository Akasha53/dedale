"""Configuration du module interne : backend, modèles, chemins des données."""

from __future__ import annotations

import os
from pathlib import Path

# Racine des données synthétiques (boîte mail + documents).
RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DONNEES = RACINE / "donnees"
FICHIER_MAILS = DOSSIER_DONNEES / "boite_mail.json"
DOSSIER_DOCUMENTS = DOSSIER_DONNEES / "documents"

# Boîte noire : console API du backend (agent A).
BACKEND_BASE = os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700")

# Modèles. Clé dans .env (jamais commité). Sans clé, repli sur `claude -p`.
MODELE_AGENT = os.environ.get("DEDALE_MODELE_AGENT", "claude-sonnet-5-5")
MODELE_LEGER = os.environ.get("DEDALE_MODELE_LEGER", "claude-haiku-5-5")
CLE_API = os.environ.get("ANTHROPIC_API_KEY") or None

# Choix du cerveau : "auto" (api si clé, sinon cli), "api", "cli", "scripte".
# Le cerveau "scripte" est déterministe : il sert aux tests et à la démo reproductible.
CERVEAU = os.environ.get("DEDALE_CERVEAU", "auto")

# Hôtes considérés comme internes (pas d'exfiltration si un lien pointe là).
HOTES_INTERNES = {
    "orbispay.example",
    "intranet.orbispay.example",
    "127.0.0.1",
    "localhost",
}

# Le port de l'agent interne, pour mémoire (le contrat le fixe à 8702).
PORT = 8702
