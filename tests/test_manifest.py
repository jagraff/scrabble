"""The run manifest: coverage, uniformity, and tamper detection.

The manifest asserts two things no individual checkpoint can. Coverage --
every cell the partition defines has a file -- because a cell that was never
launched leaves nothing behind, and a short directory otherwise looks
exactly like a complete one. Uniformity -- one solver build across every
cell -- because checkpoint identity deliberately does not gate on the solver
version, and this is where the cost of that choice is collected.

Synthesised checkpoints throughout; no solver.
"""

import json

import pytest

from scrabble_max import identity as ID
from scrabble_max import manifest as M
from scrabble_max.finalize import write_header


@pytest.fixture
def lex(tmp_path):
    p = tmp_path / 'lex.txt'
    p.write_text('AA\nAB\nCAT\n')
    return str(p)


@pytest.fixture(autouse=True)
def seeded(monkeypatch):
    monkeypatch.setenv('PYTHONHASHSEED', '0')


def _run(lex, **over):
    kw = dict(lexicon_path=lex, threshold=1786, word='OXYPHENBUTAZONE',
              n_blocks=4)
    kw.update(over)
    return ID.run_manifest(**kw)


def _cell_file(cell_dir, run, *, pattern=(0, 2, 3), pivot=3, index=0,
               block=None, complete=True, configs=2, env=None):
    cell = ID.cell_manifest(run, pattern=pattern, pivot=pivot,
                            cell_index=index, block=block)
    cell_dir.mkdir(parents=True, exist_ok=True)
    tag = ''.join(f'{c:02d}' for c in sorted(pattern))
    path = cell_dir / f'{tag}_p{pivot:02d}c{index:03d}.jsonl'
    write_header(str(path), cell, env or {'ortools': '9.15.6755',
                                          'python': '3.12.3'})
    with open(path, 'a') as f:
        for i in range(configs):
            f.write(json.dumps({
                'seconds': 3.0, 'blank_penalty': True,
                'config': {'placed': list(pattern), 'crosses': {'0': f'W{i}'},
                           'relaxed_score': 1787}}) + '\n')
        if complete:
            f.write(json.dumps({'seconds': 1.0, 'blank_penalty': True,
                                'complete': True}) + '\n')
    return path


def test_manifest_hashes_cells_and_artifacts(tmp_path, lex):
    run = _run(lex)
    ckpt = tmp_path / 'enum_cells'
    _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}', run)
    art = tmp_path / 'result.json'
    art.write_text('{"x": 1}')

    man = M.build(ckpt_dir=str(ckpt), artifacts=[str(art)], run=run)
    assert man['summary']['cells'] == 1
    assert man['summary']['cells_complete'] == 1
    assert man['summary']['configurations'] == 2
    assert man['cells'][0]['sha256'] and man['artifacts'][0]['sha256']


def test_verify_catches_an_edited_artifact(tmp_path, lex):
    run = _run(lex)
    ckpt = tmp_path / 'enum_cells'
    _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}', run)
    art = tmp_path / 'result.json'
    art.write_text('{"x": 1}')
    man = M.build(ckpt_dir=str(ckpt), artifacts=[str(art)], run=run)
    # Pinned: the tree this test runs in may legitimately have uncommitted
    # source, and that would otherwise show up as a second complaint.
    man['source_dirty'] = False
    path = tmp_path / 'MANIFEST.json'
    M.write(man, str(path))

    assert M.verify(str(path)) == []
    art.write_text('{"x": 2}')
    problems = M.verify(str(path))
    assert len(problems) == 1 and 'changed since' in problems[0]


def test_verify_catches_an_edited_checkpoint(tmp_path, lex):
    run = _run(lex)
    ckpt = tmp_path / 'enum_cells'
    cell = _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}',
                      run)
    man = M.build(ckpt_dir=str(ckpt), run=run)
    path = tmp_path / 'MANIFEST.json'
    M.write(man, str(path))

    with open(cell, 'a') as f:
        f.write(json.dumps({'seconds': 1.0, 'config': {
            'placed': [0], 'crosses': {}, 'relaxed_score': 1}}) + '\n')
    problems = M.verify(str(path))
    assert any('changed since' in p for p in problems)


