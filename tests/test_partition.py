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
