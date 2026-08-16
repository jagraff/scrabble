"""Cell-splitting refutation (scrabble_max.decompose).

The entire method rests on one property: the option set for a pinned cell
must be **exhaustive**. Every legal board puts *something* in that cell, so
refuting every option refutes the configuration -- but only if no legal
value was left out of the list. A partition that misses one value would
still report "all branches refuted", and the conclusion would be false.

The specific trap, hit for real while writing this: narrowing a cell's
letters to those with tiles still spare. A blank can stand in for a letter
with no copies left, so a spare-based option set is not exhaustive.
"""

import pytest

from scrabble_max.decompose import (LETTERS, pivot_candidates, sound_options)
from scrabble_max.lexicon import load
from scrabble_max.rules import DISTRIBUTION, N
from scrabble_max.tighten import second_letters

WORD = 'OXYPHENBUTAZONE'
CROSSES = {0: 'OPACIFICATIONS', 1: 'XEROSES', 3: 'PREADJUSTING',
           7: 'BRAINWASHING', 10: 'AMELIORATIVE', 11: 'ZOOGAMETE',
           14: 'EQUALITY'}


@pytest.fixture(scope='module')
def lex():
    return load()


def test_row_one_options_are_every_legal_continuation(lex):
    """The vertical run starts at row 0, so the row-1 letter must be able
    to follow the row-0 letter in some word -- and every such letter must
    be offered, because a blank can supply any of them."""
    for c in (2, 4, 5, 6, 8, 9, 12, 13):
        opts = sound_options(lex, WORD, 1, c, CROSSES)
        assert opts[0] is None, 'the empty cell must be an option'
        assert set(opts[1:]) == set(second_letters(lex, WORD[c], 0))


def test_options_are_not_narrowed_by_tile_availability(lex):
    """A blank can supply a letter with no copies left, so any option set
    filtered by spare tiles would not be exhaustive. This pins the bug
    that was actually written first."""
    import collections
    use = collections.Counter(WORD)
    for w in CROSSES.values():
        use.update(w[1:])
    exhausted = {ch for ch in LETTERS
                 if use.get(ch, 0) >= DISTRIBUTION[ch]}
    assert exhausted, 'setup: this configuration must exhaust some letter'
    offered = set()
    for c in (2, 4, 5, 6, 8, 9, 12, 13):
        offered |= set(sound_options(lex, WORD, 1, c, CROSSES)[1:])
    assert offered & exhausted, (
        'options must still offer letters whose tiles are used up; a blank '
        'can supply them')


def test_deep_cells_offer_every_letter(lex):
    """Below row 1 there is no row-0 letter constraining the cell, so the
    only sound option set is everything."""
    opts = sound_options(lex, WORD, 5, 5, CROSSES)
    assert opts[0] is None and set(opts[1:]) == set(LETTERS)


def test_cells_inside_a_pinned_cross_word_are_not_pivots(lex):
    """They are already determined, so splitting on them would multiply
    branches without constraining anything."""
    assert sound_options(lex, WORD, 1, 0, CROSSES) is None
    assert sound_options(lex, WORD, 3, 7, CROSSES) is None


def test_row_zero_is_never_a_pivot(lex):
    assert sound_options(lex, WORD, 0, 4, CROSSES) is None


def test_pivots_are_ordered_narrowest_first(lex):
    piv = pivot_candidates(lex, WORD, CROSSES)
    sizes = [len(sound_options(lex, WORD, r, c, CROSSES)) for r, c in piv]
    assert sizes == sorted(sizes)
    assert all(s > 1 for s in sizes), 'a one-option cell is not a split'


def test_every_pivot_is_a_real_board_cell(lex):
    for r, c in pivot_candidates(lex, WORD, CROSSES):
        assert 1 <= r < N and 0 <= c < N
