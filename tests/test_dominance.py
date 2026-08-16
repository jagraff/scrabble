"""Randomised dominance testing: every bound must dominate every real play.

The whole argument is a tower of exhaustive case analyses, and each level
eliminates cases using an upper bound. It is sound only if every bound is a
*genuine* upper bound -- every stage may only enlarge the feasible set,
never shrink it. That property is argued in prose, guarded by directional
comparisons between runs, and spot-checked against exactly one board: the
1,786 construction.

One board is a thin guard on the property everything rests on. So: generate
legal plays, score them exactly with the rules engine, and require every
bound to dominate. A bound that falls below a score a real play achieves is
refuting a play that demonstrably exists, which is the one failure mode that
makes the theorem false rather than merely unproven.

**What this catches, and what it does not.** Measured by mutation (see
`test_the_fuzzer_catches_a_broken_cap`): a single mis-tabulated cap cell is
caught immediately; scaling every cap by 0.9 passes silently. The second is
not a defect. The stage-A geometry cap is coarse on purpose -- its job is to
eliminate most geometries cheaply -- so it sits far above what play in those
geometries can reach, and a 10% shave leaves it a valid upper bound in most
spans.

Dominance testing is therefore a weak instrument for coarse bounds and a
sharp one for tight ones. This project's two real bugs -- the
`cross_options` dedup shrinking the feasible region, and the blank
accounting overcharging -- were in stage B and the blank penalty, whose
bounds sit within a few points of the 1,786 they must not refute. Those are
guarded by the single-board checks in `test_tighten.py` and
`test_blank_penalty.py`, which is where they were in fact caught. This file
adds breadth across geometries; it does not replace them, and random search
cannot reach the extremal region where they bite.

Runtime is capped by wall clock, not by iteration count, so the fast test
stays fast on a slow machine instead of merely doing fewer iterations on a
fast one. Seeded, so a failure reproduces.
"""

import random
import time
from collections import Counter

import pytest

from scrabble_max.board import (IllegalMove, IllegalPosition, Move,
                                apply_move, check_static_position)
from scrabble_max.bounds import (best_rest_table, cross_bound_table,
                                 geometry_cap_table, relaxed_max_for_span)
from scrabble_max.lexicon import load
from scrabble_max.rules import CENTER, DISTRIBUTION, N, Tile

FAST_BUDGET = 3.0
SLOW_BUDGET = 30.0


@pytest.fixture(scope='module')
def tables():
    lex = load()
    cb = cross_bound_table(best_rest_table(lex))
    cap, _ = geometry_cap_table(lex, cb)
    by_len = {}
    for w in lex:
        if len(w) <= N:
            by_len.setdefault(len(w), []).append(w)
    for k in by_len:
        by_len[k].sort()                      # order must not depend on hash
    return lex, cb, cap, by_len


def _line_cells(r, c, length, horiz):
    return [(r, c + i) if horiz else (r + i, c) for i in range(length)]


def _try_move(grid, word, cells, lex, bag):
    """Place `word` on `cells`, using only tiles the bag still holds.

    Returns (result, placements) or None. Every rule is checked by
    `apply_move`; inventory is checked here because a board using nine Es
    is not a legal position and a bound owes it nothing.
    """
    placements = {}
    need = Counter()
    for ch, cell in zip(word, cells):
        if cell in grid:
            if grid[cell].letter != ch:
                return None
            continue
        placements[cell] = Tile(ch)
        need[ch] += 1
    if not placements or len(placements) > 7:
        return None
    for ch, n in need.items():
        if bag[ch] < n:
            return None
    try:
        res = apply_move(grid, Move(placements), lex)
    except (IllegalMove, IllegalPosition, ValueError):
        return None
    return res, placements


_PREFIXES = None


def _game_prefixes(lex):
    """Boards reached after each move of the known 26-move game.

    Random play from an empty board only reaches sparse positions -- the
    first version of this test topped out at 150 points, which exercises a
    bound of 2,238 not at all. The record's own pre-move board is the
    opposite problem: at 97 tiles it is too full for a long word to fit, and
    it topped out at 72.

    The prefixes span both, 5 tiles to 97, so a long play has somewhere to
    go while the board is still dense enough to build cross-words. Every
    prefix is legal by construction, being a position the known game
    actually passed through.
    """
    global _PREFIXES
    if _PREFIXES is None:
        from scrabble_max.racks import full_sequence
        out, grid = [], {}
        for mv in full_sequence():
            grid = apply_move(grid, Move(dict(mv)), lex).new_grid
            out.append(dict(grid))
        _PREFIXES = out
    return _PREFIXES


