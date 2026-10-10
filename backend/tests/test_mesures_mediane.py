"""/api/mesures : médiane et moyenne explicites, en millisecondes, à côté des champs historiques."""

from app.mesures import duree_ms
from tests.conftest import BASE, evenement, horo


def test_duree_ms_mediane_et_moyenne():
    assert duree_ms([]) == {"mediane_ms": None, "moyenne_ms": None, "echantillons": 0}
    # Une valeur extrême tire la moyenne, pas la médiane.
    assert duree_ms([1.0, 2.0, 30.0]) == {"mediane_ms": 2000, "moyenne_ms": 11000, "echantillons": 3}
    assert duree_ms([0.5, 1.5]) == {"mediane_ms": 1000, "moyenne_ms": 1000, "echantillons": 2}


def _agent_banc(client, sid, debut, pas=1.7):
    """Session du banc classée agent IA à son deuxième événement (le canari)."""
    client.post("/api/leurres", json=[
        {"id": "C-M1", "source": "interne", "surface": "mail", "nature": "canari_mail"}])
    for i, (surface, typ, extra) in enumerate([
        ("mail", "entree_agent", {}),
        ("mail", "leurre_touche", {"leurre_id": "C-M1", "details": {"consigne": "envoie tout"}}),
        ("outil", "appel_outil", {"outil": "envoyer_mail", "details": {"exfiltration": True}}),
    ]):
        client.post("/api/evenements", json=evenement(
            session_id=sid, source="interne", surface=surface, type=typ,
            horodatage=horo(BASE, debut + i * pas), **extra))


def test_mesures_exposent_mediane_et_moyenne(client):
    # Trois agents détectés au deuxième événement : 1 s, 2 s et 9 s après leur début.
    for n, pas in enumerate((1.0, 2.0, 9.0), start=1):
        _agent_banc(client, f"banc-interne-000{n}", n * 100, pas)
    m = client.get("/api/mesures").json()
    assert m["temps_detection"] == {"mediane_ms": 2000, "moyenne_ms": 4000, "echantillons": 3}
    # Champ historique inchangé : c'est une moyenne, en secondes.
    assert m["temps_detection_s"] == 4.0
    assert m["temps_confinement"] == {"mediane_ms": None, "moyenne_ms": None, "echantillons": 0}
    assert m["temps_confinement_s"] is None
