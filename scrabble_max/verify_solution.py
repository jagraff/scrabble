"""Re-verify a stage-C tableau solution with the exact rules engine.

The tableau model is optimistic about blank placement, so any solution it
reports must be checked here: we reconstruct the pre-move board, assign
blanks optimally-for-real (greedy: blanks go to unscored duplicate
tiles), and run the full legality + scoring pipeline.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from .board import Move, apply_move, check_static_position, parse_board
from .rules import DISTRIBUTION, N, Tile
from .lexicon import load


def verify(board_rows, placed_cols, lexicon):
    word = board_rows[0]
    full = parse_board('\n'.join(board_rows))
    # blanks: any letter over its distribution must be blanked; choose the
    # copies NOT on row 0 and not in a placed column's cross run first
    # (unscored), else fail over to scored cells (score recomputed anyway).
    usage = Counter(t.letter for t in full.values())
    needed = {ch: max(0, n - DISTRIBUTION[ch]) for ch, n in usage.items()}
    if sum(needed.values()) > 2:
        raise ValueError('needs more than 2 blanks')
    for ch, k in needed.items():
        if not k:
            continue
        # prefer deep cells (unscored) for blanks
        cands = sorted((c for c, t in full.items() if t.letter == ch),
                       key=lambda c: -c[0])
        for cell in cands[:k]:
            full[cell] = Tile(ch, is_blank=True)
    pre = {c: t for c, t in full.items()
           if not (c[0] == 0 and c[1] in placed_cols)}
    check_static_position(pre, lexicon)
    mv = Move({(0, c): full[(0, c)] for c in placed_cols})
    res = apply_move(pre, mv, lexicon)
    return res


def main():
    lex = load()
    path = sys.argv[1] if len(sys.argv) > 1 else 'results/tableau.json'
    data = json.load(open(path))
    sol = data.get('solution')
    if not sol:
        print('no solution present in', path)
        return
    res = verify(sol['board_rows'], set(sol['placed']), lex)
    print(f"claimed {sol['value']}, rules engine says {res.total}")
    for w in res.words:
        print(f"  {w.word}: {w.score}")


if __name__ == '__main__':
    main()
