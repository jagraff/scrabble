"""Rack and bag feasibility for the constructed game (scrabble_max.racks).

These tests upgrade the reachability claim from "buildable by legal board
moves" to "playable in a legal game": they check that the move sequence
can be dealt to two alternating players and supplied from a legal shuffle.
"""

import os

import pytest

from scrabble_max.racks import (RACK, final_move_tiles, full_bag,
                                parse_reachability_log, schedule,
                                verify_witness)

pytestmark = pytest.mark.skipif(
    not os.path.exists('results/reachability.log'),
    reason='reachability log not present')


@pytest.fixture(scope='module')
def moves():
    seq = parse_reachability_log()
    seq.append(final_move_tiles())
    return seq


def test_bag_is_the_official_hundred_tiles():
    bag = full_bag()
    assert sum(bag.values()) == 100
    assert bag['?'] == 2


def test_sequence_is_the_expected_length(moves):
    assert len(moves) == 26          # 25 build-up moves plus the record play


def test_every_move_fits_in_a_rack(moves):
    assert all(1 <= sum(t.values()) <= RACK for t in moves)


def test_schedule_exists_and_verifies(moves):
    ok, wit = schedule(moves, log=lambda *a: None)
    assert ok, 'no rack/bag schedule found'
    verified, detail = verify_witness(moves, wit)
    assert verified, detail


def test_tile_accounting_closes(moves):
    """Played + held + remaining must be exactly the 100-tile set."""
    ok, wit = schedule(moves, log=lambda *a: None)
    assert ok
    verified, detail = verify_witness(moves, wit)
    assert verified
    assert 'in bag' in detail


def test_no_letter_exceeds_its_distribution(moves):
    from collections import Counter
    from scrabble_max.rules import DISTRIBUTION
    used = Counter()
    for t in moves:
        used += t
    assert used['?'] <= 2
    for ch, n in used.items():
        if ch != '?':
            assert n <= DISTRIBUTION[ch], f'{ch}: {n} > {DISTRIBUTION[ch]}'
