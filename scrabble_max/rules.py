"""Core Scrabble rules model: board premiums, tile set, scoring.

Coordinates are (row, col), 0-indexed, row 0 at the top. The standard
notation "A1" style used in reports maps row 0 -> rank 1, col 0 -> file A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

N = 15
CENTER = (7, 7)

# Official English Scrabble tile distribution (100 tiles). '?' is a blank.
DISTRIBUTION = {
    'A': 9, 'B': 2, 'C': 2, 'D': 4, 'E': 12, 'F': 2, 'G': 3, 'H': 2,
    'I': 9, 'J': 1, 'K': 1, 'L': 4, 'M': 2, 'N': 6, 'O': 8, 'P': 2,
    'Q': 1, 'R': 6, 'S': 4, 'T': 6, 'U': 4, 'V': 2, 'W': 2, 'X': 1,
    'Y': 2, 'Z': 1, '?': 2,
}
assert sum(DISTRIBUTION.values()) == 100

VALUES = {
    'A': 1, 'B': 3, 'C': 3, 'D': 2, 'E': 1, 'F': 4, 'G': 2, 'H': 4,
    'I': 1, 'J': 8, 'K': 5, 'L': 1, 'M': 3, 'N': 1, 'O': 1, 'P': 3,
    'Q': 10, 'R': 1, 'S': 1, 'T': 1, 'U': 1, 'V': 4, 'W': 4, 'X': 8,
    'Y': 4, 'Z': 10, '?': 0,
}

# Premium squares of the standard board (quadrant definition, mirrored).
_TW_QUAD = [(0, 0), (0, 7)]
_DW_QUAD = [(1, 1), (2, 2), (3, 3), (4, 4), (7, 7)]
_TL_QUAD = [(1, 5), (5, 1), (5, 5)]
_DL_QUAD = [(0, 3), (2, 6), (3, 0), (3, 7), (6, 2), (6, 6), (7, 3)]


def _mirror(cells: Iterable[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    out = set()
    for r, c in cells:
        for rr in (r, N - 1 - r):
            for cc in (c, N - 1 - c):
                out.add((rr, cc))
                out.add((cc, rr))
    return frozenset(out)


TW = _mirror(_TW_QUAD)
DW = _mirror(_DW_QUAD)
TL = _mirror(_TL_QUAD)
DL = _mirror(_DL_QUAD)

assert len(TW) == 8 and len(DW) == 17 and len(TL) == 12 and len(DL) == 24
assert not (TW & DW) and not (TL & DL) and not ((TW | DW) & (TL | DL))
assert CENTER in DW


def word_multiplier(cell: tuple[int, int]) -> int:
    if cell in TW:
        return 3
    if cell in DW:
        return 2
    return 1


def letter_multiplier(cell: tuple[int, int]) -> int:
    if cell in TL:
        return 3
    if cell in DL:
        return 2
    return 1


@dataclass(frozen=True)
class Tile:
    """A tile on the board: the letter it represents and whether it is a blank."""
    letter: str  # 'A'..'Z' (what it stands for)
    is_blank: bool = False

    @property
    def value(self) -> int:
        return 0 if self.is_blank else VALUES[self.letter]

    @property
    def inventory_key(self) -> str:
        return '?' if self.is_blank else self.letter


def coord_name(cell: tuple[int, int]) -> str:
    r, c = cell
    return f"{chr(ord('A') + c)}{r + 1}"
