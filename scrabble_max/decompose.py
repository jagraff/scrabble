"""Refute a stubborn configuration by splitting on individual board cells.

Some configurations resist the tableau solver outright. The one left open
by tier 3 was still `UNKNOWN` after 1,300s, having neither produced a board
nor excluded one. Its 258 ceiling-surviving siblings all fell in about
three seconds, and re-running them with the score constraint removed shows
why: they are *structurally* impossible, so propagation alone refutes them.
The stubborn one has no such shallow contradiction, so the solver has to
search rather than propagate.

It does, however, decompose. Pinning a single cell -- the row-1 square
under one pre-existing column -- refuted 23 of 26 branches in ~2s each.
The hardness is concentrated in a few sub-branches rather than spread
through the problem, so splitting again on those is the natural move.

Soundness rests entirely on the option sets being **exhaustive**: every
legal board assigns *something* to the pinned cell, so if every possible
assignment is refuted, so is the configuration. Two traps, both hit while
developing this:

  * restricting a cell's letters to those with tiles still spare. A blank
    can stand in for a letter that has no copies left, so that partition
    is not exhaustive and refuting all of its branches proves nothing.
  * treating a branch that timed out as refuted. `UNKNOWN` is undecided;
    it is reported as such and never folded into the refuted count.
"""

from __future__ import annotations

import time

from .cstage import solve_tableau
from .rules import N
from .tighten import second_letters

WORD = 'OXYPHENBUTAZONE'
LETTERS = [chr(ord('A') + i) for i in range(26)]


def sound_options(lexicon, word, r, c, crosses):
    """Every value cell (r, c) can legally take, or None if it is already
    determined by the configuration and so useless as a pivot.

    `None` in the returned list means "empty". The sets are deliberately
    generous: a blank can supply any letter, so availability of tiles must
    NOT be used to narrow them.
    """
    if r == 0:
        return None                      # row 0 is the word itself
    if c in crosses:
        # inside the pinned cross word, hence already fixed
        if r < len(crosses[c]):
            return None
    if r == 1 and c not in crosses:
        # the vertical run starts at row 0, so this letter must be able to
        # follow word[c] in some lexicon word
        return [None] + sorted(second_letters(lexicon, word[c], 0))
    return [None] + LETTERS


def pivot_candidates(lexicon, word, crosses):
    """Cells worth splitting on, narrowest option set first.

    A narrow pivot makes fewer branches, and each branch is more
    constrained, so both halves of the trade point the same way."""
    out = []
    for r in range(1, N):
        for c in range(N):
            opts = sound_options(lexicon, word, r, c, crosses)
            if opts and len(opts) > 1:
                out.append((len(opts), r, c))
    out.sort()
    return [(r, c) for _, r, c in out]


def refute(lexicon, placed, crosses, threshold=1786, word=WORD,
           time_limit=25.0, max_depth=3, fixed=None, pivots=None,
           depth=0, log=print, stats=None, split_time_limit=6.0):
    """Try to prove no legal board with this configuration beats
    `threshold`. Returns (refuted, open_branches).

    `refuted` is True only if every branch reached INFEASIBLE. Any branch
    that times out at the deepest level is returned in `open_branches`,
    and the configuration is *not* refuted.
    """
    from .finalize import exact_fixed_blank_loss
    fixed = dict(fixed or {})
    stats = stats if stats is not None else {'solves': 0, 'seconds': 0.0}
    if pivots is None:
        pivots = pivot_candidates(lexicon, word, crosses)

    fb = exact_fixed_blank_loss(word, set(placed), crosses)
    if fb is None:
        return True, []                  # needs >2 blanks: impossible

    # A node that will be split if it does not resolve should not spend
    # the full budget failing to resolve. Measured on the first run: 21
    # solves took 142s, nearly all of it internal nodes burning 25s to
    # return UNKNOWN before being split anyway. Only the deepest level,
    # where there is no split to fall back on, gets the full limit.
    budget = time_limit if depth >= max_depth else min(time_limit,
                                                       split_time_limit)
    t0 = time.time()
    name, val, bound, sol = solve_tableau(
        lexicon, word, 0, time_limit=budget,
        fix_placed_exact=set(placed), fix_crosses=crosses,
        min_score=threshold + 1, known_upper=None,
        fixed_blank_loss=fb, fix_cells=fixed or None,
        log=lambda s: None, verbose=False)
    stats['solves'] += 1
    stats['seconds'] += time.time() - t0

    if name == 'INFEASIBLE':
        return True, []
    if val is not None:
        # a board beating the threshold: report, never silently swallow
        log(f'{"  " * depth}*** FEASIBLE at {val} with {fixed} ***')
        return False, [{'fixed': dict(fixed), 'status': name, 'value': val,
                        'solution': sol}]
    if depth >= max_depth:
        return False, [{'fixed': dict(fixed), 'status': name, 'value': None,
                        'solution': None}]

    # split on the narrowest unpinned pivot
    pivot = next(((r, c) for (r, c) in pivots if (r, c) not in fixed), None)
    if pivot is None:
        return False, [{'fixed': dict(fixed), 'status': 'NO_PIVOT_LEFT',
                        'value': None, 'solution': None}]

    opts = sound_options(lexicon, word, pivot[0], pivot[1], crosses)
    log(f'{"  " * depth}split {pivot} into {len(opts)} branches '
        f'(depth {depth})', flush=True)
    still_open = []
    for a in opts:
        sub = dict(fixed)
        sub[pivot] = a
        ok, opened = refute(lexicon, placed, crosses, threshold, word,
                            time_limit, max_depth, sub, pivots, depth + 1,
                            log, stats, split_time_limit)
        if not ok:
            still_open.extend(opened)
    if not still_open:
        log(f'{"  " * depth}all {len(opts)} branches refuted at {pivot}')
    return (not still_open), still_open
