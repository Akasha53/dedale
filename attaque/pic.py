"""Démonstration d'un pic d'appels : pose une habitude pour un agent, puis un pic.

Le script envoie au backend, pour un agent fictif d'Orbis Pay, quelques minutes d'activité
régulière (son habitude), puis une rafale d'appels dans la même minute. Le backend apprend
l'habitude (`backend/app/anomalies.py`) et ouvre une alerte « comportement inhabituel » quand
la rafale sort de l'ordinaire. Les horodatages sont posés par le script : une heure
d'activité passée tient en quelques secondes.

Trafic synthétique, étiqueté comme tel. Sessions préfixées `demo-pic-…` : hors des mesures.

    uv run python pic.py                       # backend sur 8700, agent de rapprochement
    uv run python pic.py --base http://127.0.0.1:8750 --agent orbis-assistant
    uv run python pic.py --volume              # au lieu du pic : un volume lu multiplié par dix
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def _poster(base: str, chemin: str, corps, timeout: float = 3.0):
    donnees = json.dumps(corps).encode("utf-8")
    from banc.backend import entete_jeton

    req = urllib.request.Request(base.rstrip("/") + chemin, data=donnees, method="POST",
                                 headers={"Content-Type": "application/json",
                                          **entete_jeton("passerelle")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            return json.loads(rep.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"backend muet ({exc}) — démarre-le d'abord : uv run uvicorn app.main:app --port 8700",
              file=sys.stderr)
        raise SystemExit(2)


def _lire(base: str, chemin: str, timeout: float = 3.0):
    from banc.backend import entete_jeton

    req = urllib.request.Request(base.rstrip("/") + chemin, headers=entete_jeton("analyste"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            return json.loads(rep.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _appel(base, sid, agent, t, outil, **params):
    corps = {"horodatage": t.isoformat(timespec="milliseconds"), "source": "interne",
             "surface": "outil", "type": "appel_outil", "session_id": sid, "outil": outil,
             "ip": "127.0.0.1", "user_agent": "banc-pic/0.1",
             "details": {"agent": agent, "parametres": params, "verdict": "autorise",
                         "verite_terrain": None}}
    return _poster(base, "/api/evenements", corps)


def lancer(base: str, agent: str, mode: str) -> int:
    debut = datetime.now(timezone.utc) - timedelta(minutes=30)
    pose = f"demo-pic-{agent}"
    # Habitude : trois appels par minute pendant douze minutes (relevé, résumé, rapport).
    for m in range(12):
        t = debut + timedelta(minutes=m)
        sid = f"{pose}-hab-{m // 4}"
        _appel(base, sid, agent, t + timedelta(seconds=1), "lire_releve", lignes=40)
        _appel(base, sid, agent, t + timedelta(seconds=20), "resumer")
        _appel(base, sid, agent, t + timedelta(seconds=40), "envoyer_rapport",
               destinataire="compta@orbispay.example")
    print(f"Habitude posée pour {agent} : 3 appels/minute sur 12 minutes.")

    pointe = debut + timedelta(minutes=20)
    sid = f"{pose}-pointe"
    if mode == "volume":
        _appel(base, sid, agent, pointe, "lire_releve", lignes=600)
        print("Un relevé de 600 lignes lu en un appel (habitude : 40).")
    else:
        for i in range(25):
            _appel(base, sid, agent, pointe + timedelta(seconds=i), "lire_releve", lignes=40)
        print("Rafale de 25 appels dans la même minute.")

    incidents = (_lire(base, "/api/incidents") or {}).get("incidents", [])
    anomalie = next((i for i in incidents if i.get("type") == "interne_anomalie"
                     and i.get("session_id") == sid), None)
    if anomalie is None:
        print("Aucune alerte d'anomalie ouverte — vérifier le backend.", file=sys.stderr)
        return 1
    maillon = next((e for e in anomalie.get("chaine", []) if e.get("etape") == "anomalie"), {})
    print(f"\nAlerte ouverte : {anomalie['id']} ({anomalie['gravite']}) — {anomalie['titre']}")
    print(f"  {maillon.get('detail', '')}")
    fiche = _lire(base, f"/api/agents/{agent}")
    if isinstance(fiche, dict):
        h = fiche.get("habitude", {})
        print(f"  Habitude connue : {h.get('appels_par_minute')} appels/minute, "
              f"outils {', '.join(h.get('outils', []))}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Démo d'un comportement anormal (pic d'appels ou volume).")
    p.add_argument("--base", default="http://127.0.0.1:8700", help="URL du backend")
    p.add_argument("--agent", default="orbis-rapprochement", help="agent fictif visé")
    p.add_argument("--volume", action="store_const", const="volume", dest="mode",
                   help="volume lu x10 au lieu d'un pic d'appels")
    p.set_defaults(mode="pic")
    args = p.parse_args(argv)
    return lancer(args.base, args.agent, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
