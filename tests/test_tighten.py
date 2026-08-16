import pytest

from scrabble_max.lexicon import load
from scrabble_max.tighten import adjacent_pairs, cross_options, tighten_candidate

LEX = load()


def test_cross_options_hook_validity():
    # every option's remainder of length >= 2 must itself be a word
    for ch in ('O', 'B', 'Z', 'E'):
        for raw_rest, rest_len, counts, example, inward in cross_options(LEX, ch, 0):
            rest = example[1:]
            assert example[0] == ch
            assert example in LEX
            if len(rest) >= 2:
                assert rest in LEX, (example, rest)


def test_cross_options_row14_hooks_at_end():
    for raw_rest, rest_len, counts, example, inward in cross_options(LEX, 'Q', 14):
        assert example[-1] == 'Q'
        if len(example) >= 3:
            assert example[:-1] in LEX


def test_known_hooks_present():
    # the hooks used in the 1786 construction must appear as options
    def rests(ch, row):
        return {ex for _, _, _, ex, _ in cross_options(LEX, ch, row)}
    assert 'OPACIFICATIONS' in rests('O', 0)
    assert 'BLADDERLIKE' in rests('B', 0)
    assert 'NARROWING' in rests('N', 0)
    assert 'ZOOGAMETE' in rests('Z', 0)
    assert 'ESTABLISHMENTS' in rests('E', 0)
    assert 'PREQUALIFYING' in rests('P', 0)
    assert 'XED' in rests('X', 0)


def test_non_hook_words_excluded():
    # OXYPHENBUTAZONE is not a valid O-hook: XYPHENBUTAZONE is not a word
    assert all(ex != 'OXYPHENBUTAZONE'
               for _, _, _, ex, _ in cross_options(LEX, 'O', 0))


def test_adjacent_pairs():
    pairs = adjacent_pairs(LEX)
    assert ('Q', 'U') in pairs
    assert ('Z', 'Z') in pairs  # PIZZA
    assert ('Q', 'X') not in pairs
    assert ('X', 'Z') not in pairs


@pytest.mark.slow
def test_every_per_mask_bound_records_how_it_was_reached():
    """A per-mask cell can be a proved optimum or a timeout-derived
    `BestObjectiveBound`. Both are valid upper bounds, but only the first
    reproduces exactly across solver versions, and until now only the
    winning mask's status was written down -- so a rerun disagreeing on a
    cell could not be told from a bug.

    Theorem 3 rests on these cells, which is why the distinction has to be
    on disk rather than inferable."""
    status = {}
    (bound, _), per_mask = tighten_candidate(
        LEX, 'OXYPHENBUTAZONE', 0, time_limit=120.0, status_out=status)
    assert set(status) == set(per_mask), 'every cell must record a status'
    assert set(status.values()) <= {'OPTIMAL', 'BOUND', 'INFEASIBLE'}
    for mask, st in status.items():
        if st == 'INFEASIBLE':
            assert per_mask[mask] == float('-inf')
        else:
            assert per_mask[mask] > float('-inf')


@pytest.mark.slow
def test_tight_bound_dominates_known_1786():
    # The real 1786 play satisfies every stage-B constraint, so the stage-B
    # optimum for (OXYPHENBUTAZONE, row 0) must be >= 1786.
    (bound, detail), per_mask = tighten_candidate(LEX, 'OXYPHENBUTAZONE', 0,
                                                  time_limit=120.0)
    assert bound >= 1786


# --- regression: the unsound multiset deduplication in cross_options ---
#
# cross_options once keyed its options by the *multiset* of letters in the
# remainder, keeping one representative per anagram class.  Callers read
# the representative's ordered letters (rest_letter_at_depth for the
# adjacency constraints, o[4] for the row-1 inward letter), so the merge
# silently deleted legal cross-word choices from the relaxation and broke
# the "every legal play satisfies these constraints" property Lemma 1
# needs.  It was also nondeterministic: the lexicon is a frozenset, so
# which representative survived depended on PYTHONHASHSEED.

ANAGRAM_HOOK_CASES = [
    # (hook letter, row, two valid cross words, differing inward letters)
    ('Y', 0, 'YARE', 'YEAR'),
    ('E', 0, 'EARS', 'ERAS'),
]


@pytest.mark.parametrize('ch,row,w1,w2', ANAGRAM_HOOK_CASES)
def test_order_distinct_anagram_hooks_both_retained(ch, row, w1, w2):
    """Anagram cross words must not be collapsed into one option."""
    assert w1 in LEX and w2 in LEX
    opts = cross_options(LEX, ch, row)
    words = {o[3] for o in opts}
    assert w1 in words and w2 in words, (
        f'{w1}/{w2} are order-distinct options with the same remainder '
        f'multiset; both must survive')
    inward = {o[3]: o[4] for o in opts}
    assert inward[w1] != inward[w2], (
        'this case only guards the bug if the inward letters differ')


def test_cross_options_never_merges_order_distinct_options():
    """No two distinct valid cross words may share an option entry.

    Stronger than the cases above: whatever key cross_options uses, it
    must not merge options whose ordered letters are later inspected.
    Equivalently, every valid cross word appears as its own option.
    """
    from scrabble_max.tighten import N, word_playable
    for ch in ('A', 'E', 'O', 'Y', 'S', 'T'):
        for row in (0, 14):
            expected = set()
            for w in LEX:
                if len(w) < 2 or len(w) > N or not word_playable(w):
                    continue
                if (w[0] if row == 0 else w[-1]) != ch:
                    continue
                rest = w[1:] if row == 0 else w[:-1]
                if len(rest) >= 2 and rest not in LEX:
                    continue
                expected.add(w)
            got = {o[3] for o in cross_options(LEX, ch, row)}
            assert got == expected, (
                f'{ch} row {row}: {len(expected - got)} valid cross words '
                f'missing from the options, e.g. '
                f'{sorted(expected - got)[:5]}')


def test_cross_options_is_deterministic():
    """The option list must not depend on set iteration order."""
    import json
    import subprocess
    import sys

    prog = (
        'import json;'
        'from scrabble_max.lexicon import load;'
        'from scrabble_max.tighten import cross_options;'
        'L=load();'
        "print(json.dumps([cross_options(L,c,r) for r in (0,14) "
        "for c in ('Y','E','A')], default=str))"
    )
    outs = []
    for seed in ('0', '1', '7'):
        p = subprocess.run([sys.executable, '-c', prog],
                           capture_output=True, text=True,
                           env={'PYTHONHASHSEED': seed, 'PATH': '/usr/bin'})
        assert p.returncode == 0, p.stderr
        outs.append(json.loads(p.stdout))
    assert outs[0] == outs[1] == outs[2], (
        'cross_options output varies with PYTHONHASHSEED')
