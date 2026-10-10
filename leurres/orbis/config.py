"""Reglages de la surface. Tout est surchargeable par variables d'environnement."""
from __future__ import annotations

import os

# Backend collecteur (agent A). La surface ne tombe jamais s'il est absent.
BACKEND = os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700").rstrip("/")

# Delai d'appel au backend : le contrat promet une reponse < 50 ms, on coupe large.
TIMEOUT_BACKEND = float(os.environ.get("DEDALE_TIMEOUT_BACKEND", "0.4"))

PORT_HTTP = int(os.environ.get("DEDALE_PORT_HTTP", "8701"))
PORT_MCP = int(os.environ.get("DEDALE_PORT_MCP", "8711"))
HOTE = os.environ.get("DEDALE_HOTE", "127.0.0.1")

# Graine fixe : le labyrinthe doit etre deterministe (meme URL -> meme page).
GRAINE = os.environ.get("DEDALE_GRAINE", "orbis-pay-dedale-2026")

# Bornes du labyrinthe cote serveur (jamais de vraie boucle infinie chez nous).
LABY_SLEEP_MIN = float(os.environ.get("DEDALE_LABY_SLEEP_MIN", "0.6"))
LABY_SLEEP_MAX = float(os.environ.get("DEDALE_LABY_SLEEP_MAX", "2.0"))
LABY_PROFONDEUR_MAX = int(os.environ.get("DEDALE_LABY_PROFONDEUR_MAX", "5000"))

DOMAINE = "orbispay.example"
