"""Confiance entre agents (V3b) : provenance signée des délégations.

Un orchestrateur délègue des tâches à des sous-agents. Le risque (OWASP Agentic ASI07) :
un message FORGÉ se fait passer pour un agent de confiance quand aucune provenance n'est
vérifiée, ce qui permet une escalade (« l'agent-paie me demande un virement »).

La parade est simple et classique : chaque délégation légitime porte une signature HMAC
calculée avec le secret partagé de l'agent émetteur. Une délégation sans signature, ou avec
une signature invalide, n'est pas authentifiée : on la bloque et on la signale.

Les secrets ci-dessous sont synthétiques et locaux (aucun secret réel). Ce module ne fait
que signer/vérifier ; le blocage effectif vit dans la passerelle.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

# Canari/règle de détection posé sur l'usurpation inter-agent (enregistré au backend).
CANARI_USURPATION = "C-7C34"

# Secrets partagés des agents de confiance (fictifs, locaux). En vrai : coffre, rotation.
_SECRETS: dict[str, bytes] = {
    "agent-paie": b"orbis-demo-secret-paie-3c1f",
    "agent-rh": b"orbis-demo-secret-rh-9a2d",
    "orchestrateur": b"orbis-demo-secret-orch-5b7e",
}


@dataclass(frozen=True)
class Delegation:
    """Un message de délégation d'un agent à un autre."""

    expediteur: str
    message: str
    signature: str | None = None


def signer(expediteur: str, message: str) -> str:
    """Signature HMAC-SHA256 d'un message par un agent de confiance connu."""
    cle = _SECRETS[expediteur]
    return hmac.new(cle, message.encode("utf-8"), hashlib.sha256).hexdigest()


def deleguer(expediteur: str, message: str) -> Delegation:
    """Fabrique une délégation LÉGITIME, signée avec le secret de l'émetteur."""
    return Delegation(expediteur=expediteur, message=message, signature=signer(expediteur, message))


def verifier(deleg: Delegation) -> bool:
    """Vrai si la provenance est authentique : émetteur connu et signature valide.

    Comparaison à temps constant. Un émetteur inconnu ou une signature absente/fausse est
    rejeté (provenance invalide)."""
    if not deleg.signature or deleg.expediteur not in _SECRETS:
        return False
    attendue = signer(deleg.expediteur, deleg.message)
    return hmac.compare_digest(attendue, deleg.signature)


def inventaire_backend() -> list[dict]:
    """La règle de détection d'usurpation, publiée comme canari (nature agent_usurpation)."""
    return [
        {
            "id": CANARI_USURPATION,
            "source": "interne",
            "surface": "agent",
            "nature": "agent_usurpation",
            "emplacement": "orchestrateur d'agents Orbis Pay, provenance des délégations",
            "description": (
                "Délégation inter-agent sans provenance vérifiée : un message forgé se fait "
                "passer pour un agent de confiance (pas de signature). Bloqué et signalé."
            ),
            # OWASP Agentic ASI07 (confiance inter-agent / provenance) — demandé par le brief.
            "risques": ["OWASP ASI07"],
            # ATLAS : usurpation/injection via un message d'agent (plausible, à confirmer).
            "techniques": ["AML.T0051"],
            "humain_visible": False,
        }
    ]
