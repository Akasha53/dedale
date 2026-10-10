"""Lance la surface Orbis Pay : HTTP (8701) + MCP leurre (8711).

    uv run python lancer.py

Le serveur MCP tourne dans un thread dedie (son propre boucle d'evenements).
Les deux enregistrent leurs leurres au demarrage ; si le backend (8700) est
absent, ils demarrent quand meme.
"""
from __future__ import annotations

import threading

import uvicorn

from orbis import config
from orbis.app import app
from orbis import mcp_serveur


def _demarrer_mcp() -> None:
    try:
        mcp_serveur.lancer()
    except Exception as exc:  # le MCP ne doit pas abattre le HTTP
        print(f"[leurres] serveur MCP arrete : {exc}")


def main() -> None:
    threading.Thread(target=_demarrer_mcp, daemon=True).start()
    print(f"[leurres] surface HTTP sur http://{config.HOTE}:{config.PORT_HTTP}")
    print(f"[leurres] MCP leurre sur http://{config.HOTE}:{config.PORT_MCP}/mcp")
    uvicorn.run(app, host=config.HOTE, port=config.PORT_HTTP, log_level="info")


if __name__ == "__main__":
    main()
