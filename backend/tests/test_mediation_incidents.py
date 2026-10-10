"""Médiation universelle de la passerelle interne : chaque règle nomme son incident.

Les règles C-8A61 (outil inconnu), C-5B27 (canal de sortie détourné) et C-3F90 (outil MCP
modifié) sont publiées comme des canaris. Premier canari touché de la session, elles donnent
`interne_outil_inconnu`, `interne_canal_detourne` ou `interne_outil_modifie`, et la session
est suspendue en attendant l'analyste.
"""

from __future__ import annotations

import pytest

from tests.conftest import BASE, evenement, horo

REGLES = [
    ("C-8A61", "outil_inconnu", "envoyer_mail", "interne_outil_inconnu"),
    ("C-5B27", "canal_detourne", "chercher_document", "interne_canal_detourne"),
    ("C-3F90", "outil_modifie", "convertir_montant", "interne_outil_modifie"),
]


@pytest.mark.parametrize("regle,nature,outil,type_attendu", REGLES)
def test_regle_de_mediation_nomme_l_incident(client, regle, nature, outil, type_attendu):
    client.post("/api/leurres", json=[
        {"id": regle, "source": "interne", "surface": "outil", "nature": nature,
         "emplacement": "passerelle de l'agent interne", "description": "Règle, pas un piège."},
        {"id": "C-2B91", "source": "interne", "surface": "document", "nature": "faux_secret",
         "emplacement": "coffre", "description": "Fausse clé d'API."},
    ])
    sid = f"S-{nature}"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil=outil,
        details={"verdict": "retenu", "retenu": True, "motif": nature, "parametres": {},
                 nature: {"outil": outil, "canaris": ["C-2B91"]}},
        horodatage=horo(BASE, 0)))
    for i, leurre in enumerate((regle, "C-2B91"), start=1):
        client.post("/api/evenements", json=evenement(
            session_id=sid, source="interne", surface="outil", type="leurre_touche",
            leurre_id=leurre, outil=outil, details={"type": nature, "detail": "retenu"},
            horodatage=horo(BASE, i * 0.1)))

    incidents = client.get("/api/incidents").json()["incidents"]
    inc = next(i for i in incidents if i["session_id"] == sid)
    assert inc["type"] == type_attendu
    assert client.get(f"/api/sessions/{sid}").json()["etat"] == "suspendue"
