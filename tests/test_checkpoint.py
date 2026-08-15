"""Enumeration checkpointing (finalize.repair_checkpoint / read_checkpoint).

The failure that motivated these is worth stating, because it is the one
that would matter: appending after a torn write concatenates the new
record onto the broken one, yielding a single unparseable line that
swallows *both* -- the partial record and a good one after it. The file
still carried its `complete` marker, so a later resume returned a list
missing a configuration while asserting it was exhaustive. Every
downstream claim rests on that exhaustiveness, so checkpointing that
silently drops entries is worse than no checkpointing at all.

Almost all of this is file handling, so it is tested without the solver:
records are synthesised rather than enumerated. Only the end-to-end
round-trip needs CP-SAT, and it is marked slow.
"""

import json
import os

import pytest

from scrabble_max.finalize import (read_checkpoint, repair_checkpoint,
                                   resume_enumeration)


def _record(i):
    return {'seconds': 1.5,
            'config': {'placed': [0, 2, 3, 7, 11, 13, 14],
                       'crosses': {'0': f'WORD{i}', '7': 'BLADDERLIKE'},
                       'relaxed_score': 1787}}


def _write(path, n, complete=False, tear_last=False):
    lines = [json.dumps(_record(i)) for i in range(n)]
    if complete:
        lines.append(json.dumps({'seconds': 2.0, 'complete': True}))
    text = ''.join(l + '\n' for l in lines)
    if tear_last:
        text = text.rstrip('\n')
        text = text[:len(text) - len(lines[-1]) // 2]
    path.write_text(text)


def test_intact_file_reads_back_whole(tmp_path):
    p = tmp_path / 'c.jsonl'
    _write(p, 5)
    cfgs, complete, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 5 and not complete and not corrupt


def test_complete_marker_is_read(tmp_path):
    p = tmp_path / 'c.jsonl'
    _write(p, 3, complete=True)
    cfgs, complete, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 3 and complete and not corrupt


def test_torn_final_line_is_skipped_and_flagged(tmp_path):
    p = tmp_path / 'c.jsonl'
    _write(p, 5, tear_last=True)
    cfgs, _, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 4, 'the torn record is dropped, the rest survive'
    assert corrupt


def test_repair_truncates_only_a_partial_line(tmp_path):
    p = tmp_path / 'c.jsonl'
    _write(p, 5, tear_last=True)
    assert repair_checkpoint(str(p)) is True
    assert p.read_text().endswith('\n')
    cfgs, _, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 4 and not corrupt


def test_repair_is_a_no_op_on_an_intact_file(tmp_path):
    p = tmp_path / 'c.jsonl'
    _write(p, 5)
    before = p.read_text()
    assert repair_checkpoint(str(p)) is False
    assert p.read_text() == before


def test_appending_after_a_torn_line_without_repair_eats_a_good_record(
        tmp_path):
    """The original bug, pinned so it cannot come back: without repair the
    append fuses onto the broken line and two records are lost, not one."""
    p = tmp_path / 'c.jsonl'
    _write(p, 5, tear_last=True)
    with open(p, 'a') as f:                     # deliberately no repair
        f.write(json.dumps(_record(99)) + '\n')
    cfgs, _, _, corrupt = read_checkpoint(str(p))
    assert corrupt
    assert len(cfgs) == 4, ('4 intact + 1 appended = 5 expected, but the '
                            'fused line loses the appended one too')


def test_repair_then_append_keeps_every_record(tmp_path):
    """With repair, only the torn record is lost and the append survives."""
    p = tmp_path / 'c.jsonl'
    _write(p, 5, tear_last=True)
    repair_checkpoint(str(p))
    with open(p, 'a') as f:
        f.write(json.dumps(_record(99)) + '\n')
    cfgs, _, _, corrupt = read_checkpoint(str(p))
    assert len(cfgs) == 5 and not corrupt


def test_complete_is_not_honoured_when_a_line_is_corrupt(tmp_path, monkeypatch):
    """A short list claiming exhaustiveness is the dangerous case: resume
    must re-verify rather than trust the marker."""
    p = tmp_path / '00020307111314.jsonl'
    text = ''.join(json.dumps(_record(i)) + '\n' for i in range(4))
    text += '{"seconds": 1.0, "conf\n'                 # corrupt mid-file
    text += json.dumps({'seconds': 2.0, 'complete': True}) + '\n'
    p.write_text(text)
    cfgs, complete, _, corrupt = read_checkpoint(str(p))
    assert complete and corrupt, 'setup: marker present, a line unparseable'

    called = {}

    def fake_enumerate(*a, **k):
        called['ran'] = True
        return [], True

    monkeypatch.setattr('scrabble_max.finalize.enumerate_configs',
                        fake_enumerate)
    resume_enumeration(None, (0, 2, 3, 7, 11, 13, 14),
                       checkpoint_dir=str(tmp_path), log=lambda *a, **k: None)
    assert called.get('ran'), ('resume trusted a complete marker on a file '
                               'with a lost line')


def test_missing_file_is_empty_not_an_error(tmp_path):
    cfgs, complete, timings, corrupt = read_checkpoint(
        str(tmp_path / 'nope.jsonl'))
    assert cfgs == [] and not complete and not corrupt
    assert repair_checkpoint(str(tmp_path / 'nope.jsonl')) is False
