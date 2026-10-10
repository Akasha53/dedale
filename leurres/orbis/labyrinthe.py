"""Labyrinthe : des pages et des routes d'API qui s'enchainent sans fin pour un
client automatique, mais bornees cote serveur.

Principe : chaque page est derivee de maniere DETERMINISTE d'un jeton (meme jeton
-> meme page). Le jeton encode une profondeur et un chemin. Une page propose 2 a 3
enfants, donc un crawler suit indefiniment ; mais chaque requete est O(1) chez nous
(un hachage, pas de recursion, pas de stockage qui grossit). La lenteur est simulee
par un sleep borne, deterministe par page. Aucune vraie boucle infinie cote serveur.

But mesure par le backend : combien de temps et de requetes un client passe ici.
"""
from __future__ import annotations

import hashlib
from random import Random

from . import config

# Decor credible : fragments reutilises pour fabriquer des pages plausibles.
_SECTIONS = [
    "Journal d'audit", "File d'export", "Reconciliation", "Lot de virements",
    "Registre KYC", "Archive mandats SEPA", "Rapprochement bancaire",
    "Tableau de bord conformite", "Index transactions", "Pagination des ecritures",
]
_VERBES = ["Consulter", "Poursuivre", "Charger la suite de", "Ouvrir", "Deplier", "Exporter"]


def _hache(*parties: str) -> str:
    brut = (config.GRAINE + "|" + "|".join(parties)).encode()
    return hashlib.sha256(brut).hexdigest()


def jeton_initial() -> str:
    """Jeton d'entree du labyrinthe (profondeur 0)."""
    return "0-" + _hache("entree")[:12]


def _profondeur(jeton: str) -> int:
    try:
        return int(jeton.split("-", 1)[0])
    except (ValueError, IndexError):
        return 0


def _enfant(jeton: str, branche: int) -> str:
    prof = min(_profondeur(jeton) + 1, config.LABY_PROFONDEUR_MAX)
    h = _hache(jeton, str(branche))[:12]
    return f"{prof}-{h}"


def _sleep_de(jeton: str) -> float:
    """Delai deterministe, borne entre LABY_SLEEP_MIN et LABY_SLEEP_MAX."""
    rng = Random(int(_hache(jeton, "sleep")[:8], 16))
    return round(config.LABY_SLEEP_MIN + rng.random() * (config.LABY_SLEEP_MAX - config.LABY_SLEEP_MIN), 3)


def _branches(jeton: str) -> list[int]:
    rng = Random(int(_hache(jeton, "branches")[:8], 16))
    return list(range(rng.randint(2, 3)))


def page_html(jeton: str) -> tuple[str, float]:
    """Rend une page HTML du labyrinthe et le delai a appliquer avant de repondre."""
    rng = Random(int(_hache(jeton, "html")[:8], 16))
    prof = _profondeur(jeton)
    section = rng.choice(_SECTIONS)
    ref = _hache(jeton, "ref")[:8].upper()
    sleep = _sleep_de(jeton)

    liens = []
    for b in _branches(jeton):
        enfant = _enfant(jeton, b)
        verbe = rng.choice(_VERBES)
        liens.append(f'<li><a href="/labyrinthe/{enfant}">{verbe} le lot {ref}-{b:02d}</a></li>')

    lignes = []
    for i in range(rng.randint(4, 7)):
        lignes.append(
            f"<tr><td>ORB-{rng.randint(10000,99999)}</td>"
            f"<td>FICTIF client #{rng.randint(1,9999):04d}</td>"
            f"<td>{rng.choice(['en file','en cours','differe'])}</td>"
            f"<td>page {prof}</td></tr>"
        )

    corps = f"""<main class="laby">
  <p class="fil">Zone interne Orbis Pay &middot; export par lots &middot; reference {ref} &middot; segment {prof}</p>
  <h1>{section}</h1>
  <p>Traitement par lots en cours. Chargez le segment suivant pour obtenir la suite de l'export.
  Donnees synthetiques de demonstration, marquees <strong>FICTIF</strong>.</p>
  <table class="tbl"><thead><tr><th>Ref</th><th>Entite</th><th>Etat</th><th>Segment</th></tr></thead>
  <tbody>{''.join(lignes)}</tbody></table>
  <h2>Segments suivants</h2>
  <ul class="suite">{''.join(liens)}</ul>
</main>"""
    return corps, sleep


def page_json(jeton: str, racine: str = "/api/internal/export-clients") -> tuple[dict, float]:
    """Rend une page JSON paginee du labyrinthe (variante API) et son delai."""
    rng = Random(int(_hache(jeton, "json")[:8], 16))
    prof = _profondeur(jeton)
    sleep = _sleep_de(jeton)
    enfant = _enfant(jeton, 0)
    enregistrements = [
        {
            "id": f"ORB-{rng.randint(10000,99999)}",
            "raison_sociale": f"FICTIF SARL {rng.randint(100,999)}",
            "iban": "FR76FICTIF" + "".join(str(rng.randint(0, 9)) for _ in range(10)),
            "statut": rng.choice(["actif", "suspendu", "en_revue"]),
            "_note": "donnee synthetique, aucune valeur reelle",
        }
        for _ in range(rng.randint(3, 6))
    ]
    corps = {
        "avertissement": "Donnees entierement fictives (FICTIF). Export de demonstration.",
        "segment": prof,
        "enregistrements": enregistrements,
        "curseur_suivant": enfant,
        "suite": f"{racine}?cursor={enfant}",
    }
    return corps, sleep
