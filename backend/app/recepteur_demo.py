"""Faux récepteur de webhook pour la démo : affiche chaque alerte reçue dans le terminal.

    uv run python -m app.recepteur_demo [--port N]

Sans --port, le système choisit un port libre. Le récepteur n'écoute que sur 127.0.0.1 et
répond `ok`, comme Slack. Il imprime la ligne `export DEDALE_WEBHOOK_URL=…` à poser avant de
lancer le backend. Aucune alerte ne quitte la machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_TAILLE_MAX = 1_000_000


def _texte(objet) -> str:
    if isinstance(objet, dict):
        return str(objet.get("text") or "")
    return str(objet or "")


def _clair(texte: str) -> str:
    """Retire l'échappement Slack pour l'affichage terminal."""
    return texte.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("*", "")


def formater(message: dict) -> str:
    """Rend un message Slack (`text` + `blocks`) lisible dans un terminal."""
    lignes = ["", "─" * 64]
    for bloc in message.get("blocks") or []:
        genre = bloc.get("type")
        if genre == "header":
            lignes.append(_clair(_texte(bloc.get("text"))).upper())
        elif genre == "section":
            if bloc.get("text"):
                lignes.append(_clair(_texte(bloc.get("text"))))
            for champ in bloc.get("fields") or []:
                lignes.append("  " + _clair(_texte(champ)).replace("\n", " : ", 1))
        elif genre == "actions":
            for el in bloc.get("elements") or []:
                if el.get("url"):
                    lignes.append(f"→ {_texte(el.get('text'))} : {el['url']}")
        elif genre == "context":
            lignes.append(" · ".join(_clair(_texte(el)) for el in bloc.get("elements") or []))
    if not message.get("blocks"):
        lignes.append(_clair(str(message.get("text") or "")))
    lignes.append("─" * 64)
    return "\n".join(lignes)


class _Recepteur(BaseHTTPRequestHandler):
    server_version = "DedaleRecepteurDemo/1.0"

    def do_POST(self):  # noqa: N802 (nom imposé par http.server)
        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            taille = -1
        if taille < 0 or taille > _TAILLE_MAX:
            self._repondre(413, b"trop gros")
            return
        try:
            message = json.loads(self.rfile.read(taille) or b"{}")
            if not isinstance(message, dict):
                raise ValueError
        except ValueError:
            self._repondre(400, b"json invalide")
            return
        self.server.recus.append(message)
        if self.server.afficher:
            print(formater(message), flush=True)
        self._repondre(200, b"ok")

    def _repondre(self, code: int, corps: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):  # silence : seul le message compte
        pass


def creer_serveur(port: int = 0, afficher: bool = True) -> ThreadingHTTPServer:
    serveur = ThreadingHTTPServer(("127.0.0.1", port), _Recepteur)
    serveur.recus = []
    serveur.afficher = afficher
    return serveur


def url_de(serveur: ThreadingHTTPServer) -> str:
    hote, port = serveur.server_address[:2]
    return f"http://{hote}:{port}/webhook"


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Faux récepteur Slack/Teams pour la démo Dédale.")
    parseur.add_argument("--port", type=int, default=0, help="port d'écoute (défaut : un port libre)")
    args = parseur.parse_args(argv)
    serveur = creer_serveur(args.port)
    url = url_de(serveur)
    print(f"Récepteur de démo à l'écoute sur {url}")
    print(f"Avant de lancer le backend : export DEDALE_WEBHOOK_URL={url}", flush=True)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
