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
