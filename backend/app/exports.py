"""Export d'un incident vers un SIEM : ECS 8.x (Elastic), règles Sigma, CEF (ArcSight, syslog).

- `vers_ecs` : un document ECS par événement de la session (`ecs.py`).
- `vers_sigma` : les règles Sigma qui attrapent cet incident, au format YAML à plusieurs
  documents (`sigma_regles.py`) : la règle de son type, les règles de geste qui le concernent,
  et les variantes proxy ou serveur web : la générique, et celle spécialisée sur ce qu'il a vu.
- `vers_cef` : une ligne CEF par événement (`cef.py`), prête pour un collecteur syslog.

Tout texte d'origine piégée est déjà neutralisé en amont (store/securite) ; un salarié n'y
apparaît que sous son pseudonyme.
"""

from __future__ import annotations

from . import cef, ecs, sigma_regles


def _evenements(incident: dict, evenements: list[dict] | None) -> list[dict]:
    if evenements is not None:
        return evenements
    from .store import store  # import local : le store importe ce module indirectement
    return (store.session_detail(incident.get("session_id") or "") or {}).get("evenements", [])


def vers_ecs(incident: dict, evenements: list[dict]) -> dict:
    return ecs.vers_ecs(incident, evenements)


def vers_sigma(incident: dict, evenements: list[dict] | None = None) -> str:
    """Règles Sigma de l'incident, séparées par `---` (sigma-cli lit ce fichier tel quel)."""
    docs = ecs.vers_ecs(incident, _evenements(incident, evenements))["documents"]
    return sigma_regles.vers_yaml(sigma_regles.regles_incident(incident.get("type") or "", docs))


def vers_cef(incident: dict, evenements: list[dict] | None = None) -> str:
    from .notifications import lien_incident
    return cef.vers_cef(incident, _evenements(incident, evenements), lien_incident(str(incident.get("id"))))
