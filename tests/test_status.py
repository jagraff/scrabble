"""Reading enumeration progress off disk (scrabble_max.status).

This is read-only reporting, so nothing it does can corrupt a run. What it
can do is mislead -- and the two ways that matter are:

  * choking on a checkpoint that is *being written*. The last line of a
    live file is routinely half-written, and a status tool that raised (or
    worse, reported zero) on the file it is meant to observe would be
    useless exactly when it is wanted.
  * hiding a stall. The point of the tool is to show lack of progress as
    clearly as progress, so a cell that has been silent far longer than
    any solve it has completed has to be called out rather than shown as
    an ordinary "running" row.
"""

import json
import time

from scrabble_max.status import collect, read_one, render


def _entry(i, seconds=12.0, penalty=True):
    return {'seconds': seconds, 'blank_penalty': penalty,
            'config': {'placed': [0, 2, 3, 7, 11, 13, 14],
                       'crosses': {'0': f'WORD{i}'},
                       'relaxed_score': 1787}}


def _write(path, n, seconds=12.0, complete=False, penalty=True, torn=False):
    lines = [json.dumps(_entry(i, seconds, penalty)) for i in range(n)]
    if complete:
        lines.append(json.dumps({'seconds': 30.0, 'complete': True,
                                 'blank_penalty': penalty}))
    text = ''.join(l + '\n' for l in lines)
    if torn:
        text += json.dumps(_entry(99))[:20]      # half a line, no newline
    path.write_text(text)


def test_the_identity_header_is_not_progress(tmp_path):
    """The stamp is not a solve, and it carries no charging scale of its
    own -- letting it contribute a None would read as "this file cannot
    vouch for itself" and raise a spurious mixed-scale alarm."""
    p = tmp_path / '00020307111314_p03c000.jsonl'
    header = json.dumps({'header': {'threshold': 1786}, 'identity': 'ab'})
    p.write_text(header + '\n'
                 + ''.join(json.dumps(_entry(i)) + '\n' for i in range(3)))
    r = read_one(str(p))
    assert r['configs'] == 3
    assert len(r['timings']) == 3, 'the header contributes no duration'
    assert r['scales'] == {True}


def test_cells_are_found_inside_run_namespaced_directories(tmp_path):
    """Checkpoints live in `<dir>/run-<hash>/`, and a watcher pointed at
    the parent must still find them."""
    from scrabble_max.status import cell_files
    run = tmp_path / 'run-5de00fc1974d'
    run.mkdir()
    _write(run / '00020307111314_p03c000.jsonl', 3)
    assert len(cell_files(str(tmp_path))) == 1
    assert len(collect(str(tmp_path))) == 1


def test_a_live_run_is_never_merged_with_an_archived_one(tmp_path):
    """The counts must belong to one run. Merging a live run's cells with
    a superseded run's flat files gave "8/10 finished, 1356 configurations"
    -- 1322 from the old run plus 34 from the new. A watcher whose job is
    to say whether a run has finished must not be able to say that."""
    from scrabble_max.status import cell_files
    for i in range(4):                                  # superseded, flat
        _write(tmp_path / f'0001020307111{i}.jsonl', 100, complete=True)
    run = tmp_path / 'run-ddc68461eadd'
    run.mkdir()
    _write(run / '00020307111314_p03c000.jsonl', 3)

    found = cell_files(str(tmp_path))
    assert len(found) == 1, 'the flat files belong to a different run'
    rows = collect(str(tmp_path))
    assert sum(r['configs'] for r in rows) == 3, 'no cross-run arithmetic'


def test_the_newest_run_wins_when_several_are_present(tmp_path):
    import os
    import time as _t
    old = tmp_path / 'run-aaaaaaaaaaaa'
    old.mkdir()
    _write(old / 'a_p03c000.jsonl', 5)
    new = tmp_path / 'run-bbbbbbbbbbbb'
    new.mkdir()
    _write(new / 'b_p03c000.jsonl', 2)
    os.utime(old, (_t.time() - 3600, _t.time() - 3600))

    from scrabble_max.status import cell_files, runs_present
    assert [os.path.basename(d) for d in runs_present(str(tmp_path))][0] \
        == 'run-bbbbbbbbbbbb'
    assert sum(r['configs'] for r in collect(str(tmp_path))) == 2
    assert len(cell_files(str(tmp_path))) == 1


def test_flat_files_are_still_read_when_there_is_no_namespaced_run(tmp_path):
    """The pre-hardening layout, so an archived run can still be inspected."""
    from scrabble_max.status import cell_files
    _write(tmp_path / '00010203071114.jsonl', 2)
    assert len(cell_files(str(tmp_path))) == 1


