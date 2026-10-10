"""Gestionnaire du flux temps réel WS /ws pour la console du SOC."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import WebSocket


class Diffuseur:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.lock = asyncio.Lock()
        # Posé par validation_metier.brancher : le SOC ne reçoit que la vue minimisée.
        self.filtre = None

    async def connecter(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self.lock:
            self.clients.add(ws)

    async def deconnecter(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.discard(ws)

    async def diffuser(self, type_: str, donnees: dict) -> None:
        if self.filtre is not None:
            donnees = self.filtre(type_, donnees)
        message = {"type": type_, "donnees": donnees}
        async with self.lock:
            cibles = list(self.clients)
        morts = []
        for ws in cibles:
            try:
                await ws.send_json(message)
            except Exception:
                morts.append(ws)
        if morts:
            async with self.lock:
                for ws in morts:
                    self.clients.discard(ws)
                    with contextlib.suppress(Exception):
                        await ws.close()


diffuseur = Diffuseur()
