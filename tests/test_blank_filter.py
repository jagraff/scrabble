"""The pre-tableau blank filter (finalize.blank_cost_gap).

The filter subtracts the excess of a configuration's true blank cost over
the face value the relaxation charges. Getting the direction wrong makes
it refute configurations that are not refutable, so these tests pin the
sign, the double-counting trap, and agreement with the archived runs.
"""

import json
import os

import pytest

from scrabble_max.finalize import blank_cost_gap, exact_fixed_blank_loss

WORD = 'OXYPHENBUTAZONE'


def test_gap_is_never_negative():
    """True cost is at least face value, so the excess cannot be negative.
    A negative gap would *raise* the bound and break soundness."""
    cfg = {0: 'OPACIFICATIONS', 1: 'XEROSES', 3: 'PREQUALIFYING',
           7: 'BLADDERLIKE', 10: 'AMENORRHEA', 11: 'ZOOGAMETE',
           14: 'EJACULATING'}
    gap = blank_cost_gap(WORD, {0, 1, 3, 7, 10, 11, 14}, cfg)
    assert gap is None or gap >= 0


def test_gap_is_strictly_less_than_the_whole_loss():
    """The trap: subtracting the whole exact loss double-counts the face
    value the relaxation already charged."""
    cfg = {0: 'OPACIFICATIONS', 1: 'XEROSES', 3: 'PREQUALIFYING',
           7: 'BLADDERLIKE', 10: 'AMENORRHEA', 11: 'ZOOGAMETE',
           14: 'EJACULATING'}
    placed = {0, 1, 3, 7, 10, 11, 14}
    fb = exact_fixed_blank_loss(WORD, placed, cfg)
    gap = blank_cost_gap(WORD, placed, cfg)
    if fb is None:
        assert gap is None
    else:
        _, exact = fb
        assert gap <= exact
        if exact > 0:
            assert gap < exact, 'gap must exclude the face value charged'


def test_no_blanks_means_no_gap():
    """A configuration needing no blanks cannot be tightened by this."""
    cfg = {0: 'OPACIFICATIONS', 2: 'YARROWS', 3: 'PREQUALIFIED',
           7: 'BRAINWASHING', 10: 'ABRIDGED', 11: 'ZOOGAMETES',
           14: 'EVOCATIVELY'}
    placed = {0, 2, 3, 7, 10, 11, 14}
    fb = exact_fixed_blank_loss(WORD, placed, cfg)
    if fb is not None and fb[0] == 0:
        assert blank_cost_gap(WORD, placed, cfg) == 0


def test_more_than_two_blanks_is_none():
    """Agrees with exact_fixed_blank_loss on the impossible case."""
    cfg = {0: 'OXYPHENBUTAZONE', 7: 'OXYPHENBUTAZONE',
           14: 'OXYPHENBUTAZONE'}
    assert blank_cost_gap(WORD, {0, 7, 14}, cfg) is None


@pytest.mark.skipif(
    not os.path.isdir('results/pre_fix/pattern_configs'),
    reason='archived configurations not present')
def test_filter_never_contradicts_an_archived_verdict():
    """Every archived configuration was refuted by the tableau. The filter
    may refute a subset of them, but must never claim a configuration
    survives that the tableau refuted -- and must never be applied to one
    the tableau found feasible (there are none)."""
    d = 'results/pre_fix/pattern_configs'
    checked = killed = 0
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        for r in json.load(open(f'{d}/{fn}')):
            cfg = r['config']
            crosses = {int(a): b for a, b in dict(cfg['crosses']).items()}
            placed = set(cfg['placed'])
            gap = blank_cost_gap(WORD, placed, crosses)
            checked += 1
            assert r['status'] == 'INFEASIBLE', 'archive should be all refuted'
            if gap is not None and cfg['relaxed_score'] - gap <= 1786:
                killed += 1
    assert checked > 1000
    # ~95% on the archived data; assert a floor so a regression is visible
    assert killed / checked > 0.9, f'filter killed only {killed}/{checked}'
