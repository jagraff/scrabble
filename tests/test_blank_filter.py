"""The pre-tableau blank filter (finalize.config_ceiling).

The filter charges a configuration's blanks their true cost. Getting the
direction wrong makes it refute configurations that are not refutable, so
these tests pin the sign, the double-counting trap, the dependence on
which cells were actually placed, and agreement with the archived runs.
"""

import json
import os

import pytest

from scrabble_max.finalize import (blank_cost_gap, config_ceiling,
                                   exact_fixed_blank_loss,
                                   model_blank_charge)

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


def test_the_double_letter_only_counts_when_the_tile_is_placed():
    """A DL square doubles only a tile the mover *places*. Charging the
    doubled loss at an unplaced column over-states the loss, which lowers
    the ceiling and can refute a configuration that is not refutable.

    This needs a synthetic word, and the reason is worth recording: for
    OXYPHENBUTAZONE the bug is *inert*, because every main-word loss is
    at least 27x face value while every cross-remainder loss is at most
    3x, so the sorted pick never reaches a main-word entry -- verified
    across all 1903 archived configurations, where the old and fixed
    functions agree exactly. Nothing enforces that precondition, so pin
    the behaviour on a word that violates it.

    Here the only two J's sit at columns 3 and 11, the two DLs, so the
    main-word entry is the selected one: 8 x 2 x 27 placed against
    8 x 1 x 27 unplaced."""
    word = 'ABCJDEFGHIKJLMN'
    assert [i for i, ch in enumerate(word) if ch == 'J'] == [3, 11]
    assert exact_fixed_blank_loss(word, {0, 3, 7, 11, 14}, {}) == (1, 432)
    assert exact_fixed_blank_loss(word, {0, 7, 14}, {}) == (1, 216)


def test_ceiling_does_not_depend_on_the_charging_scale():
    """The whole point of recomputing: the same configuration must yield
    the same ceiling no matter what the enumeration charged for blanks.
    `blank_cost_gap` needs the scale, and passing the wrong one is the
    double-count -- the ceiling needs no such coordination."""
    cfg = {0: 'OPACIFICATIONS', 1: 'XEROSES', 2: 'YATAGHANS',
           3: 'PREQUALIFIED', 7: 'BLADDERLIKE', 11: 'ZOOGAMETE',
           14: 'EVOCATIVELY'}
    placed = {0, 1, 2, 3, 7, 11, 14}
    face = model_blank_charge(WORD, placed, cfg, blank_penalty=False)
    pen = model_blank_charge(WORD, placed, cfg, blank_penalty=True)
    assert pen > face, 'this configuration should exercise the penalty'
    # the two scales leave different residual gaps ...
    assert (blank_cost_gap(WORD, placed, cfg, blank_penalty=False)
            > blank_cost_gap(WORD, placed, cfg, blank_penalty=True))
    # ... but both reconstruct to the same ceiling.  A run on a given
    # scale records `raw_total - charge`; correcting that by the residual
    # gap for the *same* scale must land on the recomputed ceiling.
    exact = exact_fixed_blank_loss(WORD, placed, cfg)[1]
    ceiling = config_ceiling(WORD, placed, cfg)
    assert ceiling is not None
    raw_total = ceiling + exact
    for charge, bp in ((face, False), (pen, True)):
        recorded = raw_total - charge          # what that run would write
        gap = blank_cost_gap(WORD, placed, cfg, blank_penalty=bp)
        assert recorded - gap == ceiling
    # and the double-count: correcting a penalty-on score with the
    # penalty-off gap is exactly the bug, and under-shoots
    assert (raw_total - pen) - blank_cost_gap(
        WORD, placed, cfg, blank_penalty=False) < ceiling


def test_model_charge_never_exceeds_the_true_loss():
    """The charge must stay a lower bound on the true loss, or the model
    is over-charging and could refute a real play."""
    cfg = {0: 'OPACIFICATIONS', 1: 'XEROSES', 2: 'YATAGHANS',
           3: 'PREQUALIFIED', 7: 'BLADDERLIKE', 11: 'ZOOGAMETE',
           14: 'EVOCATIVELY'}
    placed = {0, 1, 2, 3, 7, 11, 14}
    exact = exact_fixed_blank_loss(WORD, placed, cfg)[1]
    for bp in (False, True):
        assert model_blank_charge(WORD, placed, cfg, blank_penalty=bp) <= exact


def test_cross_words_must_sit_at_placed_columns():
    """The model enforces `x <= placed`; a caller that violates it would
    silently get a wrong multiplier rather than an error."""
    with pytest.raises(AssertionError):
        config_ceiling(WORD, {0, 7}, {0: 'OPACIFICATIONS',
                                      14: 'EVOCATIVELY'})


@pytest.mark.skipif(
    not os.path.isdir('results/pre_fix/pattern_configs'),
    reason='archived configurations not present')
def test_filter_never_contradicts_an_archived_verdict():
    """Every archived configuration was refuted by the tableau. The filter
    may refute a subset of them, but must never claim a configuration
    survives that the tableau refuted -- and must never be applied to one
    the tableau found feasible (there are none).

    Also pins the two soundness directions across the whole archive: the
    model's charge stays a lower bound on the true loss on either scale,
    and the recomputed ceiling never falls below what the recorded-score
    correction gave (falling below would be a *new* refutation)."""
    d = 'results/pre_fix/pattern_configs'
    checked = killed = 0
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        for r in json.load(open(f'{d}/{fn}')):
            cfg = r['config']
            crosses = {int(a): b for a, b in dict(cfg['crosses']).items()}
            placed = set(cfg['placed'])
            checked += 1
            assert r['status'] == 'INFEASIBLE', 'archive should be all refuted'
            ceiling = config_ceiling(WORD, placed, crosses)
            fb = exact_fixed_blank_loss(WORD, placed, crosses)
            if fb is not None:
                for bp in (False, True):
                    assert model_blank_charge(
                        WORD, placed, crosses, blank_penalty=bp) <= fb[1]
            # the archive was enumerated with the penalty off
            gap = blank_cost_gap(WORD, placed, crosses, blank_penalty=False)
            if gap is not None:
                assert ceiling >= cfg['relaxed_score'] - gap
            if ceiling is not None and ceiling <= 1786:
                killed += 1
    assert checked > 1000
    # ~95% on the archived data; assert a floor so a regression is visible
    assert killed / checked > 0.9, f'filter killed only {killed}/{checked}'