def _bag_of(grid):
    bag = Counter(DISTRIBUTION)
    bag['?'] = 2
    for t in grid.values():
        bag['?' if t.is_blank else t.letter] -= 1
    return bag


def random_plays(tables, seed=0, budget=FAST_BUDGET, max_plays=None,
                 start='empty'):
    """Yield (grid_before, placements, result, horiz) for legal plays.

    Builds boards the way a game does -- legal move after legal move --
    because a board assembled any other way is not necessarily reachable,
    and a bound owes nothing to an unreachable position.
    """
    lex, cb, cap, by_len = tables
    rng = random.Random(seed)
    deadline = time.time() + budget
    n = 0

    while time.time() < deadline and (max_plays is None or n < max_plays):
        if start == 'game':
            # a position the known game actually passed through: legal by
            # construction, and dense enough for cross-words to score
            grid = dict(rng.choice(_game_prefixes(lex)))
            bag = _bag_of(grid)
            for _ in range(rng.randint(4, 12)):
                if time.time() > deadline:
                    break
                got = _extend(grid, bag, tables, rng)
                if got is None:
                    continue
                res, placed, horiz = got
                yield dict(grid), placed, res, horiz
                n += 1
                grid = res.new_grid
            continue
        grid, bag = {}, Counter(DISTRIBUTION)
        # opening move: through the centre, which is what makes it legal
        L = rng.randint(2, 7)
        word = rng.choice(by_len[L])
        horiz = rng.random() < 0.5
        off = rng.randint(0, L - 1)
        r, c = (CENTER[0], CENTER[1] - off) if horiz else \
               (CENTER[0] - off, CENTER[1])
        if not (0 <= r < N and 0 <= c < N):
            continue
        cells = _line_cells(r, c, L, horiz)
        if any(not (0 <= x < N and 0 <= y < N) for x, y in cells):
            continue
        got = _try_move(grid, word, cells, lex, bag)
        if got is None:
            continue
        res, placed = got
        for ch in (t.letter for t in placed.values()):
            bag[ch] -= 1
        yield dict(grid), placed, res, horiz
        n += 1
        grid = res.new_grid

        # then extend the board for a while, crossing existing tiles
        for _ in range(rng.randint(1, 12)):
            if time.time() > deadline:
                break
            got = _extend(grid, bag, tables, rng)
            if got is None:
                continue
            res, placed, horiz = got
            yield dict(grid), placed, res, horiz
            n += 1
            grid = res.new_grid


def _extend(grid, bag, tables, rng):
    """One random legal play crossing a tile already on the board.

    Biased towards the edge rows and long words: those are where the word
    multipliers stack and where the bounds under test are largest, so an
    unbiased generator spends its whole budget in a region that tests
    nothing.
    """
    lex, cb, cap, by_len = tables
    cells_sorted = sorted(grid)
    if not cells_sorted:
        return None
    if rng.random() < 0.5:
        edge = [c for c in cells_sorted if c[0] in (0, N - 1)
                or c[1] in (0, N - 1)]
        anchor = rng.choice(edge or cells_sorted)
    else:
        anchor = rng.choice(cells_sorted)
    ch0 = grid[anchor].letter
    L = rng.randint(7, N) if rng.random() < 0.5 else rng.randint(2, 8)
    cands = by_len.get(L)
    if not cands:
        return None
    word = rng.choice(cands)
    if ch0 not in word:
        return None
    horiz = rng.random() < 0.5
    idx = word.index(ch0)
    r, c = (anchor[0], anchor[1] - idx) if horiz else (anchor[0] - idx,
                                                       anchor[1])
    cells = _line_cells(r, c, L, horiz)
    if any(not (0 <= x < N and 0 <= y < N) for x, y in cells):
        return None
    got = _try_move(grid, word, cells, lex, bag)
    if got is None:
        return None
    res, placed = got
    for t in placed.values():
        bag['?' if t.is_blank else t.letter] -= 1
    return res, placed, horiz


