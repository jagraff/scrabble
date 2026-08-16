"""The blank-penalty sweep entry point.

`results/blank_penalty_tier2.json` selects which patterns tier 3 enumerates,
and it had no command that could regenerate it -- so the step that chose the
work was the one step of the chain a clean re-run could not reproduce.

The directional checks are the point of the module: a tightening that raised
a bound, or one that pushed the record play's own pattern below 1,786, would
be unsound rather than merely surprising. Those run without the solver.
"""

import json
import os

import pytest

from scrabble_max.blank_tier2 import KNOWN_PLACED, check, survivors

HAVE = os.path.exists('results/blank_penalty_tier2.json')
HAVE_SURVIVORS = os.path.exists('results/pattern_row1.json')


@pytest.fixture
def rows():
    with open('results/blank_penalty_tier2.json') as f:
        return json.load(f)


@pytest.mark.skipif(not HAVE_SURVIVORS, reason='tier-2 output not present')
@pytest.mark.skipif(not HAVE, reason='sweep not present')
def test_survivors_match_the_recorded_sweep(rows):
    """The sweep must cover exactly the patterns tier 2 kept. Fewer means a
    pattern goes to tier 3 unswept; more means it swept something tier 2
    had already eliminated."""
    assert set(survivors()) == {tuple(r['placed']) for r in rows}


@pytest.mark.skipif(not HAVE, reason='sweep not present')
def test_committed_sweep_passes_its_own_directional_checks(rows):
    assert check(rows) == []


def test_a_risen_bound_is_rejected():
    """A tightening may lower a bound, never raise it."""
    bad = [{'placed': list(KNOWN_PLACED), 'old': 1790.0, 'new': 1791.0,
            'dies': False}]
    problems = check(bad)
    assert any('ROSE' in p for p in problems)


def test_refuting_the_record_play_is_rejected():
    """The sharpest available soundness check: the record pattern scores
    1,786, so a bound below that is refuting a play that exists."""
    bad = [{'placed': list(KNOWN_PLACED), 'old': 1790.0, 'new': 1780.0,
            'dies': True}]
    problems = check(bad)
    assert any('refutes a play that exists' in p for p in problems)


def test_the_record_pattern_must_be_present():
    problems = check([{'placed': [0, 1, 2, 3, 4, 5, 6], 'old': 1.0,
                       'new': 1.0, 'dies': True}])
    assert any('not in the sweep' in p for p in problems)


def test_the_record_pattern_may_not_be_marked_dead():
    bad = [{'placed': list(KNOWN_PLACED), 'old': 1791.0, 'new': 1791.0,
            'dies': True}]
    assert any('marked dead' in p for p in check(bad))
