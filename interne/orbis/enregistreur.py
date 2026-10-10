"""Enregistreur de la boîte noire détaillée : maillons datés, chrono et masquage.

La passerelle en mode protégé (scénario jury) note chaque maillon de la chaîne :

    source -> consigne -> intention -> appel_outil -> decision -> resultat

Chaque maillon porte une date ISO à la milliseconde, un décalage en ms depuis le début de
la session, un détail inerte et, le cas échéant, ses références (OWASP agentique, MITRE ATLAS,
MITRE ATT&CK). Aucun maillon ne recopie une consigne piégée ni la valeur d'une clé : seuls
une empreinte, une longueur et l'identifiant du canari sont gardés.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

# Référentiels. Libellés OWASP : Top 10 for Agentic Applications (2026). ATLAS et ATT&CK :
# identifiants publics, libellés à revérifier sur atlas.mitre.org et attack.mitre.org avant
# la fiche défense.
REFERENTIEL: dict[str, dict] = {
    "OWASP ASI01": {"cadre": "OWASP agentique", "nom": "Agent Goal Hijack (détournement d'objectif)"},
    "OWASP ASI02": {"cadre": "OWASP agentique", "nom": "Tool Misuse and Exploitation (usage détourné d'outil)"},
    "OWASP ASI03": {"cadre": "OWASP agentique", "nom": "Identity and Privilege Abuse (abus de droits)"},
    "OWASP ASI04": {"cadre": "OWASP agentique", "nom": "Agentic Supply Chain Vulnerabilities (outils et serveurs MCP non maîtrisés)"},
    "AML.T0051": {"cadre": "MITRE ATLAS", "nom": "LLM Prompt Injection (indirecte, par un document lu)"},
    "AML.T0053": {"cadre": "MITRE ATLAS", "nom": "AI Agent Tool Invocation (ex-LLM Plugin Compromise)"},
    "AML.T0057": {"cadre": "MITRE ATLAS", "nom": "LLM Data Leakage"},
    "T1555": {"cadre": "MITRE ATT&CK", "nom": "Credentials from Password Stores"},
}

MAILLONS = ("source", "consigne", "intention", "appel_outil", "decision", "resultat")


def references(*codes: str) -> list[dict]:
    """[{cadre, id, nom}] pour une liste de codes ; un code inconnu garde son identifiant."""
    sortie = []
    for code in codes:
        ref = REFERENTIEL.get(code, {"cadre": "autre", "nom": code})
        sortie.append({"cadre": ref["cadre"], "id": code, "nom": ref["nom"]})
    return sortie


def empreinte(texte: str) -> str:
    """Empreinte courte d'un contenu : permet de rapprocher une preuve sans l'exposer."""
    return "sha256:" + hashlib.sha256((texte or "").encode("utf-8")).hexdigest()[:16]


_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏  ﻿]")
_URL_REQUETE = re.compile(r"(https?://[^\s?#)\"'<>]+)\?[^\s)\"'<>]*")


def masquer(valeur, jetons: dict[str, str] | None = None):
    """Copie de `valeur` où chaque faux secret canari devient « [canari C-xxxx masqué] » et
    où la partie requête d'une URL est retirée (elle porte en général la donnée volée).
    Parcourt dicts et listes. Sert à tout ce qui sort de la passerelle vers le backend."""
    jetons = jetons or {}
    if isinstance(valeur, dict):
        return {k: masquer(v, jetons) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [masquer(v, jetons) for v in valeur]
    if isinstance(valeur, str):
        texte = _URL_REQUETE.sub(r"\1?[paramètres masqués]", valeur)
        for cid, jeton in jetons.items():
            if jeton and jeton in texte:
                texte = texte.replace(jeton, f"[canari {cid} masqué]")
        return texte
    return valeur


def inerte(texte: str, limite: int = 200) -> str:
    """Texte aplati, sans caractères de contrôle, tronqué. Jamais réinjecté comme consigne."""
    texte = unicodedata.normalize("NFKC", texte or "")
    texte = _CTRL.sub(" ", texte)
    texte = " ".join(texte.split())
    if len(texte) > limite:
        texte = texte[:limite].rstrip() + " […]"
    return texte


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Instant:
    iso: str
    mono: float  # time.monotonic(), pour les durées


def ecart_ms(debut: "Instant | None", fin: "Instant | None") -> float | None:
    if debut is None or fin is None:
        return None
    return round((fin.mono - debut.mono) * 1000.0, 2)


class Enregistreur:
    """Boîte noire locale de la passerelle protégée. Une instance par session."""

    def __init__(self) -> None:
        self.debut = self.instant()
        self.maillons: list[dict] = []
        self.chronos: list[dict] = []  # un chrono par appel retenu

    @staticmethod
    def instant() -> Instant:
        return Instant(iso=maintenant_iso(), mono=time.monotonic())

    def noter(
        self,
        maillon: str,
        titre: str,
        detail: str,
        *,
        moment: Instant | None = None,
        outil: str | None = None,
        canari_id: str | None = None,
        preuve: dict | None = None,
        refs: list[dict] | None = None,
    ) -> dict:
        moment = moment or self.instant()
        entree = {
            "ordre": len(self.maillons) + 1,
            "maillon": maillon,
            "horodatage": moment.iso,
            "t_ms": ecart_ms(self.debut, moment),
            "titre": titre,
            "detail": inerte(detail, 240),
            "outil": outil,
            "canari_id": canari_id,
            "preuve": preuve or {},
            "references": refs or [],
        }
        self.maillons.append(entree)
        return entree

    def references_cumulees(self) -> list[dict]:
        """Toutes les références posées sur la chaîne, sans doublon, dans l'ordre d'apparition."""
        vus: set[str] = set()
        sortie = []
        for m in self.maillons:
            for ref in m["references"]:
                if ref["id"] not in vus:
                    vus.add(ref["id"])
                    sortie.append(ref)
        return sortie

    def maillons_presents(self) -> list[str]:
        return [m["maillon"] for m in self.maillons]


def chrono_dict(points: dict[str, Instant | None]) -> dict:
    """Chrono exposé dans un événement : dates ISO et durées en ms entre étapes connues."""
    d: dict = {f"{k}_a": (v.iso if v else None) for k, v in points.items()}
    demande, detection = points.get("demande"), points.get("detection")
    envoi, accuse = points.get("envoi_console"), points.get("accuse_console")
    decision, resultat = points.get("decision"), points.get("resultat")
    d["detection_ms"] = ecart_ms(demande, detection)
    d["envoi_console_ms"] = ecart_ms(detection, envoi)
    d["accuse_console_ms"] = ecart_ms(envoi, accuse)
    d["attente_decision_ms"] = ecart_ms(accuse or envoi, decision)
    d["application_ms"] = ecart_ms(decision, resultat)
    d["total_ms"] = ecart_ms(demande, resultat or decision or accuse or envoi)
    return {k: v for k, v in d.items() if v is not None}