def _span(placements, grid_after, horiz):
    """The main word's span: (line index, start, length).

    The main word runs through every placed cell, so it is the maximal run
    containing them -- which may reach well beyond the tiles just played.
    """
    cells = sorted(placements)
    line = cells[0][0] if horiz else cells[0][1]
    lo = hi = (cells[0][1] if horiz else cells[0][0])
    hi = (cells[-1][1] if horiz else cells[-1][0])
    step = (0, 1) if horiz else (1, 0)

    def at(i):
        return (line, i) if horiz else (i, line)

    while lo - 1 >= 0 and at(lo - 1) in grid_after:
        lo -= 1
    while hi + 1 < N and at(hi + 1) in grid_after:
        hi += 1
    del step
    return line, lo, hi - lo + 1


def _check(tables, seed, budget, start='empty'):
    """Every play must be dominated by the geometry cap for its span, and
    by the word-specific stage-A bound."""
    lex, cb, cap, by_len = tables
    checked, worst = 0, (0, None)
    for grid_before, placements, res, horiz in random_plays(
            tables, seed=seed, budget=budget, start=start):
        checked += 1
        line, start, length = _span(placements, res.new_grid, horiz)
        # cap is tabulated over rows; the premium layout is symmetric under
        # transposition, so a column play reads the same table transposed.
        c = cap[line][start][length]
        assert res.total <= c, (
            f'GEOMETRY CAP VIOLATED: a legal play scores {res.total} but '
            f'cap[{line}][{start}][{length}] = {c}. The cap is an upper '
            f'bound used to eliminate whole geometries, so a play above it '
            f'means eliminations were unsound. placements='
            f'{ {k: v.letter for k, v in placements.items()} }')
        if res.total > worst[0]:
            worst = (res.total, (line, start, length))

        main = [w for w in res.words
                if len(w.cells) == length
                and (w.cells[0][0] == line if horiz else
                     w.cells[0][1] == line)]
        if main and length == N and horiz and line in (0, N - 1):
            b, _ = relaxed_max_for_span(main[0].word, line, start, cb)
            assert res.total <= b, (
                f'STAGE-A WORD BOUND VIOLATED: {main[0].word} on row '
                f'{line} scores {res.total} > relaxed max {b}')
    return checked, worst


def test_the_record_play_is_dominated(tables):
    """The sharpest single case, and the one the chain must never refute:
    the 1,786 construction itself, scored by the rules engine."""
    from scrabble_max import known
    lex, cb, cap, _ = tables
    res = apply_move(known.pre_board(), known.MOVE, lex)
    assert res.total == known.EXPECTED_SCORE == 1786
    assert res.total <= cap[0][0][15], (
        f'the geometry cap {cap[0][0][15]} is below the 1786 play it must '
        f'dominate')
    b, _ = relaxed_max_for_span('OXYPHENBUTAZONE', 0, 0, cb)
    assert res.total <= b


def test_random_legal_plays_are_dominated(tables):
    checked, worst = _check(tables, seed=0, budget=FAST_BUDGET)
    assert checked >= 20, (
        f'only {checked} plays generated in {FAST_BUDGET}s -- the generator '
        f'is not producing legal moves, so this test proves nothing')
    print(f'\n  from empty: {checked} legal plays dominated; '
          f'highest {worst[0]} at span {worst[1]}')


def test_higher_scoring_plays_are_dominated(tables):
    """Plays into the known game's own positions, which score an order of
    magnitude higher than play from an empty board.

    What this does NOT do is reach the extremal tip. 1,786 is a
    hand-constructed position of a kind random search will not stumble
    into -- that is what makes it a record -- so the top of the range is
    covered by `test_the_record_play_is_dominated` and by the pipeline's
    own bounds, not here. The value of this test is breadth: a bound that
    is wrong *systematically* rather than only in the last few points shows
    up across thousands of ordinary plays.
    """
    checked, worst = _check(tables, seed=0, budget=FAST_BUDGET,
                            start='game')
    assert checked >= 20, f'only {checked} plays generated'
    assert worst[0] >= 200, (
        f'highest score generated was {worst[0]}; this test exists to '
        f'exercise the bounds well above trivial plays, and at that score '
        f'it is not doing so')
    print(f'\n  from game positions: {checked} legal plays dominated; '
          f'highest {worst[0]} at span {worst[1]}')


