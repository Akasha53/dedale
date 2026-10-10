"""Runner du banc d'attaque et de mesure de Dédale.

Lance N sessions de chaque type de trafic (humain, script, agent IA, agent
interne détourné) contre la surface fictive locale, à graine fixe, et écrit un
résumé lisible. Les métriques finales sont calculées par le backend
(GET /api/mesures) à partir de la vérité terrain étiquetée par le banc ; le banc
génère le trafic et vérifie la cohérence.

Exemples :
    uv run python campagne.py                 # autodétecte le mode, simulateur
    uv run python campagne.py --n 10          # 10 sessions par type
    uv run python campagne.py --mode autonome --client-ia auto
    uv run python campagne.py --realiste      # délais en vraies secondes
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

from banc import evenement as ev
from banc import rapport
from banc.backend import Backend
from banc.client_ia import ClientIA
from banc.monde import Monde
from banc.surface import LEURRES_SEMES, SurfaceHTTP, SurfaceLocale
from banc.trafic import GENERATEURS

GRAINE_DEFAUT = 1337
N_DEFAUT = 5


def _surface_en_ligne(base: str) -> bool:
    try:
        req = urllib.request.Request(base.rstrip("/") + "/", method="GET")
        with urllib.request.urlopen(req, timeout=1.0):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _choisir_mode(mode: str, base_leurres: str) -> str:
    if mode != "auto":
        return mode
    return "surface" if _surface_en_ligne(base_leurres) else "autonome"


def lancer(n: int = N_DEFAUT, graine: int = GRAINE_DEFAUT, mode: str = "auto",
           client_ia: str = "simulateur", realiste: bool = False,
           base_leurres: str = "http://127.0.0.1:8701",
           base_interne: str = "http://127.0.0.1:8702",
           base_backend: str = "http://127.0.0.1:8700") -> dict:
    """Exécute la campagne et renvoie {manifeste, stats, mesures, mode, ...}."""
    mode = _choisir_mode(mode, base_leurres)
    backend = Backend(base_backend)
    if mode == "surface":
        surface: SurfaceLocale | SurfaceHTTP = SurfaceHTTP(base_leurres, base_interne)
    else:
        surface = SurfaceLocale()
        backend.enregistrer_leurres(LEURRES_SEMES)  # la surface déclare ses leurres

    monde = Monde(mode, surface, backend)
    client = ClientIA(client_ia, random.Random(graine))

    # Ordre déterministe ; un RNG indépendant par session pour la reproductibilité.
    for verite in ev.VERITES:
        generateur = GENERATEURS[verite]
        for numero in range(1, n + 1):
            rng = random.Random(f"{graine}:{verite}:{numero}")
            if verite in (ev.AGENT_IA, ev.AGENT_INTERNE):
                generateur(monde, numero, rng, client=client, realiste=realiste)
            else:
                generateur(monde, numero, rng, realiste=realiste)

    stats = rapport.coherence(monde.manifeste)
    mesures = backend.mesures()
    sessions = backend.sessions()
    return {
        "mode": mode,
        "client_ia": client.backend_effectif,
        "graine": graine,
        "n_par_type": n,
        "manifeste": monde.manifeste,
        "stats": stats,
        "mesures": mesures,
        "sessions": sessions,
        "backend_ok": backend.disponible is True,
        "ecarts_classement": rapport.comparer_classements(sessions),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Banc d'attaque et de mesure de Dédale.")
    p.add_argument("--n", type=int, default=N_DEFAUT,
                   help=f"sessions par type (défaut {N_DEFAUT})")
    p.add_argument("--graine", type=int, default=GRAINE_DEFAUT,
                   help=f"graine aléatoire (défaut {GRAINE_DEFAUT})")
    p.add_argument("--mode", choices=["auto", "autonome", "surface"], default="auto",
                   help="auto : surface si leurres/ répond, sinon autonome")
    p.add_argument("--client-ia", choices=["simulateur", "auto", "api", "claude-p"],
                   default="simulateur",
                   help="défaut simulateur (reproductible) ; auto = API→claude -p→simulateur")
    p.add_argument("--realiste", action="store_true",
                   help="attendre en vraies secondes (cadence réelle, plus lent)")
    p.add_argument("--base-leurres", default="http://127.0.0.1:8701")
    p.add_argument("--base-interne", default="http://127.0.0.1:8702")
    p.add_argument("--backend", default="http://127.0.0.1:8700")
    p.add_argument("--sortie", default="sorties",
                   help="dossier où écrire le manifeste et le résumé JSON")
    args = p.parse_args(argv)

    res = lancer(n=args.n, graine=args.graine, mode=args.mode,
                 client_ia=args.client_ia, realiste=args.realiste,
                 base_leurres=args.base_leurres, base_interne=args.base_interne,
                 base_backend=args.backend)

    texte = rapport.resume_texte(
        res["stats"], mode=res["mode"], client_ia=res["client_ia"],
        graine=res["graine"], n_par_type=res["n_par_type"],
        mesures=res["mesures"], backend_ok=res["backend_ok"])
    print(texte)
    if res["ecarts_classement"]:
        print("\nÉcarts de classement (backend GET /api/sessions) :")
        for e in res["ecarts_classement"]:
            print(f"  - {e}")

    dossier = Path(args.sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"campagne-{args.graine}.json").write_text(
        json.dumps({k: v for k, v in res.items() if k != "manifeste"} |
                   {"manifeste": res["manifeste"]},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (dossier / f"campagne-{args.graine}.txt").write_text(texte + "\n", encoding="utf-8")

    return 1 if res["stats"]["anomalies"] else 0


if __name__ == "__main__":
    sys.exit(main())
