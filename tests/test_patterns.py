"""Tests for the pattern-level completeness proof (scrabble_max.patterns).

The critical property is soundness of the filters: a relaxation that
excluded a play which genuinely scores 1786 would invalidate the whole
proof, so we check the filters against the known record play directly.
"""

import json
import os

import pytest

from scrabble_max import known
from scrabble_max.bounds import best_rest_table, cross_bound_table
from scrabble_max.lexicon import load
from scrabble_max.patterns import (RACK, WORD, pattern_bound,
                                   qualifying_patterns)

KNOWN_PLACED = tuple(sorted(c for (_, c) in known.MOVE.placements))


@pytest.fixture(scope='module')
def lexicon():
    return load()


def test_known_play_places_seven_tiles_on_the_top_row():
    assert all(r == 0 for (r, _) in known.MOVE.placements)
    assert len(KNOWN_PLACED) == RACK
    assert KNOWN_PLACED == (0, 1, 3, 6, 7, 11, 14)


def test_known_pattern_covers_all_three_triple_words():
    assert {0, 7, 14} <= set(KNOWN_PLACED)


def test_stage_a_bound_does_not_exclude_the_record_play(lexicon):
    """Soundness: the tier-1 relaxation must not rule out a pattern that
    actually achieves 1786, or the proof would be vacuous."""
    cb = cross_bound_table(best_rest_table(lexicon))
    assert pattern_bound(KNOWN_PLACED, cb=cb) >= known.EXPECTED_SCORE


def test_record_pattern_survives_tier_one(lexicon):
    pats, _ = qualifying_patterns(lexicon, threshold=known.EXPECTED_SCORE - 1)
    assert KNOWN_PLACED in {S for _, S in pats}


def test_pattern_counts_are_stable(lexicon):
    """495 = C(12,4): seven placed tiles, three of them pinned to the TWs."""
    pats, n_total = qualifying_patterns(lexicon,
                                        threshold=known.EXPECTED_SCORE)
    assert n_total == 495
    assert len(pats) == 165
    assert all(len(S) == RACK for _, S in pats)
    assert all({0, 7, 14} <= set(S) for _, S in pats)
    assert all(b > known.EXPECTED_SCORE for b, _ in pats)


def test_bounds_are_monotone_in_the_threshold(lexicon):
    lo, _ = qualifying_patterns(lexicon, threshold=1700)
    hi, _ = qualifying_patterns(lexicon, threshold=1900)
    assert {S for _, S in hi} <= {S for _, S in lo}


@pytest.mark.skipif(not os.path.exists('results/pattern_row1.json'),
                    reason='tier-2 results not present')
def test_tier_two_survivors_match_the_config_enumeration():
    """The row-1-exact filter and the (abandoned) per-config enumeration
    are independent routes to the same set of placed patterns."""
    import ast
    import re
    recs = json.load(open('results/pattern_row1.json'))
    kept = {tuple(r['placed']) for r in recs if r['kept']}
    enumerated = set()
    with open('results/configs.log') as f:
        for line in f:
            m = re.match(r'\s*config #\d+: \d+ placed=(\([^)]*\))', line)
            if m:
                enumerated.add(ast.literal_eval(m.group(1)))
    assert kept == enumerated
    assert KNOWN_PLACED in kept


@pytest.mark.skipif(not os.path.exists('results/pattern_proof_configs.json'),
                    reason='tier-3c results not present')
def test_per_pattern_enumeration_covers_the_global_one():
    """Every configuration the abandoned global enumeration found for a
    pattern must reappear in that pattern's own enumeration -- otherwise
    the per-pattern loop is missing cases and its completeness claim is
    worthless.  It should be a strict superset: the global loop never ran
    any single pattern to exhaustion."""
    import ast
    import re
    old = {}
    with open('results/configs.log') as f:
        for line in f:
            m = re.match(r'\s*config #\d+: \d+ placed=(\([^)]*\)) (\{.*\})',
                         line)
            if m:
                S = ast.literal_eval(m.group(1))
                crosses = {int(k): v
                           for k, v in ast.literal_eval(m.group(2)).items()}
                old.setdefault(S, set()).add(tuple(sorted(crosses.items())))

    checked = 0
    for rec in json.load(open('results/pattern_proof_configs.json')):
        S = tuple(rec['placed'])
        path = 'results/pattern_configs/%s.json' % ''.join(
            f'{c:02d}' for c in S)
        if not os.path.exists(path):
            continue
        new = set()
        for r in json.load(open(path)):
            cr = {int(k): v for k, v in dict(r['config']['crosses']).items()}
            new.add(tuple(sorted(cr.items())))
        assert old.get(S, set()) <= new, f'{S}: per-pattern list is missing '\
            f'{len(old[S] - new)} configs the global enumeration found'
        checked += 1
    assert checked, 'no per-pattern config files to compare'


@pytest.mark.skipif(not os.path.exists('results/pattern_row1.json'),
                    reason='tier-2 results not present')
def test_tier_two_only_eliminates_on_a_proven_bound():
    recs = json.load(open('results/pattern_row1.json'))
    for r in recs:
        if not r['kept']:
            assert r['infeasible'] or r['row1_bound'] is not None