def test_a_half_written_final_line_does_not_lose_the_rest(tmp_path):
    """The normal state of a live checkpoint."""
    p = tmp_path / '00020307111314.jsonl'
    _write(p, 5, torn=True)
    r = read_one(str(p))
    assert r['configs'] == 5 and r['corrupt']


def test_counts_and_timings(tmp_path):
    p = tmp_path / '00020307111314.jsonl'
    _write(p, 4, seconds=10.0)
    r = read_one(str(p))
    assert r['configs'] == 4
    assert sum(r['timings']) == 40.0
    assert not r['complete']


def test_complete_marker_is_not_counted_as_a_configuration(tmp_path):
    p = tmp_path / '00020307111314.jsonl'
    _write(p, 3, complete=True)
    r = read_one(str(p))
    assert r['configs'] == 3 and r['complete']


def test_cells_are_grouped_under_their_pattern(tmp_path):
    for i in range(3):
        _write(tmp_path / f'00020307091114_p03c{i:03d}.jsonl', 2)
    rows = collect(str(tmp_path))
    assert len(rows) == 3
    assert {r['pattern'] for r in rows} == {'00020307091114'}


def test_by_pattern_sums_cells_into_one_row(tmp_path):
    for i in range(4):
        _write(tmp_path / f'00020307091114_p03c{i:03d}.jsonl', 5,
               complete=(i < 2))
    out = render(collect(str(tmp_path)), by_pattern=True)
    assert '20' in out, 'four cells of five configurations should total 20'
    assert '2/4 cells' in out


def test_a_long_silence_is_reported_not_shown_as_normal(tmp_path):
    """A cell silent for far longer than any solve it has finished is the
    signal worth surfacing -- it is the closing proof, a hard solve, or a
    hang, and the tool must not let it look routine."""
    p = tmp_path / '00020307111314.jsonl'
    _write(p, 3, seconds=5.0)
    old = time.time() - 3600
    import os
    os.utime(p, (old, old))
    out = render(collect(str(tmp_path)))
    assert 'longer than any solve' in out
    assert '00020307111314' in out


def test_a_finished_run_is_not_reported_as_stalled(tmp_path):
    p = tmp_path / '00020307111314.jsonl'
    _write(p, 3, seconds=5.0, complete=True)
    old = time.time() - 3600
    import os
    os.utime(p, (old, old))
    out = render(collect(str(tmp_path)))
    assert 'longer than any solve' not in out
    assert 'done' in out


def test_mixed_charging_scales_are_called_out(tmp_path):
    p = tmp_path / '00020307111314.jsonl'
    lines = [json.dumps(_entry(0, penalty=True)),
             json.dumps(_entry(1, penalty=False))]
    p.write_text(''.join(l + '\n' for l in lines))
    out = render(collect(str(tmp_path)))
    assert 'MIXED CHARGING SCALES' in out


def test_empty_directory_says_so_rather_than_printing_a_bare_table(tmp_path):
    assert 'no checkpoints yet' in render(collect(str(tmp_path)))


def test_a_started_cell_that_has_found_nothing_is_visible(tmp_path):
    """The gap this closes: a cell writes nothing until it finds a
    configuration, and one that finds none writes nothing until it ends.
    Four busy workers then look exactly like a run that never started."""
    p = tmp_path / '00020307091114_p03c001.jsonl'
    p.write_text(json.dumps({'seconds': 0.0, 'blank_penalty': True,
                             'started': time.time()}) + '\n')
    rows = collect(str(tmp_path))
    assert rows[0]['configs'] == 0 and not rows[0]['complete']
    out = render(rows)
    assert 'searching' in out
    assert 'no checkpoints yet' not in out


def test_the_started_marker_does_not_count_as_a_solve(tmp_path):
    """It carries no duration; averaging its 0.0 in would drag the median
    toward zero and make solves look faster than they are."""
    p = tmp_path / '00020307111314.jsonl'
    lines = [json.dumps({'seconds': 0.0, 'started': time.time()})]
    lines += [json.dumps(_entry(i, seconds=12.0)) for i in range(3)]
    p.write_text(''.join(l + '\n' for l in lines))
    r = read_one(str(p))
    assert r['timings'] == [12.0, 12.0, 12.0]
    assert r['configs'] == 3


def test_a_silent_cell_with_no_finished_solve_is_still_flagged(tmp_path):
    """It has no yardstick of its own, so the fallback is how long solves
    are taking elsewhere -- otherwise the one cell that never finds
    anything is the one that never gets flagged."""
    import os
    busy = tmp_path / '00020307091114_p03c000.jsonl'
    _write(busy, 4, seconds=12.0)
    quiet = tmp_path / '00020307091114_p03c001.jsonl'
    quiet.write_text(json.dumps({'seconds': 0.0,
                                 'started': time.time() - 3600}) + '\n')
    old = time.time() - 3600
    os.utime(quiet, (old, old))
    out = render(collect(str(tmp_path)))
    assert 'longer than any solve' in out
    assert 'no solve finished yet' in out


