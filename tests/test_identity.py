"""Checkpoint identity: a stored `complete` marker is only a discharged
proof obligation for the computation that produced it.

The failure these exist to prevent is a run reporting exhaustive coverage
of a space it never searched. The sharpest instance is the block count:
cell `i` under `--blocks 4` covers option indices `i mod 4` and under
`--blocks 8` covers `i mod 8`, and the cell index -- the only part of the
file name that varied with the partition -- is identical in both. Reusing
a 4-block directory at 8 blocks therefore accepted five files whose union
no longer covered the option set, and printed complete=True.

No solver here: identity is decided before any model is built, so every
case is a synthesised file and the module runs in well under a second.
"""

import json

import pytest

from scrabble_max import identity as ID
from scrabble_max.finalize import (StaleCheckpoint, checkpoint_header,
                                   checkpoint_scales, read_checkpoint,
                                   verify_checkpoint_identity, write_header)


@pytest.fixture
def lex(tmp_path):
    p = tmp_path / 'lex.txt'
    p.write_text('AA\nAB\nCAT\n')
    return str(p)


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv('PYTHONHASHSEED', '0')


def _run(lex, **over):
    kw = dict(lexicon_path=lex, threshold=1786, word='OXYPHENBUTAZONE',
              row=0, blank_penalty=True, prune_unplaced=True, n_blocks=4)
    kw.update(over)
    return ID.run_manifest(**kw)


def _cell(run, **over):
    """A cell manifest. `pivot`/`block` are accepted as a shorthand for a
    single-column cell, which most of these cases want."""
    pivot = over.pop('pivot', 3)
    block = over.pop('block', frozenset({1, 5, 9}))
    kw = dict(pattern=(0, 2, 3, 7, 11, 13, 14), cell_index=1,
              constraints=[(pivot, block)])
    kw.update(over)
    return ID.cell_manifest(run, **kw)


def _write(path, cell, n=2, complete=True):
    write_header(str(path), cell)
    with open(path, 'a') as f:
        for i in range(n):
            f.write(json.dumps({
                'seconds': 1.0, 'blank_penalty': True,
                'config': {'placed': [0, 2, 3], 'crosses': {'0': f'W{i}'},
                           'relaxed_score': 1787}}) + '\n')
        if complete:
            f.write(json.dumps({'seconds': 2.0, 'blank_penalty': True,
                                'complete': True}) + '\n')


# --- the four isolation cases the audit asked for ------------------------

def test_threshold_isolation(tmp_path, lex, seeded):
    """Written at 1786, re-run at 1785: the old file searched for a
    strictly smaller set of configurations and cannot certify the new one."""
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(_run(lex, threshold=1786)))
    with pytest.raises(StaleCheckpoint, match='threshold'):
        verify_checkpoint_identity(str(p), _cell(_run(lex, threshold=1785)))


def test_block_count_isolation(tmp_path, lex, seeded):
    """The one that actually bit: same pattern, same pivot, same cell
    index, same file name -- different slice of the option space."""
    four = _cell(_run(lex, n_blocks=4), block=frozenset({1, 5, 9}))
    eight = _cell(_run(lex, n_blocks=8), block=frozenset({1, 9}))
    p = tmp_path / 'c.jsonl'
    _write(p, four)
    with pytest.raises(StaleCheckpoint) as e:
        verify_checkpoint_identity(str(p), eight)
    assert 'n_blocks' in str(e.value) and 'block' in str(e.value)


def test_block_membership_isolation_at_equal_count(tmp_path, lex, seeded):
    """n_blocks alone is not enough. Two runs can agree on the count and
    still slice differently, so membership is stored explicitly rather
    than trusted to follow from the count."""
    run = _run(lex)
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(run, block=frozenset({1, 5, 9})))
    with pytest.raises(StaleCheckpoint, match='block'):
        verify_checkpoint_identity(str(p), _cell(run,
                                                 block=frozenset({2, 6, 10})))


def test_lexicon_isolation(tmp_path, lex, seeded):
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(_run(lex)))
    with open(lex, 'a') as f:
        f.write('ZZZ\n')
    with pytest.raises(StaleCheckpoint, match='lexicon_sha256'):
        verify_checkpoint_identity(str(p), _cell(_run(lex)))


def test_model_source_isolation(tmp_path, lex, seeded):
    """Editing a module that builds the model invalidates the proofs it
    produced. Simulated by hashing a different source set rather than by
    editing the package under the test."""
    a = _run(lex, sources=('rules.py',))
    b = _run(lex, sources=('rules.py', 'lexicon.py'))
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(a))
    with pytest.raises(StaleCheckpoint, match='model_sources_sha256'):
        verify_checkpoint_identity(str(p), _cell(b))


# --- what must still be accepted -----------------------------------------

def test_matching_checkpoint_is_accepted(tmp_path, lex, seeded):
    p = tmp_path / 'c.jsonl'
    cell = _cell(_run(lex))
    _write(p, cell)
    assert verify_checkpoint_identity(str(p), cell) == 'stamped'
    cfgs, complete, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 2 and complete and not corrupt


