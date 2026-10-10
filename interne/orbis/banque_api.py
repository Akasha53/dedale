"""Petite API bancaire locale de démo pour le scénario réel.

Une vraie API HTTP (FastAPI/uvicorn) sur 127.0.0.1, sur un port libre, qui écrit chaque
virement demandé dans un fichier JSONL. Elle remplace, pour le mode réel, le faux objet en
mémoire `Outils.executer_paiement` : l'agent appelle réellement cet endpoint à travers la
passerelle, et le fichier prouve après coup ce qui est passé.

Tout est local et fictif. Aucun virement réel, aucun compte réel : des montants et des noms
inventés d'Orbis Pay, écrits dans un fichier du bac à sable. Rien ne quitte la machine.

Dépendances `fastapi`/`uvicorn` : présentes seulement dans l'extra `reel` de ce module. Ce
fichier n'est importé que par le scénario réel ; le reste d'`interne/` reste sans dépendance.
"""

from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path


def _port_libre() -> int:
    """Un port TCP libre sur la boucle locale (on le relâche aussitôt pour le passer à uvicorn)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def construire_app(fichier_virements: Path):
    """Fabrique l'app FastAPI. Chaque POST /virements ajoute une ligne au fichier JSONL."""
    from fastapi import Body, FastAPI, HTTPException

    fichier = Path(fichier_virements)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    verrou = threading.Lock()

    app = FastAPI(title="Banque de démo Orbis Pay (locale)")

    @app.get("/sante")
    def sante() -> dict:
        return {"etat": "ok", "fichier": str(fichier)}

    @app.post("/virements")
    def executer(corps: dict = Body(...)) -> dict:
        # Validation manuelle (pas de modèle Pydantic local, qui casse la résolution de FastAPI).
        if "montant" not in corps or "beneficiaire" not in corps:
            raise HTTPException(status_code=422, detail="montant et beneficiaire sont requis")
        try:
            montant = float(corps["montant"])
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail="montant invalide") from e
        ligne = {
            "horodatage": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "montant": montant,
            "beneficiaire": str(corps["beneficiaire"]),
            "motif": corps.get("motif"),
            "iban": corps.get("iban"),
            "statut": "enregistre",
        }
        with verrou:
            with fichier.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            numero = sum(1 for _ in fichier.open(encoding="utf-8"))
        return {"id": f"VIR-{numero:04d}", **ligne}

    @app.get("/virements")
    def lister() -> dict:
        if not fichier.exists():
            return {"virements": [], "total": 0}
        lignes = [json.loads(x) for x in fichier.read_text(encoding="utf-8").splitlines() if x.strip()]
        return {"virements": lignes, "total": len(lignes)}

    return app


class BanqueLocale:
    """Lance l'API bancaire dans un fil de fond (uvicorn) et l'arrête proprement.

    Usage : `with BanqueLocale(fichier) as banque: banque.base`.
    """

    def __init__(self, fichier_virements: Path, *, hote: str = "127.0.0.1", port: int | None = None):
        self.fichier = Path(fichier_virements)
        self.hote = hote
        self.port = port or _port_libre()
        self._serveur = None
        self._fil: threading.Thread | None = None

    @property
    def base(self) -> str:
        return f"http://{self.hote}:{self.port}"

    def demarrer(self, attente_s: float = 10.0) -> "BanqueLocale":
        import time
        import urllib.request

        import uvicorn

        app = construire_app(self.fichier)
        config = uvicorn.Config(app, host=self.hote, port=self.port, log_level="warning")
        self._serveur = uvicorn.Server(config)
        self._fil = threading.Thread(target=self._serveur.run, daemon=True)
        self._fil.start()
        # Attendre que /sante réponde.
        debut = time.monotonic()
        while time.monotonic() - debut < attente_s:
            try:
                with urllib.request.urlopen(self.base + "/sante", timeout=0.5):
                    return self
            except Exception:  # noqa: BLE001 — démarrage : on réessaie jusqu'à l'attente max
                time.sleep(0.1)
        raise RuntimeError(f"l'API bancaire locale n'a pas démarré sur {self.base}")

    def arreter(self) -> None:
        if self._serveur is not None:
            self._serveur.should_exit = True
        if self._fil is not None:
            self._fil.join(timeout=5.0)

    def __enter__(self) -> "BanqueLocale":
        return self.demarrer()

    def __exit__(self, *a) -> None:
        self.arreter()