# --- refutation phase ---------------------------------------------------

def _configs_file(tmp_path, counts):
    p = tmp_path / 'tier3_configs.json'
    p.write_text(json.dumps({'patterns': [
        {'placed': list(placed), 'count': n, 'complete': True, 'configs': []}
        for placed, n in counts.items()]}))
    return str(p)


def _check_rows(n, status='INFEASIBLE', value=None, reason=None):
    """`reason` is what marks a kill by the exact ceiling: check_configs
    sets it only when it skipped the solver entirely. A row without one
    that also has no value is a *timeout*, not a cheap win."""
    row = {'config': {'placed': [0], 'crosses': {}, 'relaxed_score': 1787},
           'status': status, 'value': value, 'bound': 1780, 'solution': None}
    if reason:
        row['reason'] = reason
    return [dict(row) for _ in range(n)]


CEIL = 'exact blank cost puts this ceiling at 1786 <= 1786'


def test_checks_count_decided_against_the_enumerated_total(tmp_path):
    from scrabble_max.status import collect_checks, render_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 14})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(json.dumps(_check_rows(9)))
    rows = collect_checks(str(cdir), cfg)
    assert rows[0]['done'] == 9 and rows[0]['total'] == 14
    assert '9/14' in render_checks(rows)


def test_a_file_caught_mid_rewrite_reuses_the_last_good_read(tmp_path):
    """check_configs rewrites the whole file after every configuration, so
    landing mid-write is routine. Reporting 0 there would look exactly
    like a pattern that had stalled."""
    from scrabble_max.status import collect_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 14})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    f = cdir / '00020307111314.json'
    f.write_text(json.dumps(_check_rows(9)))
    cache = {}
    assert collect_checks(str(cdir), cfg, cache)[0]['done'] == 9
    f.write_text('[{"status": "INFEA')                  # caught mid-write
    row = collect_checks(str(cdir), cfg, cache)[0]
    assert row['done'] == 9 and row['writing']


def test_a_status_other_than_infeasible_is_raised_as_an_alarm(tmp_path):
    """An UNKNOWN is an undecided configuration, and the proof is not
    closed while one exists -- it must never blend into the table."""
    from scrabble_max.status import collect_checks, render_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 2})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(
        json.dumps(_check_rows(1) + _check_rows(1, status='UNKNOWN')))
    out = render_checks(collect_checks(str(cdir), cfg))
    assert 'NOT INFEASIBLE' in out and 'UNKNOWN' in out


def test_a_configuration_above_the_threshold_is_shouted_about(tmp_path):
    """The one result that would overturn the record rather than confirm
    it. It must not be a quiet row in a table."""
    from scrabble_max.status import collect_checks, render_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 1})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(
        json.dumps(_check_rows(1, status='OPTIMAL', value=1790)))
    out = render_checks(collect_checks(str(cdir), cfg))
    assert 'SCORE ABOVE 1786' in out and '1790' in out


def test_all_infeasible_and_complete_states_the_conclusion(tmp_path):
    from scrabble_max.status import collect_checks, render_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 3})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(json.dumps(_check_rows(3)))
    out = render_checks(collect_checks(str(cdir), cfg))
    assert 'every configuration INFEASIBLE' in out


def test_ceiling_kills_and_solver_decisions_are_counted_separately(tmp_path):
    """They are different evidence: a ceiling kill is closed-form
    arithmetic, a solver decision is a CP-SAT infeasibility proof."""
    from scrabble_max.status import collect_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 4})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(json.dumps(
        _check_rows(3, reason=CEIL) + _check_rows(1, value=1700)))
    row = collect_checks(str(cdir), cfg)[0]
    assert row['no_solve'] == 3 and row['done'] - row['no_solve'] == 1


def test_a_timeout_is_not_counted_as_a_ceiling_kill(tmp_path):
    """The bug this replaces: an UNKNOWN also has value None, so counting
    'no value' as a ceiling kill filed an undecided configuration under
    the decided column -- and the run then printed that every
    configuration had been killed by the ceiling while one was open."""
    from scrabble_max.status import collect_checks, render_checks
    cfg = _configs_file(tmp_path, {(0, 2, 3, 7, 11, 13, 14): 3})
    cdir = tmp_path / 'checks'
    cdir.mkdir()
    (cdir / '00020307111314.json').write_text(json.dumps(
        _check_rows(2, reason=CEIL) + _check_rows(1, status='UNKNOWN')))
    row = collect_checks(str(cdir), cfg)[0]
    assert row['no_solve'] == 2, 'the UNKNOWN must not be a ceiling kill'
    out = render_checks([row])
    assert 'NOT INFEASIBLE' in out
    assert 'every configuration INFEASIBLE' not in out