def test_solver_version_is_recorded_but_not_gated(tmp_path, lex, seeded):
    """An infeasibility proof is a fact about the model, not the solver
    that found it. Upgrading OR-Tools must not discard sound work -- the
    version is recorded for uniformity assertions over the manifest."""
    p = tmp_path / 'c.jsonl'
    cell = _cell(_run(lex))
    write_header(str(p), cell, {'ortools': '9.14.0', 'python': '3.12.3'})
    stored, _ = checkpoint_header(str(p))
    assert verify_checkpoint_identity(str(p), cell) == 'stamped'
    assert 'ortools' not in stored, 'environment must stay out of the gate'
    with open(p) as f:
        assert json.loads(f.readline())['environment']['ortools'] == '9.14.0'


def test_missing_file_is_absent_not_stale(tmp_path, lex, seeded):
    assert verify_checkpoint_identity(str(tmp_path / 'nope.jsonl'),
                                      _cell(_run(lex))) == 'absent'


# --- legacy files ---------------------------------------------------------

def test_unstamped_checkpoint_is_refused_by_default(tmp_path, lex, seeded):
    """The 50 committed pre-hardening cells land here: unknown identity is
    not the same as matching identity."""
    p = tmp_path / 'c.jsonl'
    p.write_text(json.dumps({'seconds': 1.0, 'blank_penalty': True,
                             'complete': True}) + '\n')
    with pytest.raises(StaleCheckpoint, match='no identity header'):
        verify_checkpoint_identity(str(p), _cell(_run(lex)))


def test_unstamped_checkpoint_can_be_opted_into(tmp_path, lex, seeded):
    p = tmp_path / 'c.jsonl'
    p.write_text(json.dumps({'seconds': 1.0, 'complete': True}) + '\n')
    assert verify_checkpoint_identity(str(p), _cell(_run(lex)),
                                      allow_unstamped=True) == 'unstamped'


def test_torn_first_line_is_not_mistaken_for_a_header(tmp_path, lex, seeded):
    p = tmp_path / 'c.jsonl'
    p.write_text('{"header": {"threa\n')
    with pytest.raises(StaleCheckpoint, match='no identity header'):
        verify_checkpoint_identity(str(p), _cell(_run(lex)))


# --- the header must not disturb the existing readers --------------------

def test_header_does_not_count_as_a_configuration(tmp_path, lex, seeded):
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(_run(lex)), n=3)
    cfgs, complete, timings, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 3 and complete and not corrupt
    assert len(timings) == 4, 'header contributes no timing entry'


def test_header_does_not_muddy_the_charging_scale(tmp_path, lex, seeded):
    """The header has no `blank_penalty` key of its own, and a stray None
    in this set is read as "the file cannot vouch for itself"."""
    p = tmp_path / 'c.jsonl'
    _write(p, _cell(_run(lex)))
    assert checkpoint_scales(str(p)) == {True}


def test_write_header_is_idempotent(tmp_path, lex, seeded):
    """A resumed cell must not append a second header."""
    p = tmp_path / 'c.jsonl'
    cell = _cell(_run(lex))
    assert write_header(str(p), cell) is True
    assert write_header(str(p), cell) is False
    assert p.read_text().count('"header"') == 1


# --- the hash seed --------------------------------------------------------

def test_unpinned_hash_seed_refuses_to_run(tmp_path, lex, monkeypatch):
    """Unset must fail loudly rather than record None: with the variable
    unset every process reports the same None while running under
    different seeds, so the check would report a match in exactly the
    case that is dangerous."""
    monkeypatch.delenv('PYTHONHASHSEED', raising=False)
    with pytest.raises(RuntimeError, match='PYTHONHASHSEED'):
        _run(lex)
    monkeypatch.setenv('PYTHONHASHSEED', 'random')
    with pytest.raises(RuntimeError, match='PYTHONHASHSEED'):
        _run(lex)


def test_hash_seed_is_gated(tmp_path, lex, monkeypatch):
    monkeypatch.setenv('PYTHONHASHSEED', '0')
    a = _cell(_run(lex))
    monkeypatch.setenv('PYTHONHASHSEED', '1')
    b = _cell(_run(lex))
    p = tmp_path / 'c.jsonl'
    _write(p, a)
    with pytest.raises(StaleCheckpoint, match='pythonhashseed'):
        verify_checkpoint_identity(str(p), b)


# --- digest hygiene -------------------------------------------------------

def test_digest_ignores_key_order(lex, seeded):
    a = _run(lex)
    assert ID.digest(a) == ID.digest(dict(reversed(list(a.items()))))


def test_no_cross_cell_collisions(lex, seeded):
    """Every cell of a run must hash differently, or two cells share a
    stored proof."""
    run = _run(lex)
    ds = {ID.digest(_cell(run, cell_index=i,
                          block=None if i == 0 else frozenset({i})))
          for i in range(9)}
    assert len(ds) == 9


