from itertools import combinations

import pytest

from scrabble_max import known
from scrabble_max.cstage import TW_COLS, solve_tableau, tw_occupancy
from scrabble_max.lexicon import load

LEX = load()


@pytest.mark.parametrize('mask', [c for k in range(4)
                                  for c in combinations(TW_COLS, k)])
def test_tw_mask_pins_every_triple_word_column(mask):
    """The score reads the word multiplier off the mask's length, so the
    unnamed TW columns must be forced empty rather than left free. A
    solution covering an unmultiplied TW square would be scored below its
    true value, and this model eliminates by failing to reach a threshold
    -- so under-scoring can discard a legal record-beating board."""
    occ = tw_occupancy(mask)
    assert set(occ) == set(TW_COLS), 'every TW column must be constrained'
    assert all(occ[c] == 1 for c in mask)
    assert all(occ[c] == 0 for c in TW_COLS if c not in mask)


@pytest.mark.parametrize('mask', [c for k in range(4)
                                  for c in combinations(TW_COLS, k)])
def test_word_multiplier_matches_the_pinned_occupancy(mask):
    """`WM = 3 ** len(tw_placed)` is only the true multiplier because the
    occupancy above is exact; this ties the two together so they cannot
    drift apart."""
    occ = tw_occupancy(mask)
    assert 3 ** len(mask) == 3 ** sum(occ.values())


def test_non_tw_column_is_rejected():
    with pytest.raises(ValueError, match='triple-word'):
        tw_occupancy((0, 5))


# --- the TW mask and fix_placed_exact must agree -------------------------
#
# Both pin `placed`. If they disagree on a column the model is infeasible by
# contradiction rather than by refutation, and the caller reads INFEASIBLE
# as "no legal board realises this configuration above the threshold" -- so
# a configuration that might genuinely beat the record is discarded with no
# Scrabble content in the reasoning. Silent, and in the unsound direction.

@pytest.mark.parametrize('placed', [
    (0, 1, 3, 7, 11, 13),           # 14 missing
    (1, 3, 7, 11, 13, 14),          # 0 missing
    (0, 1, 3, 11, 13, 14),          # 7 missing
])
def test_a_configuration_missing_a_triple_word_column_is_refused(placed):
    """Rather than silently returning INFEASIBLE."""
    with pytest.raises(ValueError, match='pinned both ways'):
        solve_tableau(LEX, 'OXYPHENBUTAZONE', 0,
                      fix_placed_exact=set(placed), build_only=True,
                      log=lambda s: None)


def test_a_partial_mask_conflicting_the_other_way_is_refused():
    """The mirror case, introduced by making the mask exact: an unnamed TW
    column is forced empty, so a configuration that places it conflicts."""
    with pytest.raises(ValueError, match='pinned both ways'):
        solve_tableau(LEX, 'OXYPHENBUTAZONE', 0, tw_placed=(0, 7),
                      fix_placed_exact={0, 1, 3, 7, 11, 13, 14},
                      build_only=True, log=lambda s: None)


def test_a_consistent_configuration_is_accepted():
    """The guard must not reject the configurations the pipeline actually
    checks, or every tier-3 refutation becomes an exception."""
    m, g = solve_tableau(LEX, 'OXYPHENBUTAZONE', 0,
                         fix_placed_exact={0, 1, 3, 6, 7, 11, 14},
                         build_only=True, log=lambda s: None)
    assert m is not None and g


def test_a_consistent_partial_mask_is_accepted():
    m, g = solve_tableau(LEX, 'OXYPHENBUTAZONE', 0, tw_placed=(0, 7),
                         fix_placed_exact={0, 1, 3, 7, 11, 13},
                         build_only=True, log=lambda s: None)
    assert m is not None and g


@pytest.mark.slow
def test_tableau_model_reproduces_1786_when_fixed():
    """With the whole grid fixed to the known construction, the tableau
    model must be feasible and evaluate to exactly 1786 — validating the
    automata, connectivity flow, inventory and scoring in one shot."""
    name, val, bound, sol = solve_tableau(
        LEX, 'OXYPHENBUTAZONE', 0, time_limit=600,
        hint_grid=known.pre_board(), hint_placed={0, 1, 3, 6, 7, 11, 14},
        fix_hint=True, log=lambda s: None)
    assert name == 'OPTIMAL'
    assert val == 1786