@pytest.mark.parametrize('seed', [1, 2, 3])
def test_random_legal_plays_are_dominated_other_seeds(tables, seed):
    checked, _ = _check(tables, seed=seed, budget=FAST_BUDGET / 3)
    assert checked >= 5


@pytest.mark.slow
def test_random_legal_plays_are_dominated_at_length(tables):
    checked, worst = _check(tables, seed=99, budget=SLOW_BUDGET)
    print(f'\n  {checked} legal plays dominated; highest {worst[0]} '
          f'at span {worst[1]}')


def _best_main_word_in_span(lex, r, c0, L):
    """The largest main-word contribution achievable in a span.

    Recomputed word by word, where the cap reaches the same quantity through
    `vmax[L]`. It is not an independent derivation of the cap and does not
    pretend to be: what it catches is `vmax` being computed over too small a
    set of words -- if `word_playable` ever filtered too aggressively, the
    cap would drop below a word that can really be played, and this says so.
    """
    from scrabble_max.bounds import adjusted_sum, word_playable
    from scrabble_max.rules import letter_multiplier, word_multiplier
    MAX_TILE = 10

    wm_prod, prem = 1, 0
    for i in range(L):
        cell = (r, c0 + i)
        wm_prod *= word_multiplier(cell)
        prem += (letter_multiplier(cell) - 1) * MAX_TILE
    best = 0
    for w in lex:
        if len(w) == L and word_playable(w):
            s = adjusted_sum(w)
            if s > best:
                best = s
    return wm_prod * (best + prem)


@pytest.mark.parametrize('r,c0,L', [
    (0, 0, 15), (14, 0, 15), (7, 0, 15), (0, 0, 7), (0, 8, 7),
    (7, 7, 1), (3, 3, 9), (1, 1, 5),
])
def test_cap_dominates_the_best_main_word_in_its_span(tables, r, c0, L):
    """The cap must dominate the best word that span can actually hold."""
    lex, cb, cap, _ = tables
    best = _best_main_word_in_span(lex, r, c0, L)
    assert cap[r][c0][L] >= best, (
        f'cap[{r}][{c0}][{L}] = {cap[r][c0][L]} is below the {best} that '
        f'the best main word in that span actually scores; the cap is not '
        f'an upper bound')


def test_the_fuzzer_catches_a_broken_cap(tables):
    """Sensitivity, measured rather than assumed.

    A dominance test that cannot fail is decoration, so this pins what the
    fuzzer detects. It catches a cap that has dropped below a score real
    play reaches.

    What it does NOT catch, measured: scaling every cap by 0.9 passes
    silently. That is not a defect. Random play reaches ~250 in the
    geometries it samples while the caps run to ~2,238, and a cap shaved by
    10% is in most spans *still a valid upper bound* -- so a dominance test
    is right not to fail on it. The gap is real slack in a deliberately
    coarse stage-A bound, whose job is to eliminate most geometries cheaply
    rather than to be tight.

    The consequence worth stating: dominance testing is a weak instrument
    for coarse bounds and a sharp one for tight bounds. The bounds where a
    wrongly-tightened value would actually bite -- stage B's 1,798 and the
    blank-penalty ceilings, both within a few points of the 1,786 they must
    not refute -- are guarded by the single-board checks in
    `test_tighten.py` and `test_blank_penalty.py`. That is where this
    project's two real bugs were caught, and this file does not replace
    those.
    """
    lex, cb, cap, by_len = tables
    broken = [[[v for v in row] for row in plane] for plane in cap]
    broken[0][7][8] = 10
    with pytest.raises(AssertionError, match='GEOMETRY CAP VIOLATED'):
        _check((lex, cb, broken, by_len), seed=0, budget=FAST_BUDGET / 2,
               start='game')


def test_the_generator_actually_makes_legal_boards(tables):
    """Guards against the vacuity that would make everything above pass:
    if the generator emitted nothing, or emitted positions the rules engine
    would reject, the dominance assertions would hold trivially."""
    lex = tables[0]
    seen = 0
    for grid_before, placements, res, horiz in random_plays(
            tables, seed=7, budget=FAST_BUDGET / 3):
        check_static_position(res.new_grid, lex)     # raises if illegal
        assert res.total > 0
        assert 1 <= len(placements) <= 7
        seen += 1
    assert seen >= 5, f'generator produced only {seen} plays'
