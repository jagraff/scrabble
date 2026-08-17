"""Partitioned enumeration (scrabble_max.partition).

Completeness is the whole point of the enumeration, so the property that
matters here is *covering*: every configuration must land in some cell.
A partition that is merely disjoint would quietly drop configurations and
still look tidy -- every cell would finish, nothing would collide, and the
final count would just be too small.

The cheap structural properties are tested without the solver. The one
test that actually establishes equivalence -- that the union over cells
equals the unpartitioned enumeration -- needs CP-SAT and is marked slow.
"""

import pytest

from scrabble_max.lexicon import load
from scrabble_max.partition import _key, choose_pivot, make_cells

PATTERN = (0, 2, 3, 7, 11, 13, 14)


def test_cells_cover_every_option_index():
    """The direction that loses configurations if it is wrong."""
    for n_options, n_blocks in [(100, 7), (1619, 24), (5, 5), (13, 1)]:
        cells = make_cells(n_options, n_blocks)
        blocks = [c for c in cells if c is not None]
        assert set().union(*blocks) == set(range(n_options))


def test_cells_are_disjoint():
    for n_options, n_blocks in [(100, 7), (1619, 24), (5, 5)]:
        blocks = [c for c in make_cells(n_options, n_blocks) if c is not None]
        assert sum(len(b) for b in blocks) == n_options


def test_there_is_exactly_one_no_cross_cell():
    """A configuration giving the pivot no cross word satisfies no
    `sum(x) == 1` block, so it needs a cell of its own or it is lost."""
    cells = make_cells(50, 8)
    assert cells.count(None) == 1


def test_more_blocks_than_options_does_not_produce_empty_cells():
    """An empty block would be a cell whose only work is a closing
    infeasibility proof -- wasted, though not unsound."""
    cells = make_cells(3, 24)
    assert all(len(b) > 0 for b in cells if b is not None)


def test_round_robin_spreads_adjacent_options():
    """Contiguous blocks would concentrate the high-scoring options, and
    with them nearly all the configurations, into a few cells."""
    blocks = [c for c in make_cells(100, 10) if c is not None]
    assert all(len(b) == 10 for b in blocks)
    assert {0, 10, 20} <= blocks[0]


def test_cell_checkpoints_of_different_patterns_do_not_collide():
    """Column 3 is placed in all ten survivors and has the widest option
    list, so it is the pivot for most of them. Naming a checkpoint by
    pivot and cell index alone would make two patterns share files, and
    the resume path would start one pattern from another's configurations
    and honour a completion marker that was not its own."""
    from scrabble_max.partition import _cell_tag
    a = _cell_tag((0, 2, 3, 7, 11, 13, 14), 3, 5)
    b = _cell_tag((0, 1, 3, 7, 10, 11, 14), 3, 5)
    assert a != b


def test_pivot_is_a_placed_column_with_options():
    lex = load()
    pivot, n = choose_pivot(lex, PATTERN)
    assert pivot in PATTERN, 'an unplaced pivot has no options to split on'
    assert n > 1, 'a pivot with one option cannot be partitioned'


@pytest.mark.slow
def test_union_of_cells_equals_the_unpartitioned_enumeration():
    """The equivalence the parallel run depends on."""
    from scrabble_max.finalize import enumerate_configs
    from scrabble_max.partition import enumerate_pattern

    lex = load()
    whole, complete = enumerate_configs(
        lex, fix_placed=set(PATTERN), threshold=1786, checkpoint_path=None,
        workers=1, log=lambda *a, **k: None)
    assert complete, 'baseline enumeration did not finish'

    parts, pcomplete = enumerate_pattern(
        PATTERN, n_blocks=6, max_workers=3, ckpt_dir=None,
        log=lambda *a, **k: None)
    assert pcomplete, 'some cell did not finish'
    assert {_key(c) for c in parts} == {_key(c) for c in whole}


# --- product partitioning ------------------------------------------------
#
# Splitting on one column balances badly: the surviving configurations can
# concentrate on a handful of that column's options, and because the blocks
# partition option *indices*, every configuration sharing an option shares a
# cell however finely the indices are split. Measured on
# (0,1,3,7,10,11,14): column 3 offers 1,619 options, the 623 survivors use
# 15 of them, and 334 use one. That cell took 11.0 h of solver time on one
# core while three sat idle.

