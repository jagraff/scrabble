"""Exhaustive enumeration of move geometries with rigorous score upper bounds.

Completeness argument
=====================

Every legal Scrabble move places 1..7 tiles in a single line. There is
always at least one direction d such that the maximal run (in direction d)
through the placed tiles has length >= 2 and contains ALL placed tiles
(for multi-tile moves this is the placement direction; for one-tile moves
at least one of the two runs has length >= 2, else no word is formed and
the move is illegal). Call that run the *main word* w, its cells the
*span*, and the placed cells S (1 <= |S| <= min(7, len(span))).

The move's score is exactly

    WM(S) * MainSum(w, S) + sum_{c in S} CrossScore(c) + 50*[|S| = 7]

where WM(S) is the product of word multipliers under placed cells,
MainSum is the sum of the main word's tile values with letter premiums
applied at placed cells only, and CrossScore(c) is the score of the
perpendicular word through c if one is formed (0 otherwise).  This is the
standard scoring rule and is unit-tested in the rules engine.

Transposing the board maps vertical moves to horizontal moves, preserves
premiums (tested in test_bounds.py), the lexicon and the tile bag, so it
suffices to enumerate horizontal moves.

We enumerate ALL tuples (row r, start c0, word w) with w in the lexicon
(the main word must always be a lexicon word) and compute an upper bound
on the score of ANY legal move realizing that tuple (maximized exactly
over the placed set S under the relaxations below).  Relaxing constraints
can only increase the bound, so any tuple whose relaxed maximum is below
the reference score is rigorously excluded, for every board position and
any rack.

Relaxations used (each one only enlarges the feasible set / the bound):

1. Cross words are bounded independently per placed cell: the best
   lexicon word W containing the placed letter L at a position k that
   geometrically fits in a 15-cell column through row r (k <= r and
   len(W)-1-k <= 14-r).  Interactions between different cross words
   (adjacency validity, shared tile inventory) are ignored.
2. Tile inventory is enforced only per word: a word using more copies of
   a letter than the bag holds must use blanks (value 0, at most 2 in the
   whole game), and each blank is assumed to sit on a multiplier-1 cell
   (the least possible loss).  Words needing more than 2 excess copies
   can never appear on any board and are excluded (a sound exclusion).
3. The hook tile of a cross word is assumed to be a real (non-blank)
   tile; a real tile always scores at least as much as a blank.
4. Pre-existing tiles in the main word are assumed non-blank (maximum
   value) and require no support from the rest of the board; board
   connectivity, the first-move rule and reachability are ignored.
5. Bingo bonus is granted whenever |S| = 7.

The per-tuple maximization over S is exact under those relaxations
(relaxed_max_for_span): word-multiplier cells are enumerated exhaustively
(a row contains at most 4 of them) and the remaining picks are greedy
over independent non-negative gains, which is optimal because once the
word multiplier is fixed the objective is additive over the picks.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from .rules import DISTRIBUTION, N, VALUES, letter_multiplier, word_multiplier

NEG = float('-inf')
MAX_TILE_VALUE = 10


def word_excess(word: str) -> int:
    """Number of tiles that must be blanks if this word appears on a board."""
    return sum(max(0, n - DISTRIBUTION[ch]) for ch, n in Counter(word).items())


def word_playable(word: str) -> bool:
    """False if the word can never appear on any board (needs > 2 blanks)."""
    return word_excess(word) <= 2


def raw_sum(word: str) -> int:
    return sum(VALUES[ch] for ch in word)


def adjusted_sum(word: str) -> int:
    """Max total value of the word's tiles alone: excess copies are blanks."""
    total = 0
    for ch, n in Counter(word).items():
        total += VALUES[ch] * min(n, DISTRIBUTION[ch])
    return total


def best_rest_table(lexicon) -> dict[str, list[float]]:
    """best_rest[L][r] = max over cross words W and hook positions k
    (W[k] == L, W fits vertically through row r) of the value-sum of W's
    OTHER letters (per-word inventory adjusted, hook tile real).

    -inf where no cross word fits at all.
    """
    table = {ch: [NEG] * N for ch in VALUES if ch != '?'}
    for w in lexicon:
        m = len(w)
        if m < 2 or m > N or not word_playable(w):
            continue
        adj = adjusted_sum(w)
        for k, ch in enumerate(w):
            rest = adj - VALUES[ch]
            arr = table[ch]
            for r in range(k, k + (N - m) + 1):
                if rest > arr[r]:
                    arr[r] = rest
    return table


def cross_bound_table(best_rest) -> dict[str, list[list[int]]]:
    """cb[L][r][c] = upper bound on the cross-word score contribution of a
    tile L newly placed at (r, c), including the hook tile's own value.
    0 where no cross word fits (placing no cross word is always allowed)."""
    cb = {}
    for ch, by_row in best_rest.items():
        grid = [[0] * N for _ in range(N)]
        v = VALUES[ch]
        for r in range(N):
            rest = by_row[r]
            if rest == NEG:
                continue
            for c in range(N):
                wm = word_multiplier((r, c))
                lm = letter_multiplier((r, c))
                grid[r][c] = max(0, wm * (v * lm + rest))
        cb[ch] = grid
    return cb


