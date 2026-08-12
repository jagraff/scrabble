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
def test_tight_bound_dominates_known_1786():
    # The real 1786 play satisfies every stage-B constraint, so the stage-B
    # optimum for (OXYPHENBUTAZONE, row 0) must be >= 1786.
    (bound, detail), per_mask = tighten_candidate(LEX, 'OXYPHENBUTAZONE', 0,
                                                  time_limit=120.0)
    assert bound >= 1786
