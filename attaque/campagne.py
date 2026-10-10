"""Runner du banc d'attaque et de mesure de Dédale.

Lance N sessions de chaque type de trafic (humain, script, agent IA, agent
interne détourné) contre la surface fictive locale, à graine fixe, et écrit un
résumé lisible. Les métriques finales sont calculées par le backend
(GET /api/mesures) à partir de la vérité terrain étiquetée par le banc ; le banc
génère le trafic et vérifie la cohérence.

Chaque exécution reçoit un identifiant de campagne (``--campagne`` pour le fixer),
porté par tous ses session_id : ``banc-<type>-<campagne>-NNNN``. Le bilan (détection,
faux positifs, faux négatifs, sessions non classées, temps) ne porte que sur les
sessions de la campagne courante ; GET /api/mesures est rapporté à part, comme valeur
globale du backend. La graine fixe rend le trafic identique d'une campagne à l'autre.

Sorties : ``rapports/campagne-<id>.md`` et ``.json`` (bilan), ``sorties/campagne-<id>.*``
(manifeste complet, ignoré par git).

Exemples :
    uv run python campagne.py                 # autodétecte le mode, simulateur
    uv run python campagne.py --mode autonome --backend http://127.0.0.1:8790
    uv run python campagne.py --n 10          # 10 sessions par type
    uv run python campagne.py --mode autonome --client-ia auto
    uv run python campagne.py --realiste      # délais en vraies secondes
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
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


def _commit() -> str | None:
    try:
        sortie = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                cwd=Path(__file__).parent, capture_output=True,
                                text=True, timeout=5)
        return sortie.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def lancer(n: int = N_DEFAUT, graine: int = GRAINE_DEFAUT, mode: str = "auto",
           client_ia: str = "simulateur", realiste: bool = False,
           base_leurres: str = "http://127.0.0.1:8701",
           base_interne: str = "http://127.0.0.1:8702",
           base_backend: str = "http://127.0.0.1:8700",
           campagne: str | None = None,
           types: tuple[str, ...] = ev.VERITES) -> dict:
    """Exécute la campagne et renvoie {campagne, manifeste, stats, bilan, mesures, ...}."""
    campagne = ev.valider_campagne(campagne) if campagne else ev.nouvelle_campagne()
    inconnus = [t for t in types if t not in ev.VERITES]
    if inconnus or not types:
        raise ValueError(f"types de trafic invalides : {inconnus or types!r}")
    debut = datetime.now().astimezone()
    t0 = time.perf_counter()
    mode = _choisir_mode(mode, base_leurres)
    backend = Backend(base_backend)
    if mode == "surface":
        surface: SurfaceLocale | SurfaceHTTP = SurfaceHTTP(base_leurres, base_interne)
    else:
        surface = SurfaceLocale()
        backend.enregistrer_leurres(LEURRES_SEMES)  # la surface déclare ses leurres

    monde = Monde(mode, surface, backend, campagne=campagne)
    client = ClientIA(client_ia, random.Random(graine))

    # Ordre déterministe ; un RNG indépendant par session pour la reproductibilité.
    # La graine ne dépend pas de la campagne : même trafic, identifiants neufs.
    for verite in (v for v in ev.VERITES if v in types):
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
    incidents = backend.incidents() if sessions is not None else None
    details = ({sid: backend.session(sid) for sid in monde.manifeste}
               if sessions is not None else {})
    a_nous = [s for s in (sessions or []) if s.get("id") in monde.manifeste]
    bilan = rapport.bilan_campagne(
        campagne=campagne, mode=mode, manifeste=monde.manifeste,
        reponses=monde.reponses, sessions=sessions, details=details,
        incidents=incidents)
    if monde.resultats_internes:
        r = list(monde.resultats_internes.values())
        bilan["passerelle_interne"] = {
            "sessions": len(r),
            "sessions_avec_rapport_envoye": sum(1 for x in r if x["rapports_envoyes"]),
            "rapports_envoyes": sum(x["rapports_envoyes"] for x in r),
            "etats_finaux": {e: sum(1 for x in r if x["etat_passerelle"] == e)
                             for e in sorted({str(x["etat_passerelle"]) for x in r})},
        }
    return {
        "campagne": campagne,
        "debut": debut.isoformat(timespec="seconds"),
        "duree_s": round(time.perf_counter() - t0, 1),
        "commit": _commit(),
        "base_backend": base_backend,
        "mode": mode,
        "realiste": realiste,
        "client_ia": client.backend_effectif,
        "graine": graine,
        "n_par_type": n,
        "types": [v for v in ev.VERITES if v in types],
        "manifeste": monde.manifeste,
        "stats": stats,
        "bilan": bilan,
        "mesures": mesures,
        "sessions": a_nous,
        "backend_ok": backend.disponible is True,
        "ecarts_classement": rapport.comparer_classements(a_nous),
    }


def ecrire_sorties(res: dict, texte: str, sortie: str | Path,
                   rapports: str | Path) -> dict[str, Path]:
    """Écrit le rapport (md + json, sans manifeste) et le manifeste complet."""
    nom = f"campagne-{res['campagne']}"
    dossier_r = Path(rapports)
    dossier_r.mkdir(parents=True, exist_ok=True)
    dossier_s = Path(sortie)
    dossier_s.mkdir(parents=True, exist_ok=True)
    chemins = {
        "rapport_md": dossier_r / f"{nom}.md",
        "rapport_json": dossier_r / f"{nom}.json",
        "manifeste_json": dossier_s / f"{nom}.json",
        "resume_txt": dossier_s / f"{nom}.txt",
    }
    sans_manifeste = {k: v for k, v in res.items() if k not in ("manifeste", "sessions")}
    chemins["rapport_md"].write_text(rapport.rapport_markdown(res), encoding="utf-8")
    chemins["rapport_json"].write_text(
        json.dumps(sans_manifeste, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    chemins["manifeste_json"].write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    chemins["resume_txt"].write_text(texte + "\n", encoding="utf-8")
    return chemins


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Banc d'attaque et de mesure de sAIfe.")
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
    p.add_argument("--types", default=",".join(ev.VERITES),
                   help="types de trafic joués, séparés par des virgules "
                        f"(défaut : {','.join(ev.VERITES)})")
    p.add_argument("--campagne", default=None,
                   help="identifiant de campagne (a-z, 0-9) ; défaut : neuf à chaque exécution")
    p.add_argument("--sortie", default="sorties",
                   help="dossier du manifeste complet et du résumé texte (ignoré par git)")
    p.add_argument("--rapports", default="rapports",
                   help="dossier du rapport de campagne (markdown + JSON)")
    args = p.parse_args(argv)

    res = lancer(n=args.n, graine=args.graine, mode=args.mode,
                 client_ia=args.client_ia, realiste=args.realiste,
                 base_leurres=args.base_leurres, base_interne=args.base_interne,
                 base_backend=args.backend, campagne=args.campagne,
                 types=tuple(t.strip() for t in args.types.split(",") if t.strip()))

    texte = rapport.resume_texte(
        res["stats"], mode=res["mode"], client_ia=res["client_ia"],
        graine=res["graine"], n_par_type=res["n_par_type"],
        mesures=res["mesures"], backend_ok=res["backend_ok"],
        campagne=res["campagne"], bilan=res["bilan"])
    print(texte)
    if res["ecarts_classement"]:
        print("\nÉcarts de classement (sessions de cette campagne) :")
        for e in res["ecarts_classement"]:
            print(f"  - {e}")

    chemins = ecrire_sorties(res, texte, args.sortie, args.rapports)
    print(f"\nRapport : {chemins['rapport_md']} et {chemins['rapport_json']}")

    return 1 if res["stats"]["anomalies"] else 0


if __name__ == "__main__":
    sys.exit(main())