def geometry_cap_table(lexicon, cb):
    """cap[r][c0][L] = word-independent upper bound for ANY main word of
    length L at (r, c0..c0+L-1):

      wm_prod * (VMAX[L] + sum over letter-premium cells of (lm-1)*10)
      + top-7 over span of (max over letters of cb) + 50.

    Sound because MainSum <= VMAX[L] + premium boosts (letter values are
    at most 10), the word multiplier is at most the product over all
    word-multiplier cells in the span (at most 4 in a row), each placed
    cell's cross contribution is at most the best over all letters, at
    most 7 cells are placed, and the bingo bonus is at most 50."""
    vmax = [0] * (N + 1)
    for w in lexicon:
        m = len(w)
        if m <= N and word_playable(w):
            s = adjusted_sum(w)
            if s > vmax[m]:
                vmax[m] = s
    maxcb = [[max(cb[ch][r][c] for ch in cb) for c in range(N)]
             for r in range(N)]
    cap = [[[0] * (N + 1) for _ in range(N + 1)] for _ in range(N)]
    for r in range(N):
        for c0 in range(N):
            wm_prod = 1
            prem_boost = 0
            cbs = []
            for L in range(1, N - c0 + 1):
                c = c0 + L - 1
                wm_prod *= word_multiplier((r, c))
                prem_boost += (letter_multiplier((r, c)) - 1) * MAX_TILE_VALUE
                cbs.append(maxcb[r][c])
                top7 = sum(sorted(cbs, reverse=True)[:7])
                cap[r][c0][L] = wm_prod * (vmax[L] + prem_boost) + top7 + 50
    return cap, vmax


@dataclass
class Candidate:
    word: str
    row: int
    col0: int
    relaxed_max: int
    placed_cols: tuple[int, ...]

    def to_json(self):
        return {'word': self.word, 'row': self.row, 'col0': self.col0,
                'relaxed_max': self.relaxed_max,
                'placed_cols': list(self.placed_cols)}


def relaxed_max_for_span(word, r, c0, cb):
    """Exact maximum of the relaxed objective over placed subsets S.

    Returns (value, placed_cols)."""
    L = len(word)
    cells = list(range(c0, c0 + L))
    vals = [VALUES[ch] for ch in word]
    base = adjusted_sum(word)  # excess copies blank at multiplier-1 cells

    wm_cells = []
    other = []
    for i, c in enumerate(cells):
        if word_multiplier((r, c)) > 1:
            wm_cells.append((i, word_multiplier((r, c))))
        else:
            other.append(i)

    best = (NEG, ())
    for mask in range(1 << len(wm_cells)):
        WM = 1
        P = []
        for j, (i, wm) in enumerate(wm_cells):
            if mask >> j & 1:
                WM *= wm
                P.append(i)
        if len(P) > 7:
            continue
        budget = 7 - len(P)
        gains = []
        for i in other:
            c = cells[i]
            g = (WM * vals[i] * (letter_multiplier((r, c)) - 1)
                 + cb[word[i]][r][c])
            gains.append((g, i))
        gains.sort(reverse=True)
        take = gains[:budget]
        placed_count = len(P) + len(take)
        if placed_count == 0:
            continue
        total = WM * base
        for i in P:
            total += cb[word[i]][r][cells[i]]
        total += sum(g for g, _ in take)
        if placed_count == 7:
            total += 50
        if total > best[0]:
            cols = tuple(sorted(cells[i] for i in P + [i for _, i in take]))
            best = (total, cols)
    return best


def enumerate_candidates(lexicon, threshold=1786, progress=None):
    """Return every (word, row, col0) whose relaxed max >= threshold."""
    best_rest = best_rest_table(lexicon)
    cb = cross_bound_table(best_rest)
    cap, vmax = geometry_cap_table(lexicon, cb)

    # list of geometries that can possibly reach the threshold, per length
    live_geoms = [[] for _ in range(N + 1)]
    for L in range(2, N + 1):
        for r in range(N):
            for c0 in range(N - L + 1):
                if cap[r][c0][L] >= threshold:
                    live_geoms[L].append((r, c0))

    out = []
    words = sorted(w for w in lexicon if word_playable(w) and 2 <= len(w) <= N)
    for idx, w in enumerate(words):
        if progress and idx % 20000 == 0:
            progress(idx, len(words), len(out))
        for r, c0 in live_geoms[len(w)]:
            val, cols = relaxed_max_for_span(w, r, c0, cb)
            if val >= threshold:
                out.append(Candidate(w, r, c0, int(val), cols))
    return out, {'cap': cap, 'vmax': vmax, 'best_rest': best_rest, 'cb': cb,
                 'live_geoms': live_geoms}


def main():
    import argparse
    import os
    import time

    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--out', default='results/candidates.json')
    args = ap.parse_args()
    lex = load()
    t0 = time.time()

    def prog(i, n, found):
        print(f"  {i}/{n} words, {found} candidates, {time.time()-t0:.0f}s",
              flush=True)

    cands, aux = enumerate_candidates(lex, args.threshold, progress=prog)
    cands.sort(key=lambda c: -c.relaxed_max)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)

    live = {L: aux['live_geoms'][L] for L in range(2, N + 1)
            if aux['live_geoms'][L]}
    with open(args.out, 'w') as f:
        json.dump({'threshold': args.threshold,
                   'count': len(cands),
                   'live_geometries_by_length':
                       {str(L): v for L, v in live.items()},
                   'candidates': [c.to_json() for c in cands]}, f, indent=1)
    print(f"\n{len(cands)} candidates with relaxed max >= {args.threshold} "
          f"({time.time()-t0:.0f}s) -> {args.out}")
    print("live geometries by length:",
          {L: len(v) for L, v in live.items()})
    for c in cands[:40]:
        print(f"  {c.relaxed_max:5d}  {c.word:>15s} row={c.row} c0={c.col0} "
              f"placed={c.placed_cols}")


if __name__ == '__main__':
    main()
