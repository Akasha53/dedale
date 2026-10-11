"""Un refus que les règles prononcent d'office part tout de suite (répétition générale, point 2).

Le salarié attendait 7 s sa pop-up pendant que Haiku relisait un virement déjà refusé par les
règles. Le modèle ne tourne plus qu'après, en tâche de fond, pour l'explication de la console.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app import relecteur
from tests.conftest import evenement, jeton
from tests.test_relecteur import FauxModele, _calme, _relecteur_actif  # noqa: F401

EXPLICATION = {"decision": "refuse", "motif_salarie": "Virement bloqué par précaution.",
               "motif_soc": "Bénéficiaire inconnu, montant au-dessus du plafond, juste après un phishing.",
               "confiance": 0.93}


def test_refus_sur_des_regles_sans_attendre_le_modele(client, monkeypatch):
    monkeypatch.setenv("DEDALE_RELECTEUR_DELAI", "10")
    faux = FauxModele(geste=EXPLICATION, attente=1.5)
    relecteur.definir_modele(faux, mode="cli")
    client.post("/api/evenements", json=evenement(
        source="humain", surface="poste", type="avertissement", session_id="poste-repet-c",
        horodatage=datetime.now(timezone.utc).isoformat(),
        details={"categorie": "phishing", "choix": "continuer", "message": "Lien suspect."}))
    debut = time.monotonic()
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": "r1", "session_id": "poste-repet-c", "geste": "virement", "categorie": "mail_externe",
        "message": "Virement urgent de 48 500 € à Compta Express, IBAN FR76 1111 2222 3333 4444 5555 0042."})
    duree = time.monotonic() - debut
    v = r.json()
    assert v["issue"] == "refuse" and v["fraude"] is True and v["tranche_par"] == "règles"
    assert duree < 1.0, f"le salarié a attendu {duree:.1f} s"
    # Le modèle tourne ensuite, et son explication arrive dans la console sans changer la décision.
    assert _calme()
    assert len([a for a in faux.appels if "priorite" not in a["schema"]["properties"]]) == 1
    rel = client.get(f"/api/incidents/{v['incident_id']}").json()["relecteur"]
    assert rel["decision"] == "refuse" and rel["tranche_par"] == "règles"
    assert rel["explication_modele"]["motif_soc"].startswith("Bénéficiaire inconnu")
    mesures = client.get("/api/mesures").json()["relecteur"]
    # L'explication n'est pas une décision de plus.
    assert mesures["par_acte"]["quatre_yeux"] == 1 and mesures["decisions"] == sum(mesures["par_acte"].values())