def test_mixed_solver_versions_are_reported(tmp_path, lex):
    """Identity does not gate on the solver version, so a mixed artifact is
    possible; this is the check that collects the cost of that choice."""
    run = _run(lex)
    d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
    _cell_file(d, run, index=0, env={'ortools': '9.15.6755'})
    _cell_file(d, run, index=1, env={'ortools': '9.14.0'})
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    mixed = man['summary']['mixed_environment']
    assert 'ortools' in mixed and len(mixed['ortools']) == 2

    path = tmp_path / 'MANIFEST.json'
    M.write(man, str(path))
    assert any('mixed ortools' in p for p in M.verify(str(path)))


def test_one_solver_version_is_not_reported_as_mixed(tmp_path, lex):
    run = _run(lex)
    d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
    _cell_file(d, run, index=0)
    _cell_file(d, run, index=1)
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    assert man['summary']['mixed_environment'] == {}


def test_an_unfinished_cell_is_visible(tmp_path, lex):
    run = _run(lex)
    d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
    _cell_file(d, run, index=0, complete=False)
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    assert man['summary']['cells'] == 1
    assert man['summary']['cells_complete'] == 0


def test_a_corrupt_cell_is_visible(tmp_path, lex):
    run = _run(lex)
    d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
    p = _cell_file(d, run, index=0)
    with open(p, 'a') as f:
        f.write('{"seconds": 1.0, "conf\n')
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    assert man['summary']['cells_corrupt'] == 1


def test_an_unstamped_cell_is_counted(tmp_path, lex):
    run = _run(lex)
    d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
    d.mkdir(parents=True)
    (d / '000203_p03c000.jsonl').write_text(
        json.dumps({'seconds': 1.0, 'complete': True}) + '\n')
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    assert man['summary']['cells_unstamped'] == 1
    assert man['cells'][0]['identity'] is None


PATTERN = (0, 2, 3, 7, 11, 13, 14)


@pytest.fixture(scope='module')
def geometry():
    """`choose_pivot` scans 1,619 cross options and costs ~2.7 s. Computed
    once for the module rather than once per test."""
    from scrabble_max.lexicon import load
    from scrabble_max.partition import choose_pivot, make_cells
    pivot, n_options = choose_pivot(load(), PATTERN)
    return pivot, make_cells(n_options, 4)


class TestCoverage:
    """A missing cell is the failure mode a file listing cannot see: a cell
    that was never launched writes nothing, and 4 files where 5 were
    expected looks exactly like 4 files where 4 were expected.

    One real pattern, against the real lexicon, because the expected set is
    derived from `choose_pivot`/`make_cells` and stubbing those would test
    the stub.
    """

    PATTERN = PATTERN

    def _populate(self, tmp_path, run, geometry, skip=()):
        pivot, cells = geometry
        d = tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}'
        for i, block in enumerate(cells):
            if i in skip:
                continue
            _cell_file(d, run, pattern=self.PATTERN, pivot=pivot, index=i,
                       block=block)
        return M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)

    def test_a_full_directory_has_no_complaints(self, tmp_path, lex,
                                                geometry):
        run = _run(lex)
        man = self._populate(tmp_path, run, geometry)
        assert M.check_coverage(man, [self.PATTERN]) == []

    def test_a_missing_cell_is_caught(self, tmp_path, lex, geometry):
        run = _run(lex)
        man = self._populate(tmp_path, run, geometry, skip={2})
        problems = M.check_coverage(man, [self.PATTERN])
        assert len(problems) == 1 and 'missing entirely' in problems[0]

    def test_an_unfinished_cell_is_caught(self, tmp_path, lex, geometry):
        pivot, cells = geometry
        run = _run(lex)
        man = self._populate(tmp_path, run, geometry, skip={1})
        _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}',
                   run, pattern=self.PATTERN, pivot=pivot, index=1,
                   block=cells[1], complete=False)
        man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
        problems = M.check_coverage(man, [self.PATTERN])
        assert len(problems) == 1 and 'not complete' in problems[0]

    def test_a_cell_from_another_partition_is_caught(self, tmp_path, lex,
                                                     geometry):
        """A file whose identity is valid but does not belong to the
        partition being certified -- a stray from a different run dropped
        into the directory."""
        pivot, cells = geometry
        run = _run(lex)
        man = self._populate(tmp_path, run, geometry)
        _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}',
                   run, pattern=self.PATTERN, pivot=pivot, index=99,
                   block=frozenset({3}))
        man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
        problems = M.check_coverage(man, [self.PATTERN])
        assert len(problems) == 1 and 'not in the partition' in problems[0]


