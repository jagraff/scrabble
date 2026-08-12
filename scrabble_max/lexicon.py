from __future__ import annotations

import functools
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data' / 'NWL2023.txt'


@functools.lru_cache(maxsize=None)
def load(path: str | None = None) -> frozenset[str]:
    p = Path(path) if path else DATA
    words = frozenset(w.strip().upper() for w in p.read_text().split())
    assert all(w.isalpha() for w in words)
    return words
