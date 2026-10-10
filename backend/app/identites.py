"""Salariés pseudonymisés par défaut, identité levée sur motif.

La console du SOC ne montre jamais le nom d'un salarié. Chaque poste reçoit un pseudonyme
stable (« Salarié 4821 ») et, quand l'annuaire le connaît, son service (« Finance »).
Tout ce que l'API renvoie pour un geste humain passe par `masquer` : le prénom, le nom et
l'adresse du salarié deviennent son pseudonyme, l'identifiant de session qui porterait son
prénom aussi, et les paramètres d'URL disparaissent (un `?u=camille` dit qui a cliqué).

Lever l'anonymat est un acte de l'analyste : il donne un motif, l'acte entre dans le journal
scellé (événement `console`, acte `reveler_identite`), et seul ce retour porte le nom. Le
journal garde le motif et l'auteur, jamais le nom révélé.

L'annuaire ci-dessous est fictif, comme Orbis Pay.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Annuaire fictif d'Orbis Pay. `sessions` : préfixes des sessions de son poste (garde du
# poste, app Mac de démo). `adresses` : boîtes mail qui le désignent dans un mail reçu.
ANNUAIRE: list[dict] = [
    {
        "cle": "camille",
        "nom": "Camille Martin",
        "service": "Finance",
        "poste": "PC-FIN-0412",
        "adresses": ["camille.martin@orbispay.example"],
        "sessions": ["poste-camille", "poste-mac"],
        "noms": ["Camille Martin", "Camille", "Martin"],
    },
    {
        "cle": "jeanne",
        "nom": "Jeanne Roussel",
        "service": "Ressources humaines",
        "poste": "PC-RH-0207",
        "adresses": ["jeanne.roussel@orbispay.example"],
        "sessions": ["poste-jeanne"],
        "noms": ["Jeanne Roussel", "Jeanne", "Roussel"],
    },
]

PAR_CLE = {p["cle"]: p for p in ANNUAIRE}

# Champs techniques jamais réécrits : clés de jointure et empreintes du journal scellé.
_CLES_INTACTES = {
    "id", "session_id", "incident_id", "evenement_id", "sceau", "sceau_precedent",
    "precedent", "evenement", "empreinte", "empreinte_parametres", "rang",
}

_PARAMS_MASQUES = re.compile(r"\?\[paramètres masqués\]")
_URL_AVEC_REQUETE = re.compile(r"((?:hxxps?|https?)://[^\s?#\"'<>]+)\?[^\s\"'<>)\]]*", re.IGNORECASE)


def _numero(graine: str) -> int:
    return int(hashlib.sha256(f"dedale:salarie:{graine}".encode("utf-8")).hexdigest()[:8], 16) % 9000 + 1000


def _normaliser(texte: str) -> str:
    return texte.replace("[.]", ".").lower()


def _adresses_vues(valeur: Any, sortie: set[str]) -> None:
    if isinstance(valeur, str):
        for m in re.finditer(r"[\w.+-]+@[\w-]+(?:(?:\.|\[\.\])[\w-]+)+", valeur):
            sortie.add(_normaliser(m.group(0)))
    elif isinstance(valeur, dict):
        for v in valeur.values():
            _adresses_vues(v, sortie)
    elif isinstance(valeur, list):
        for v in valeur:
            _adresses_vues(v, sortie)


def personne(session_id: str, evenements: list[dict] | None = None) -> dict | None:
    """Entrée d'annuaire du salarié de cette session, ou None si on ne sait pas qui."""
    sid = (session_id or "").lower()
    for p in ANNUAIRE:
        if any(sid.startswith(prefixe) for prefixe in p["sessions"]):
            return p
    vues: set[str] = set()
    for ev in evenements or []:
        _adresses_vues(ev.get("details") or {}, vues)
    for p in ANNUAIRE:
        if any(a in vues for a in p["adresses"]):
            return p
    # En dernier recours, le prénom cité par le poste (« Camille ouvre un mail… », `?u=camille`).
    textes: list[str] = []
    for ev in evenements or []:
        _textes(ev.get("details") or {}, textes)
    tout = " ".join(textes)
    for p in ANNUAIRE:
        prenom = p["noms"][1] if len(p["noms"]) > 1 else p["noms"][0]
        if re.search(r"(?<![\w])" + re.escape(prenom) + r"(?![\w])", tout, re.IGNORECASE):
            return p
    return None


def _textes(valeur: Any, sortie: list[str]) -> None:
    if isinstance(valeur, str):
        sortie.append(valeur)
    elif isinstance(valeur, dict):
        for v in valeur.values():
            _textes(v, sortie)
    elif isinstance(valeur, list):
        for v in valeur:
            _textes(v, sortie)


def identite(session_id: str, evenements: list[dict] | None = None) -> dict:
    """Ce que la console peut afficher : pseudonyme stable et service, jamais le nom."""
    p = personne(session_id, evenements)
    numero = _numero(p["cle"] if p else session_id)
    pseudo = f"Salarié {numero}"
    service = p["service"] if p else None
    return {
        "pseudonyme": pseudo,
        "service": service,
        "libelle": f"{pseudo} · {service}" if service else pseudo,
        "connu": p is not None,
    }


def _jetons(p: dict | None) -> list[str]:
    if p is None:
        return []
    jetons = list(p["adresses"]) + [a.replace(".", "[.]") for a in p["adresses"]]
    jetons += [a.split("@")[0] for a in p["adresses"]]
    jetons += list(p["noms"])
    return sorted(set(jetons), key=len, reverse=True)


def _masquer_texte(texte: str, motifs: list[re.Pattern], pseudo: str) -> str:
    t = _PARAMS_MASQUES.sub("", texte)
    t = _URL_AVEC_REQUETE.sub(r"\1", t)
    for motif in motifs:
        t = motif.sub(pseudo, t)
    return t


def masqueur(session_id: str, evenements: list[dict] | None = None):
    """Fonction qui pseudonymise une valeur JSON (dict, liste, texte) de cette session."""
    p = personne(session_id, evenements)
    pseudo = identite(session_id, evenements)["pseudonyme"]
    motifs = []
    if session_id:
        motifs.append(re.compile(re.escape(session_id), re.IGNORECASE))
    for j in _jetons(p):
        motifs.append(re.compile(r"(?<![\w.])" + re.escape(j) + r"(?![\w])", re.IGNORECASE))

    def masquer(valeur: Any, cle: str | None = None) -> Any:
        if cle in _CLES_INTACTES:
            return valeur
        if isinstance(valeur, str):
            return _masquer_texte(valeur, motifs, pseudo)
        if isinstance(valeur, dict):
            return {k: masquer(v, k) for k, v in valeur.items()}
        if isinstance(valeur, list):
            return [masquer(v) for v in valeur]
        return valeur

    return masquer
