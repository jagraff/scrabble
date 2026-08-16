"""Question B: is a static position reachable by a legal game?

Backwards search ("unplay"): repeatedly guess the last move — a set of
1..7 tiles lying in one line that (a) formed a contiguous run with the
tiles already present, (b) whose removal leaves a position that is still
valid (every maximal run a word, connected through the center, or empty),
and (c) which was itself a legal move on that smaller position.  Because
the current position is valid, every word formed by the guessed move is a
current maximal run and hence valid, so each unplay step preserves the
invariant and reaching the empty board yields a complete legal game
transcript (cooperative players; tile draws in a constructed game are
unconstrained, and racks of up to 7 tiles suffice since moves place at
most 7 tiles).
"""

from __future__ import annotations

import sys
from itertools import combinations

from .board import (IllegalMove, IllegalPosition, Move, apply_move,
                    check_static_position, parse_board)
from .rules import CENTER, N, Tile, coord_name


def _perp_ok(grid, cell, removed, horiz, lexicon):
    """After removing `removed` cells (all in one line with direction
    `horiz`), the perpendicular run through `cell` splits; both remaining
    parts must be valid (words if len >= 2)."""
    r, c = cell
    parts = []
    for dr, dc in (((0, -1), (0, 1)) if not horiz else ((-1, 0), (1, 0))):
        seg = []
        rr, cc = r + dr, c + dc
        while (rr, cc) in grid:
            seg.append((rr, cc))
            rr, cc = rr + dr, cc + dc
        parts.append(seg)
    for seg in parts:
        if len(seg) >= 2:
            cells = sorted(seg)
            word = ''.join(grid[x].letter for x in cells)
            if word not in lexicon:
                return False
    return True


def candidate_last_moves(grid, lexicon, per_node_cap=4000):
    """Yield Move objects that could plausibly have been the last move,
    cheaply pre-filtered (full validation is done by the caller)."""
    seen = set()
    count = 0
    for horiz in (True, False):
        for a in range(N):
            line = [(a, b) if horiz else (b, a) for b in range(N)]
            runs = []
            cur = []
            for cell in line:
                if cell in grid:
                    cur.append(cell)
                else:
                    if cur:
                        runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            for run in runs:
                L = len(run)
                if L < 2:
                    continue
                letters = [grid[c].letter for c in run]
                for k in range(min(7, L), 0, -1):
                    for comb in combinations(range(L), k):
                        cells = tuple(run[i] for i in comb)
                        if cells in seen:
                            continue
                        seen.add(cells)
                        # remaining segments of this run must be words
                        keep = [i for i in range(L) if i not in comb]
                        ok = True
                        seg = []
                        for i in keep + [None]:
                            if i is not None and (not seg or i == seg[-1] + 1):
                                seg.append(i)
                                continue
                            if len(seg) >= 2:
                                w = ''.join(letters[j] for j in seg)
                                if w not in lexicon:
                                    ok = False
                                    break
                            seg = [i] if i is not None else []
                        if not ok:
                            continue
                        # perpendicular splits at removed cells must be valid
                        if not all(_perp_ok(grid, c, cells, horiz, lexicon)
                                   for c in cells):
                            continue
                        count += 1
                        if count > per_node_cap:
                            return
                        yield Move({c: grid[c] for c in cells})


def unplay_search(grid, lexicon, *, max_nodes=200000, log=lambda s: None):
    """Try to find a legal game reaching `grid`. Returns list of moves
    (in play order) or None if the search space was exhausted / budget hit.
    """
    nodes = 0
    memo_fail = set()

    def key(g):
        return frozenset((c, t.letter, t.is_blank) for c, t in g.items())

    def rec(g, depth):
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise TimeoutError
        if not g:
            return []
        k = key(g)
        if k in memo_fail:
            return None
        # order candidate moves: prefer big removals (fewer total moves)
        cands = []
        for mv in candidate_last_moves(g, lexicon):
            pre = dict(g)
            for c in mv.placements:
                del pre[c]
            try:
                check_static_position(pre, lexicon)
            except IllegalPosition:
                continue
            try:
                res = apply_move(pre, mv, lexicon)
            except IllegalMove:
                continue
            cands.append((len(mv.placements), mv, pre))
        cands.sort(key=lambda t: -t[0])
        for _, mv, pre in cands:
            sub = rec(pre, depth + 1)
            if sub is not None:
                return sub + [mv]
        memo_fail.add(k)
        return None

    try:
        return rec(dict(grid), 0)
    except TimeoutError:
        log(f"unplay search budget exhausted ({nodes} nodes)")
        return None


def main():
    from . import known
    from .lexicon import load
    lex = load()
    grid = known.pre_board()
    seq = unplay_search(grid, lex, log=print)
    if seq is None:
        print("NO SEQUENCE FOUND (budget or exhausted)")
        sys.exit(1)
    print(f"reached the 1786 pre-board in {len(seq)} moves:")
    replay = {}
    for i, mv in enumerate(seq, 1):
        res = apply_move(replay, mv, lex)
        replay = res.new_grid
        words = ', '.join(f"{w.word}({w.score})" for w in res.words)
        cells = ', '.join(
            f"{coord_name(c)}={t.letter}{'?' if t.is_blank else ''}"
            for c, t in sorted(mv.placements.items()))
        print(f"  {i:2d}. {cells}  ->  {words}")
    # Compare by (letter, blank) rather than by Tile identity. An earlier
    # `assert replay == grid or True` sat here as well: a no-op that read
    # like a check, which is worse than no check at all.
    assert {c: (t.letter, t.is_blank) for c, t in replay.items()} == \
           {c: (t.letter, t.is_blank) for c, t in grid.items()}
    print("verified: replay reproduces the pre-board exactly")


if __name__ == '__main__':
    main()
