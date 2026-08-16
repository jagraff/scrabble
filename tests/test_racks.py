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


# --- tamper cases: a certificate is only as good as what it rejects ------
#
# Every case below starts from the genuine witness, changes one thing, and
# requires a rejection. A verifier that accepts these is not checking the
# rule it claims to check, and the schedule stops being evidence.

@pytest.fixture(scope='module')
def witness(moves):
    ok, wit = schedule(moves, log=lambda *a: None)
    assert ok
    return wit


def _tampered(wit, mutate):
    """A deep-enough copy of the witness with one field changed."""
    clone = {'opening': [dict(d) for d in wit['opening']],
             'moves': [dict(m, plays=dict(m['plays']),
                            drew_after=dict(m['drew_after']),
                            rack_after=dict(m['rack_after']))
                       for m in wit['moves']]}
    mutate(clone)
    return clone


def test_truncated_witness_is_rejected(moves, witness):
    bad = _tampered(witness, lambda w: w['moves'].pop())
    ok, detail = verify_witness(moves, bad)
    assert not ok, 'a short witness must not pass by pairwise comparison'
    assert '25 moves' in detail and '26' in detail


def test_extra_witness_move_is_rejected(moves, witness):
    bad = _tampered(witness, lambda w: w['moves'].append(w['moves'][-1]))
    ok, detail = verify_witness(moves, bad)
    assert not ok, 'a spurious trailing move must not be silently ignored'


def test_corrupted_rack_after_is_rejected(moves, witness):
    def mutate(w):
        w['moves'][5]['rack_after']['Q'] = 3
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok and 'rack_after' in detail


def test_corrupted_bag_left_is_rejected(moves, witness):
    def mutate(w):
        w['moves'][5]['bag_left'] = 99
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok and 'bag_left' in detail


def test_a_single_player_taking_every_move_is_rejected(moves, witness):
    """Rejected, though not by the alternation check: relabelling the
    movers without redealing leaves player 0 without the tiles. Kept
    because it is the obvious tamper, and the real one is below."""
    def mutate(w):
        for m in w['moves']:
            m['player'] = 0
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok


@pytest.mark.parametrize('swap_at', [0, 4, 11, 19])
def test_a_tile_feasible_alternation_break_is_rejected(moves, swap_at):
    """The real hole. A schedule where one player takes two turns in a row
    is *tile-feasible* -- the bag can supply it, so no rack or accounting
    check catches it -- and the verifier used to read the mover out of the
    record rather than derive it, so it passed. Sweeping all 25 adjacent
    swaps finds 24 such schedules; four are pinned here.

    This is what makes the schedule evidence for "two alternating players"
    rather than merely "two players".
    """
    owner = [i % 2 for i in range(len(moves))]
    owner[swap_at], owner[swap_at + 1] = owner[swap_at + 1], owner[swap_at]
    ok, wit = schedule(moves, log=lambda *a: None, owner=owner)
    assert ok, 'setup: this ownership must be tile-feasible to be a threat'
    verified, detail = verify_witness(moves, wit)
    assert not verified, 'a player taking two turns in a row must not pass'
    assert 'alternation' in detail


def test_skipping_the_refill_is_rejected(moves, witness):
    def mutate(w):
        w['moves'][3]['drew_after'] = {}
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok and 'refill' in detail


def test_short_opening_hand_is_rejected(moves, witness):
    def mutate(w):
        w['opening'][0].popitem()
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok and 'opening draw' in detail


def test_drawing_a_tile_the_bag_does_not_hold_is_rejected(moves, witness):
    def mutate(w):
        w['moves'][0]['drew_after'] = {'Q': sum(
            w['moves'][0]['drew_after'].values())}
    ok, detail = verify_witness(moves, _tampered(witness, mutate))
    assert not ok


# --- the board half -------------------------------------------------------

def test_replay_reaches_the_record_board_and_scores_1786():
    """`verify_witness` consumes tile counts, so it cannot see where the
    tiles went. This is the half that can."""
    from scrabble_max import known
    from scrabble_max.lexicon import load
    from scrabble_max.racks import full_sequence, verify_board_sequence

    target = dict(known.pre_board())
    target.update(known.MOVE.placements)
    ok, detail, scores = verify_board_sequence(full_sequence(), load(),
                                               target=target)
    assert ok, detail
    assert scores[-1] == known.EXPECTED_SCORE == 1786


def test_replay_rejects_a_moved_tile():
    """A schedule balancing the same tile counts on a different board must
    not pass as a certificate for this one."""
    from scrabble_max.lexicon import load
    from scrabble_max.racks import full_sequence, verify_board_sequence

    seq = full_sequence()
    victim = seq[0]
    cell, tile = sorted(victim.items())[0]
    moved = {c: t for c, t in victim.items() if c != cell}
    moved[(cell[0] + 3, cell[1] + 3)] = tile
    seq = [moved] + seq[1:]
    ok, detail, _ = verify_board_sequence(seq, load())
    assert not ok, 'a displaced tile must break the replay'


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