def test_no_cross_pattern_collisions(lex, seeded):
    run = _run(lex)
    a = ID.digest(_cell(run, pattern=(0, 2, 3, 7, 11, 13, 14)))
    b = ID.digest(_cell(run, pattern=(0, 1, 3, 7, 11, 13, 14)))
    assert a != b


def test_empty_block_is_distinct_from_the_no_cross_cell(lex, seeded):
    """`None` means the pivot takes no cross word; an empty set would
    enumerate nothing. Conflating them would let one stand in for the
    other."""
    run = _run(lex)
    assert (ID.digest(_cell(run, block=None))
            != ID.digest(_cell(run, block=frozenset())))


# --- the wiring, without the solver --------------------------------------

def _fake_cell_run(monkeypatch, tmp_path, recorder):
    """Stand in for the CP-SAT enumeration, keeping its checkpoint contract:
    stamp the header, then write a completion marker. What is under test is
    that `_run_cell` hands down the right identity and consults it before
    reusing anything -- not the solver."""
    from scrabble_max import finalize, partition

    def fake(lexicon, **kw):
        recorder.append(kw.get('identity'))
        finalize.write_header(kw['checkpoint_path'], kw['identity'],
                              kw.get('environment'))
        with open(kw['checkpoint_path'], 'a') as f:
            f.write(json.dumps({'seconds': 1.0, 'blank_penalty': True,
                                'complete': True}) + '\n')
        return [], True

    monkeypatch.setattr(partition, 'enumerate_configs', fake)
    monkeypatch.setattr(partition, '_lexicon', lambda: None)
    monkeypatch.setattr(partition, 'LEXICON_PATH', str(tmp_path / 'lex.txt'))
    monkeypatch.setattr(partition, 'stamp', lambda: {'ortools': 'test'})


def _cell_args(ckpt_dir, run, *, cell_index=1, block=frozenset({1, 5}),
               constraints=None):
    if constraints is None:
        constraints = [(3, block)]
    return ((0, 2, 3, 7, 11, 13, 14), constraints, cell_index, 1786,
            ckpt_dir, 60.0, run, {'ortools': 'test'}, False)


def test_run_cell_stamps_then_reuses_only_its_own_work(
        tmp_path, lex, seeded, monkeypatch):
    from scrabble_max.partition import _run_cell, _run_context

    seen = []
    _fake_cell_run(monkeypatch, tmp_path, seen)
    monkeypatch.setattr('scrabble_max.partition.LEXICON_PATH', lex)
    run, env, out = _run_context(1786, 4, str(tmp_path / 'ckpt'))

    i, cfgs, complete, _, cached = _run_cell(_cell_args(out, run))
    assert complete and not cached, 'first pass must actually enumerate'
    assert seen[0]['n_blocks'] == 4
    assert seen[0]['constraints'] == [[3, [1, 5]]]

    i, cfgs, complete, _, cached = _run_cell(_cell_args(out, run))
    assert complete and cached, 'a matching checkpoint must short-circuit'
    assert len(seen) == 1, 'the cached pass must not re-enumerate'


def test_run_cell_refuses_another_partitions_checkpoint(
        tmp_path, lex, seeded, monkeypatch):
    """The original failure, end to end: same pattern, same pivot, same
    cell index, same file name, different slice of the option space."""
    from scrabble_max.partition import _run_cell, _run_context

    _fake_cell_run(monkeypatch, tmp_path, [])
    monkeypatch.setattr('scrabble_max.partition.LEXICON_PATH', lex)
    run4, _, out4 = _run_context(1786, 4, str(tmp_path / 'ckpt'))
    _run_cell(_cell_args(out4, run4))

    # An 8-block run whose files were forced into the 4-block directory --
    # which is what a single shared directory did before namespacing.
    run8 = ID.run_manifest(lexicon_path=lex, threshold=1786,
                           word='OXYPHENBUTAZONE', n_blocks=8)
    with pytest.raises(StaleCheckpoint) as e:
        _run_cell(_cell_args(out4, run8, block=frozenset({1, 9})))
    assert 'n_blocks' in str(e.value)


def test_no_checkpoint_dir_needs_no_identity(tmp_path, lex, monkeypatch):
    """An in-memory enumeration stores nothing that a later run could
    mistake for its own, so it must not demand a pinned hash seed."""
    from scrabble_max.partition import _run_context

    monkeypatch.delenv('PYTHONHASHSEED', raising=False)
    assert _run_context(1786, 4, None) == (None, None, None)


def test_run_dir_separates_incompatible_runs(tmp_path, lex, seeded):
    a = ID.run_dir(str(tmp_path), _run(lex, threshold=1786))
    b = ID.run_dir(str(tmp_path), _run(lex, threshold=1785))
    assert a != b, 'stale reuse must also be impossible by construction'
