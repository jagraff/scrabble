"""The decomposition step tier 3 uses to close its last open case.

CP-SAT leaves a configuration or two UNDECIDED at any finite time limit, and
an undecided configuration is not a refuted one. `tier3` hands those to
`decompose.refute_parallel`, which is the step that used to be run by hand
and written up as prose.

These tests are about the wiring, not the mathematics: the decomposition
itself is exercised by the pipeline and by `results/tier3_results.md`. The
wiring is what broke -- `tier3` passed `log=lambda *x: None` while
`refute_parallel` logs with `flush=True`, so the call raised TypeError. That
crash would have landed after hours of solving, in the one step that closes
the proof, and nothing in the suite would have caught it beforehand.
"""

import pytest

from scrabble_max import decompose, tier3


def test_the_silent_logger_takes_the_calls_decompose_makes():
    """`refute_parallel` logs positionally and with flush=True. A
    positional-only lambda passes review and fails on the first call."""
    tier3._silent('a message')
    tier3._silent('a message', flush=True)
    tier3._silent('several', 'positional', flush=True, end='')


def test_a_positional_only_logger_would_have_failed():
    """Pins why `_silent` exists rather than an inline lambda, so nobody
    'simplifies' it back."""
    with pytest.raises(TypeError):
        (lambda *x: None)('a message', flush=True)


def test_tier3_passes_a_logger_that_survives_a_flushed_call(monkeypatch):
    """The regression test that matters: it checks the *call site*.

    An earlier version of this file tested `_silent` in isolation and
    tested that `refute_parallel` accepts a kwargs logger, and passed
    cleanly with the bug reintroduced -- because neither touched the
    argument `tier3` actually passes. Verified by mutation: putting
    `log=lambda *x: None` back must turn this red.
    """
    captured = {}

    def fake_refute(lex, placed, crosses, **kw):
        captured['log'] = kw['log']
        return True, []

    monkeypatch.setattr(decompose, 'refute_parallel', fake_refute)
    unresolved = [((0, 1, 3), {'config': {'placed': [0, 1, 3],
                                          'crosses': {'0': 'WORD'}}})]
    records, still = tier3.decompose_undecided(
        None, unresolved, threshold=1786, workers=1, time_limit=1.0,
        log=lambda *a, **k: None)

    assert records and records[0]['refuted'] is True and not still
    assert 'log' in captured, 'tier3 must pass a logger explicitly'
    # The exact call `refute_parallel` makes, on the exact object tier3
    # hands it. This is what raised TypeError after four hours of solving.
    captured['log']('depth 0: 1 solved, 1 refuted, 0 open', flush=True)


def test_refute_parallel_accepts_the_logger_tier3_passes(monkeypatch):
    """Drive the real `refute_parallel` control flow with the solver
    stubbed out, so every one of its logging call sites runs. Without the
    stub this needs minutes of CP-SAT; with it, milliseconds.
    """
    calls = []

    def fake_batch(args):
        # Real shape: (placed, crosses, threshold, nodes, budget), where
        # each node is {"r,c": letter}. Returns (fixed, status, value) per
        # node. Matching this exactly is the difference between exercising
        # the logging call sites and blowing up before reaching them.
        placed, crosses, threshold, nodes, budget = args
        return [(f, 'INFEASIBLE', None) for f in nodes]

    monkeypatch.setattr(decompose, '_solve_batch', fake_batch)
    monkeypatch.setattr(decompose, 'pivot_candidates',
                        lambda *a, **k: [(1, 4), (1, 6)])

    class Immediate:
        """Run submitted work inline: a process pool would not inherit the
        monkeypatched module in a spawned child."""

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            return [fn(i) for i in items]

        def submit(self, fn, *a, **k):
            class F:
                def __init__(self, v):
                    self._v = v

                def result(self):
                    return self._v
            return F(fn(*a, **k))

    monkeypatch.setattr('concurrent.futures.ProcessPoolExecutor', Immediate)

    def logger(*a, **k):
        calls.append((a, k))

    refuted, branches = decompose.refute_parallel(
        None, (0, 1, 3, 7, 10, 11, 14), {0: 'X'}, threshold=1786,
        workers=1, time_limit=1.0, max_depth=1, log=logger)

    # Not caught-and-ignored: an exception here is the failure, and letting
    # it propagate is the point. The first version of this test swallowed
    # every non-TypeError, and its stub did not match `_solve_batch`'s
    # argument shape -- so it raised AttributeError before reaching a single
    # log call and passed anyway. It made zero log calls and asserted
    # nothing, which is the failure mode this whole file is about.
    assert refuted is True, 'everything was stubbed INFEASIBLE'
    assert calls, 'no log calls were made; the logging contract went untested'
    assert any(k.get('flush') for _, k in calls), (
        'no flushed log line; the keyword call that broke tier3 was never '
        'exercised')
