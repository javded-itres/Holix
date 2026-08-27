"""Short opaque tokens for messenger inline buttons (Telegram 64-byte cap)."""

from __future__ import annotations

import secrets

_TOKEN_CAP = 48


def register_callback_token(mapping: dict[str, str], full_id: str) -> str:
    """Map *full_id* to an 8-hex token. Keeps prior entries (parallel sub-agents)."""
    wanted = (full_id or "").strip()
    if not wanted:
        token = secrets.token_hex(4)
        mapping[token] = wanted
        return token
    for tok, cid in mapping.items():
        if cid == wanted:
            return tok
    token = secrets.token_hex(4)
    while token in mapping:
        token = secrets.token_hex(4)
    mapping[token] = wanted
    while len(mapping) > _TOKEN_CAP:
        mapping.pop(next(iter(mapping)), None)
    return token


def drop_callback_token(mapping: dict[str, str], full_id: str) -> None:
    """Remove the token for one confirmation; leave siblings in place."""
    wanted = (full_id or "").strip()
    dead = [tok for tok, cid in mapping.items() if cid == wanted]
    for tok in dead:
        mapping.pop(tok, None)
