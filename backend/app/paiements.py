"""Virement demandé par un agent : montant, bénéficiaire et IBAN masqué, lisibles par le SOC.

La première question d'un RSSI devant un virement bloqué est « combien, et vers qui ? ».
À l'ingestion d'un appel `executer_paiement` (ou `emettre_virement`), le backend pose
`details.virement` à partir des paramètres de l'appel. L'IBAN n'est jamais rendu en entier :
pays, clé, puis les quatre derniers chiffres (`FR76 •••• •••• 6789`).

La passerelle ne transmet pas les paramètres d'un appel refusé d'office (hors du jeton de
tâche). Pour la démo, les valeurs manquantes viennent du bénéficiaire fictif connu ci-dessous,
et `complete_par_demo` le dit. Tout est fictif.
"""

from __future__ import annotations

import re

OUTILS_PAIEMENT = ("executer_paiement", "emettre_virement")

# Bénéficiaires fictifs : identifiant tel que l'agent l'écrit → nom et IBAN.
BENEFICIAIRES = {
    "atelier-nord": {"nom": "Atelier Nord", "iban": "FR7630004000050000123456789"},
}
# Valeurs de la démo quand l'appel n'a rien transmis (scénario « droits trop larges »).
DEMO = {"montant": 3480.0, "devise": "EUR", "beneficiaire": "atelier-nord"}


def masquer_iban(iban: str | None) -> str | None:
    if not iban:
        return None
    brut = re.sub(r"[\s•]", "", str(iban)).upper()
    if len(brut) < 8 or not brut[:2].isalpha():
        return None
    return f"{brut[:4]} •••• •••• {brut[-4:]}"


def _montant(valeur) -> float | None:
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return float(valeur)
    if isinstance(valeur, str):
        m = re.search(r"\d+(?:[.,]\d+)?", valeur.replace(" ", "").replace(" ", ""))
        if m:
            return float(m.group(0).replace(",", "."))
    return None


def resumer(outil: str | None, parametres) -> dict | None:
    """`details.virement` d'un appel de paiement, ou None pour un autre outil."""
    if outil not in OUTILS_PAIEMENT:
        return None
    p = parametres if isinstance(parametres, dict) else {}
    montant = _montant(p.get("montant"))
    cle = str(p.get("beneficiaire") or "").strip()
    complete = False
    if montant is None:
        montant, complete = DEMO["montant"], True
    if not cle:
        cle, complete = DEMO["beneficiaire"], True
    connu = BENEFICIAIRES.get(cle.lower())
    iban = p.get("iban") or (connu or {}).get("iban")
    return {
        "montant": round(montant, 2),
        "devise": str(p.get("devise") or DEMO["devise"])[:3].upper(),
        "beneficiaire": (connu or {}).get("nom") or cle[:80],
        "iban_masque": masquer_iban(iban),
        "complete_par_demo": complete,
    }
