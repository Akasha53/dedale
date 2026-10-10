"""Schémas Pydantic des entrées de l'API. Tolérants : on ne casse jamais l'appelant."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvenementIn(BaseModel):
    # extra=ignore : une surface qui envoie un champ en trop ne reçoit jamais d'erreur.
    model_config = ConfigDict(extra="ignore")

    horodatage: datetime | None = None
    source: str = "externe"
    surface: str = "site"
    type: str = "requete"
    session_id: str
    leurre_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    methode: str | None = None
    chemin: str | None = None
    outil: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LeurreIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source: str = "externe"
    surface: str = "site"
    nature: str = "consigne_cachee"
    emplacement: str = ""
    description: str = ""
    risques: list[str] = Field(default_factory=list)
    techniques: list[str] = Field(default_factory=list)
    humain_visible: bool = False


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # « accorder » et « refuser » tranchent un geste critique du salarié (quatre yeux).
    action: Literal["valider_riposte", "couper", "reprendre", "ignorer", "clore", "accorder", "refuser"]
    analyste: str = "inconnu"
    # Motif court de l'analyste : journalisé et scellé avec la décision (événement `console`).
    motif: str = Field(default="", max_length=300)


class RevelationIn(BaseModel):
    """Levée de l'anonymat d'un salarié : motif obligatoire, acte scellé."""

    model_config = ConfigDict(extra="ignore")

    motif: str = Field(default="", max_length=300)
    analyste: str = "inconnu"


class RemediationIn(BaseModel):
    """Action simulée côté salarié : mot de passe, sessions, domaine bloqué pour tous."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["reinitialiser_mot_de_passe", "fermer_sessions", "bloquer_domaine"]
    analyste: str = "inconnu"


class RetraitDroitIn(BaseModel):
    """Correctif en un clic : le droit en trop à retirer à l'agent de l'incident."""

    model_config = ConfigDict(extra="ignore")

    # Un droit vide ou inconnu est refusé par le store (400), pas par la validation (422).
    droit: str = Field(default="", max_length=200)
    analyste: str = "inconnu"
