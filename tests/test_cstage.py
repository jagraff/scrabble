import pytest

from scrabble_max import known
from scrabble_max.cstage import solve_tableau
from scrabble_max.lexicon import load

LEX = load()


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
