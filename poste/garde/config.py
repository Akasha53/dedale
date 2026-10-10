"""Réglages du poste : backend, domaine de l'entreprise, listes de confiance.

Tout est surchargageable par variable d'environnement pour la démo, mais les
valeurs par défaut suffisent à faire tourner le simulateur hors ligne.
"""

from __future__ import annotations

import os

# Backend (console API). Le poste ne tombe jamais si cette URL ne répond pas.
BACKEND_BASE = os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700")

# Entreprise fictive. Un destinataire ou un domaine qui finit par là est « interne ».
DOMAINE_ENTREPRISE = os.environ.get("ORBIS_DOMAINE", "orbispay.example")

# Services réellement autorisés par la DSI d'Orbis Pay (IA, cloud, outils).
# Un dépôt de fichier confidentiel ailleurs déclenche un avertissement.
DOMAINES_AUTORISES = {
    "orbispay.example",
    "assistant.orbispay.example",   # l'assistant IA interne, hébergé par l'entreprise
    "coffre.orbispay.example",      # gestionnaire de secrets maison
    "drive.orbispay.example",       # cloud d'entreprise
}

# Domaines de phishing connus (liste noire de démonstration, fictive).
PHISHING_CONNUS = {
    "orbispay-secure.com",
    "orbispay-verification.net",
    "login-orbispay.help",
    "secure-paiement-orbis.ru",
}

# Extensions de pièce jointe dangereuses à l'ouverture.
EXTENSIONS_PIEGEES = {
    ".exe", ".scr", ".bat", ".cmd", ".com", ".js", ".vbs",
    ".jar", ".lnk", ".ps1", ".hta", ".iso", ".msi",
}
# Documents à macros, piégés quand ils viennent d'un expéditeur externe.
EXTENSIONS_MACRO = {".docm", ".xlsm", ".pptm"}

# Seuil d'escalade au SOC : au-delà de N avertissements dans la session, ou sur
# une gravité critique, l'événement porte details.escalade = true.
SEUIL_ESCALADE = int(os.environ.get("POSTE_SEUIL_ESCALADE", "3"))
