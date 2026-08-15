"""The in-model blank penalty (tighten_candidate blank_penalty=True).

The relaxation charges a blank only its face value, which under-states
what it forfeits. The penalty adds a *lower bound* on the shortfall, so
the objective stays an upper bound on the true score and Lemma 1 still
applies.

Two things can go wrong, and both would be silent:

  * the penalty over-charges, pushing a bound below a score that is
    actually achievable -- which would refute a real play;
  * the penalty is wired backwards and *raises* a bound, which would mean
    the tightening is not a tightening at all.

The first is checked against the one play whose score is known for
certain: the 1,786 construction itself.
"""

import json
import os

import pytest

from scrabble_max import known
from scrabble_max import tighten as T
from scrabble_max.lexicon import load

WORD = 'OXYPHENBUTAZONE'
KNOWN_PLACED = tuple(sorted(c for (_, c) in known.MOVE.placements))


@pytest.fixture(scope='module')
def ctx():
    lex = load()
    return (lex,
            {(c, 0): T.cross_options(lex, c, 0) for c in set(WORD)},
            T.adjacent_pairs(lex),
            T.build_line_dawg(lex))


def _bound(ctx, S, penalty):
    lex, opts, adj, dawg = ctx
    (b, _), _ = T.tighten_candidate(
        lex, WORD, 0, opts_cache=opts, adj_pairs=adj, row1_exact=True,
        dawg=dawg, mask_filter=[7], pairwise_all_rows=True,
        fix_placed=set(S), time_limit=600.0, blank_penalty=penalty,
        log=lambda s: None)
    return b


@pytest.mark.slow
def test_penalty_does_not_refute_the_record(ctx):
    """The record play scores 1,786 and its placed set is one of the 14.
    A bound below 1,786 for that pattern would be refuting a play that
    demonstrably exists -- the sharpest available soundness check."""
    b = _bound(ctx, KNOWN_PLACED, penalty=True)
    assert b >= known.EXPECTED_SCORE, (
        f'penalty bounds the record play at {b} < {known.EXPECTED_SCORE}; '
        f'it over-charges and is unsound')


@pytest.mark.slow
def test_penalty_only_tightens(ctx):
    """A tightening may lower a bound, never raise it."""
    for S in [(0, 2, 3, 7, 11, 13, 14), KNOWN_PLACED]:
        assert _bound(ctx, S, penalty=True) <= _bound(ctx, S, penalty=False)


@pytest.mark.skipif(not os.path.exists('results/blank_penalty_tier2.json'),
                    reason='penalty sweep not present')
def test_recorded_sweep_never_raised_a_bound():
    """Cheap guard over the whole recorded sweep, no solver needed."""
    rows = json.load(open('results/blank_penalty_tier2.json'))
    assert rows, 'sweep file is empty'
    risen = [r for r in rows if r['new'] > r['old']]
    assert not risen, f'{len(risen)} bounds rose: {risen[:3]}'


@pytest.mark.skipif(not os.path.exists('results/blank_penalty_tier2.json'),
                    reason='penalty sweep not present')
def test_recorded_sweep_keeps_the_record_pattern_alive():
    rows = {tuple(r['placed']): r for r in
            json.load(open('results/blank_penalty_tier2.json'))}
    assert KNOWN_PLACED in rows, 'the record pattern must be in the sweep'
    assert not rows[KNOWN_PLACED]['dies']
    assert rows[KNOWN_PLACED]['new'] >= known.EXPECTED_SCORE
