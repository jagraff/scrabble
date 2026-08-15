"""Trimming the row-1 automaton (tighten.trim_line_dawg).

The trim removes states and transitions that cannot lie on any accepted
path of exactly 15 steps *under the per-column alphabets*. That qualifier
is the whole content of the claim: the trimmed automaton is equivalent to
the full one only on rows whose every symbol is allowed at its column, and
the model guarantees exactly that with `AddAllowedAssignments` on each
`e[c]` before it ever reaches `AddAutomaton`.

So there are two things to check, and the second is easy to forget:

  * on alphabet-respecting rows the two automata agree, including on the
    row 1 of the 1,786 board -- a trim that rejected that would refute the
    known play;
  * `inw` is contained in `sec`, which is why the alphabets do not depend
    on the placed set and one cached trim serves every pattern. If that
    ever stopped holding, the cache would hand one pattern another's
    automaton.
"""

import pytest

from scrabble_max import tighten as T
from scrabble_max.known import PRE_BOARD_TEXT
from scrabble_max.lexicon import load
from scrabble_max.rules import N

WORD = 'OXYPHENBUTAZONE'


def compile_(transitions, start, finals):
    """(delta, start, finals) built once -- `accepts` is called thousands
    of times and rebuilding a 149,039-entry map per call dominated."""
    return ({(s, l): t for s, l, t in transitions}, start, set(finals))


def accepts(machine, row):
    """Run the automaton over a row of symbol codes (0 = empty)."""
    delta, s, finals = machine
    for code in row:
        s = delta.get((s, code))
        if s is None:
            return False
    return s in finals


@pytest.fixture(scope='module')
def both():
    lex = load()
    full = T.build_line_dawg(lex)
    allowed = []
    for c in range(N):
        sec = T.second_letters(lex, WORD[c], 0)
        allowed.append(frozenset({0} | {ord(a) - 64 for a in sec}))
    tr, fin = T.trim_line_dawg(full[0], full[1], full[2], allowed)
    return (compile_(*full), compile_(tr, full[1], fin), allowed, lex,
            full)


def _respects(row, allowed):
    return all(code in allowed[c] for c, code in enumerate(row))


def _candidate_rows(lex, allowed):
    """Rows that respect the alphabets -- the only ones the model can
    present to the automaton.

    Deliberately a mix of rows that should be accepted (a single word on
    an otherwise empty row) and rows that should be rejected (the same
    word extended by one adjacent letter into a non-word run). Without the
    second kind the agreement test would only ever compare two `True`s.
    """
    rows = [[0] * N]
    for c in range(N):
        for code in sorted(allowed[c]):
            if code:
                r = [0] * N
                r[c] = code
                rows.append(r)
    for w in sorted(lex):
        if not 2 <= len(w) <= N - 1:
            continue
        for off in range(N - len(w)):
            r = [0] * N
            for i, ch in enumerate(w):
                r[off + i] = ord(ch) - 64
            if not _respects(r, allowed):
                continue
            rows.append(r)
            # extend into the next cell: the run becomes w + ch, which is
            # usually not a word, so the row should be rejected
            tail = off + len(w)
            for code in sorted(allowed[tail]):
                if not code:
                    continue
                if w + chr(code + 64) in lex:
                    continue
                r2 = list(r)
                r2[tail] = code
                rows.append(r2)
                break
            if len(rows) > 4000:
                return rows
    return rows


def test_trim_agrees_on_every_alphabet_respecting_row(both):
    full, trimmed, allowed, lex, _ = both
    rows = _candidate_rows(lex, allowed)
    assert len(rows) > 100, 'setup: need a real sample of rows'
    bad = [r for r in rows if accepts(full, r) != accepts(trimmed, r)]
    assert not bad, f'{len(bad)} rows judged differently, e.g. {bad[0]}'


def test_the_sample_contains_both_verdicts(both):
    """Guard against a vacuous pass: comparing only rows that both automata
    accept, or only rows both reject, would prove nothing."""
    full, _, allowed, lex, _ = both
    rows = _candidate_rows(lex, allowed)
    verdicts = {accepts(full, r) for r in rows}
    assert verdicts == {True, False}


def test_trim_accepts_row_one_of_the_record_board(both):
    """The sharpest single case: row 1 of the 1,786 board is legal, so a
    trim that rejected it would refute the known play."""
    full, trimmed, allowed, _, _ = both
    row1 = [ln for ln in PRE_BOARD_TEXT.splitlines() if ln.strip()][1]
    assert len(row1) == N, f'setup: expected a {N}-cell row, got {row1!r}'
    codes = [0 if ch == '.' else ord(ch.upper()) - 64 for ch in row1]
    assert _respects(codes, allowed), (
        'setup: the record row must be inside the alphabets, or the model '
        'could not admit the 1,786 play at all')
    assert accepts(full, codes), 'setup: the full automaton must accept it'
    assert accepts(trimmed, codes)


def test_inward_letters_are_always_continuation_letters(both):
    """Why one cached trim serves every pattern: a cross word's inward
    letter is by construction a letter that can follow the edge letter."""
    _, _, _, lex, _ = both
    for ch in sorted(set(WORD)):
        inw = {o[4] for o in T.cross_options(lex, ch, 0)}
        sec = set(T.second_letters(lex, ch, 0))
        assert inw <= sec, f'{ch}: {sorted(inw - sec)} not continuations'


def test_trim_actually_removes_something(both):
    """A no-op trim would pass every equivalence test above and buy
    nothing, so the size reduction is part of the contract."""
    _, _, allowed, _, full = both
    tr, _fin = T.trim_line_dawg(full[0], full[1], full[2], allowed)
    assert len(tr) < len(full[0]) / 2, (
        f'{len(tr)} of {len(full[0])} transitions kept; the trim is not '
        f'paying for the reachability sweep')


def test_trim_is_cached_across_calls(both):
    _, _, allowed, _, full = both
    a = T.trim_line_dawg(full[0], full[1], full[2], allowed)
    b = T.trim_line_dawg(full[0], full[1], full[2], allowed)
    assert a is b, 'trim recomputed instead of hitting the cache'