def test_product_cells_cover_every_combination():
    """Covering is the half completeness depends on."""
    from scrabble_max.partition import make_product_cells
    cells = make_product_cells([(3, 6), (10, 4)], n_blocks=2)
    seen = set()
    for cell in cells:
        cols = tuple(c for c, _ in cell)
        assert cols == (3, 10), 'every cell constrains every pivot'
        seen.add(tuple((c, None if b is None else tuple(sorted(b)))
                       for c, b in cell))
    assert len(seen) == len(cells), 'cells must be distinct'
    # (no-cross + 2 blocks) on each of two columns
    assert len(cells) == 3 * 3


def test_every_option_pair_lands_in_exactly_one_cell():
    """Disjointness and coverage together, checked by construction over
    every possible (option at pivot A, option at pivot B) choice including
    the no-cross-word case on either."""
    from scrabble_max.partition import make_product_cells
    n_a, n_b, blocks = 7, 5, 3
    cells = make_product_cells([(3, n_a), (10, n_b)], n_blocks=blocks)

    def lands(cell, choice_a, choice_b):
        for col, block in cell:
            choice = choice_a if col == 3 else choice_b
            if block is None:
                if choice is not None:
                    return False
            else:
                if choice is None or choice not in block:
                    return False
        return True

    for a in [None] + list(range(n_a)):
        for b in [None] + list(range(n_b)):
            hits = [i for i, cell in enumerate(cells) if lands(cell, a, b)]
            assert len(hits) == 1, (
                f'choice (a={a}, b={b}) lands in {len(hits)} cells, not one')


def test_a_clump_on_one_pivot_is_broken_by_the_other():
    """The actual failure. Every configuration shares one option at the
    first pivot -- the PREQUALIFIED case -- and they must still be spread
    across cells by the second."""
    from scrabble_max.partition import make_product_cells
    cells = make_product_cells([(3, 8), (10, 8)], n_blocks=4)
    clumped_option = 2                      # all configurations use this one
    spread = set()
    for other in range(8):
        for i, cell in enumerate(cells):
            ok = True
            for col, block in cell:
                choice = clumped_option if col == 3 else other
                if block is None or choice not in block:
                    ok = False
                    break
            if ok:
                spread.add(i)
    assert len(spread) == 4, (
        f'configurations sharing one option at pivot 3 landed in '
        f'{len(spread)} cells; with a single pivot they would all share one')


def test_choose_pivots_returns_the_widest_columns_in_order():
    from scrabble_max.lexicon import load
    from scrabble_max.partition import choose_pivots
    pivots = choose_pivots(load(), PATTERN, k=3)
    counts = [n for _, n in pivots]
    assert counts == sorted(counts, reverse=True), 'widest first'
    assert len(pivots) == 3
    assert all(c in PATTERN for c, _ in pivots), 'pivots must be placed'
    assert all(n > 0 for _, n in pivots), 'a pivot needs options to split'


def test_choose_pivots_picks_more_than_one_column():
    """The whole point: one column is not enough."""
    from scrabble_max.lexicon import load
    from scrabble_max.partition import DEFAULT_PIVOTS, choose_pivots
    pivots = choose_pivots(load(), PATTERN)
    assert len(pivots) == DEFAULT_PIVOTS >= 2
    assert len({c for c, _ in pivots}) == len(pivots), 'distinct columns'


def test_cell_tags_of_different_product_cells_do_not_collide():
    from scrabble_max.partition import _cell_tag
    tags = {_cell_tag(PATTERN, [3, 10], i) for i in range(25)}
    assert len(tags) == 25
    assert _cell_tag(PATTERN, [3, 10], 0) != _cell_tag(PATTERN, [10, 3], 0)
    assert _cell_tag(PATTERN, 3, 0) != _cell_tag(PATTERN, [3, 10], 0)


def test_normalise_partition_accepts_both_shapes():
    from scrabble_max.tighten import normalise_partition
    assert normalise_partition(None) == []
    assert normalise_partition((3, {1, 2})) == [(3, {1, 2})]
    assert normalise_partition(((3, {1, 2}),)) == [(3, {1, 2})]
    assert normalise_partition(((3, {1}), (10, None))) == [(3, {1}),
                                                           (10, None)]
    assert normalise_partition((3, None)) == [(3, None)], (
        'a bare pair whose block is None is still one pair, not a sequence')
