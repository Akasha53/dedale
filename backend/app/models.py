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

    action: Literal["valider_riposte", "couper", "reprendre", "ignorer", "clore"]
    analyste: str = "inconnu"