def test_uncommitted_source_is_reported_but_dirty_results_are_not(
        tmp_path, lex, monkeypatch):
    """`git_dirty` is true for the whole of any run, because the results
    being regenerated are tracked files. Only uncommitted *source* means
    the recorded commit fails to identify the code."""
    run = _run(lex)
    _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}', run)
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    man['source_dirty'] = False
    man['environment']['git_dirty'] = True          # results in flight
    path = tmp_path / 'MANIFEST.json'
    M.write(man, str(path))
    assert M.verify(str(path)) == []

    man['source_dirty'] = True
    M.write(man, str(path))
    assert any('uncommitted source' in p for p in M.verify(str(path)))


class TestRefutation:
    """The other half of the claim.

    Cell checkpoints certify that the *enumeration* was exhaustive. Nothing
    certified that every enumerated configuration was then refuted: the
    verdict files were unhashed and uncounted, so "every configuration
    refuted" rested on a line of console output, and a configuration that
    was enumerated and never checked would leave no trace.
    """

    def _setup(self, tmp_path, rows, enumerated=None, decomposed=None):
        d = tmp_path / 'checks'
        d.mkdir()
        (d / 'pattern.json').write_text(json.dumps(rows))
        if decomposed is not None:
            (d / 'decomposed.json').write_text(json.dumps(decomposed))
        cfg = tmp_path / 'tier3_configs.json'
        cfg.write_text(json.dumps({
            'threshold': 1786,
            'patterns': [{'placed': [0, 2, 3],
                          'count': len(rows) if enumerated is None
                          else enumerated}]}))
        return M.refutation_summary(str(d), str(cfg))

    def _row(self, status='INFEASIBLE', value=None, crosses=None):
        return {'status': status, 'value': value,
                'config': {'placed': [0, 2, 3],
                           'crosses': crosses or {'0': 'WORD'}}}

    def test_all_refuted_is_clean(self, tmp_path):
        s = self._setup(tmp_path, [self._row(), self._row()])
        assert s['refuted'] == 2 and s['undecided'] == 0
        assert M.check_refutation(s) == []

    def test_an_undecided_configuration_fails(self, tmp_path):
        s = self._setup(tmp_path, [self._row(), self._row('UNKNOWN')])
        assert s['undecided'] == 1
        assert any('UNDECIDED' in p for p in M.check_refutation(s))

    def test_decomposition_closes_an_undecided_configuration(self, tmp_path):
        """The step that was run by hand and recorded as prose. It now
        leaves a machine-readable record, and this is what reads it."""
        s = self._setup(
            tmp_path, [self._row('UNKNOWN', crosses={'0': 'HARD'})],
            decomposed=[{'placed': [0, 2, 3], 'crosses': {'0': 'HARD'},
                         'refuted': True, 'open_branches': 0}])
        assert s['undecided'] == 0 and s['refuted'] == 1
        assert M.check_refutation(s) == []

    def test_a_failed_decomposition_does_not_close_it(self, tmp_path):
        s = self._setup(
            tmp_path, [self._row('UNKNOWN', crosses={'0': 'HARD'})],
            decomposed=[{'placed': [0, 2, 3], 'crosses': {'0': 'HARD'},
                         'refuted': False, 'open_branches': 3}])
        assert s['undecided'] == 1
        assert any('UNDECIDED' in p for p in M.check_refutation(s))

    def test_a_configuration_above_the_threshold_fails(self, tmp_path):
        s = self._setup(tmp_path, [self._row('OPTIMAL', value=1787)])
        assert s['above_threshold'] == 1
        assert any('above the threshold' in p for p in M.check_refutation(s))

    def test_an_unchecked_configuration_is_caught(self, tmp_path):
        """Enumerated 5, checked 2. Without this the missing three are
        invisible: they are absent from the verdict files, and absence is
        exactly what a count of the files cannot see."""
        s = self._setup(tmp_path, [self._row(), self._row()], enumerated=5)
        assert s['missing_verdicts'] == 3
        assert any('no verdict' in p for p in M.check_refutation(s))


def test_manifest_digest_is_stable_under_reserialisation(tmp_path, lex):
    run = _run(lex)
    _cell_file(tmp_path / 'enum_cells' / f'run-{ID.digest(run)[:12]}', run)
    man = M.build(ckpt_dir=str(tmp_path / 'enum_cells'), run=run)
    a = M.write(man, str(tmp_path / 'a.json'))
    b = M.write(json.loads(json.dumps(man)), str(tmp_path / 'b.json'))
    assert a == b, 'the quoted digest must survive a round trip through JSON'
