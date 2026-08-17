"""The invariant that keeps `solve_tableau`'s TW handling safe.

`solve_tableau(tw_placed=...)` pins the three triple-word columns exactly:
those named are occupied, those unnamed are empty. `fix_placed_exact` pins
every column. If a caller ever combines a configuration whose placed set
omits a triple-word column with the default full mask, the two constraints
contradict and the model is infeasible for that reason alone -- a silent
false refutation, since the caller reads INFEASIBLE as "no board realises
this configuration above the threshold".

The contradiction predates the exactness change (the old code already
forced the named columns occupied), and it cannot arise today: Theorem 3
proves a record-beating play covers all three triple-word squares, so every
pattern that reaches tier 3 contains columns 0, 7 and 14, and so does every
configuration built from one.

This pins that. A runtime assertion inside `cstage.py` would be the more
direct guard, and is deliberately not used: `cstage.py` is one of the six
modules whose text determines the checkpoint identity, so touching it
invalidates 50 identity-bound cells and 18.7 hours of solver time, and
leaves the certified manifest pointing at a commit whose model sources
differ from HEAD -- the provenance drift the identity work exists to
prevent. The invariant is enforced here instead, where enforcing it costs
nothing, and `results/soundness_remediation.md` records the assertion as
the right change to batch into the next model-touching run.
"""

import json
import os

import pytest

TW_COLS = {0, 7, 14}
CONFIGS = 'results/tier3_configs.json'
SURVIVORS = 'results/blank_penalty_tier2.json'


@pytest.mark.skipif(not os.path.exists(CONFIGS), reason='tier 3 not run')
def test_every_tier3_pattern_covers_all_three_triple_words():
    with open(CONFIGS) as f:
        payload = json.load(f)
    assert payload['patterns'], 'no patterns: this test would prove nothing'
    for p in payload['patterns']:
        assert TW_COLS <= set(p['placed']), (
            f"pattern {tuple(p['placed'])} omits a triple-word column; "
            f'combined with the default tw_placed it would make the tableau '
            f'model infeasible by contradiction rather than by refutation')


@pytest.mark.skipif(not os.path.exists(CONFIGS), reason='tier 3 not run')
def test_every_enumerated_configuration_covers_all_three_triple_words():
    with open(CONFIGS) as f:
        payload = json.load(f)
    n = 0
    for p in payload['patterns']:
        for c in p.get('configs') or []:
            n += 1
            assert TW_COLS <= set(c['placed']), (
                f"configuration on {sorted(c['placed'])} omits a triple-word "
                f'column')
    assert n > 0, 'no configurations examined; the check would be vacuous'


@pytest.mark.skipif(not os.path.exists(SURVIVORS), reason='sweep not run')
def test_every_surviving_pattern_covers_all_three_triple_words():
    """The same at the stage that selects tier-3's work, so a pattern
    violating it would be caught before any configuration is built."""
    with open(SURVIVORS) as f:
        rows = json.load(f)
    live = [r for r in rows if not r['dies']]
    assert live, 'no surviving patterns: this test would prove nothing'
    for r in live:
        assert TW_COLS <= set(r['placed']), (
            f"surviving pattern {tuple(r['placed'])} omits a triple-word "
            f'column')


def test_the_contradiction_is_real_when_the_invariant_breaks():
    """Not a hypothetical. Spelled out as arithmetic so the reason this
    matters survives even if `cstage` is refactored: the two constraint
    sets disagree on a column, and no board can satisfy both."""
    tw_placed = (0, 7, 14)
    placed_without_a_tw = {0, 1, 3, 7, 11, 13}          # 14 is missing
    forced_one = set(tw_placed)
    forced_zero = {c for c in range(15) if c not in placed_without_a_tw}
    assert forced_one & forced_zero == {14}, (
        'column 14 would be forced both occupied and empty')
