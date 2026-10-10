"""Appel au modèle léger pour les petites tâches (résumé, brouillon NIS2).

Avec une clé API : appel HTTP à l'API Anthropic. Sans clé : repli sur le binaire `claude -p`.
Sans ni l'un ni l'autre : l'appelant utilise son gabarit. Rien ne bloque la boucle asyncio
(l'appel réseau a un délai court, le subprocess tourne dans un thread).

Le texte envoyé au modèle est strictement de la donnée. On n'y injecte jamais de contenu de
leurre brut : l'appelant ne passe que des faits déjà structurés et neutralisés.
"""

from __future__ import annotations

import asyncio

import httpx

from . import config

_API = "https://api.anthropic.com/v1/messages"


async def generer(prompt: str, max_tokens: int = 1024, timeout: float = 20.0) -> str | None:
    """Retourne le texte produit, ou None si aucun backend n'est disponible/n'a répondu."""
    if not config.LLM_ACTIF:
        return None
    if config.CLE_API:
        try:
            return await _via_api(prompt, max_tokens, timeout)
        except Exception:
            return None
    try:
        return await _via_cli(prompt, timeout)
    except Exception:
        return None


async def _via_api(prompt: str, max_tokens: int, timeout: float) -> str | None:
    entetes = {
        "x-api-key": config.CLE_API,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    corps = {
        "model": config.MODELE_LEGER,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(_API, headers=entetes, json=corps)
        r.raise_for_status()
        data = r.json()
        blocs = data.get("content", [])
        textes = [b.get("text", "") for b in blocs if b.get("type") == "text"]
        return "\n".join(t for t in textes if t) or None


async def _via_cli(prompt: str, timeout: float) -> str | None:
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--model", config.MODELE_LEGER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), timeout=timeout)
    except (asyncio.TimeoutError, FileNotFoundError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return None
    texte = out.decode("utf-8", "replace").strip()
    return texte or None
