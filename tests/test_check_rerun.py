"""The identity comparison against the run being replaced.

`check_rerun`'s directional checks only forbid movement in one direction,
which is the right instrument for comparing across the `cross_options` fix
-- the feasible region genuinely grew, so bounds genuinely rose. It is far
too loose for the certified re-run: no model change separates that from
`pre_hardening`, so every comparable number should come back *identical*,
and a bound that quietly climbed would sail through a "may only rise" test.

Synthesised directories; no solver.
"""

import json

import pytest

from scrabble_max.check_rerun import check_identical


def _write(d, name, payload):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(payload))


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / 'prev', tmp_path / 'new'


def _bounds(v):
    return [{'word': 'OXYPHENBUTAZONE', 'row': 0, 'tight_bound': v}]


def _tier2(bound, kept=True):
    return [{'placed': [0, 2, 3, 7, 11, 13, 14], 'row1_bound': bound,
             'kept': kept}]


def test_identical_directories_are_silent(dirs):
    prev, new = dirs
    for d in (prev, new):
        _write(d, 'tight_bounds.json', _bounds(1798.0))
        _write(d, 'pattern_row1.json', _tier2(1787.0))
    assert check_identical(str(prev), str(new)) == []


def test_a_moved_stage_b_bound_is_reported(dirs):
    prev, new = dirs
    _write(prev, 'tight_bounds.json', _bounds(1798.0))
    _write(new, 'tight_bounds.json', _bounds(1799.0))
    moved = check_identical(str(prev), str(new))
    assert len(moved) == 1 and 'MOVED' in moved[0]


def test_a_bound_that_rose_is_still_reported(dirs):
    """The directional check passes a risen bound by design. Between the
    hardening and the re-run nothing may move at all, in either direction
    -- that is the whole point of the sharper comparison."""
    prev, new = dirs
    _write(prev, 'tight_bounds.json', _bounds(1798.0))
    _write(new, 'tight_bounds.json', _bounds(1798.5))
    assert check_identical(str(prev), str(new))


def test_a_changed_survivor_set_is_reported(dirs):
    prev, new = dirs
    _write(prev, 'pattern_row1.json', _tier2(1787.0, kept=True))
    _write(new, 'pattern_row1.json', _tier2(1787.0, kept=False))
    moved = check_identical(str(prev), str(new))
    assert any('survivors changed' in m for m in moved)


def test_a_changed_configuration_count_is_reported(dirs):
    prev, new = dirs
    for d, count in ((prev, 14), (new, 13)):
        _write(d, 'tier3_configs.json', {'patterns': [
            {'placed': [0, 2, 3, 7, 11, 13, 14], 'count': count,
             'complete': True}]})
    moved = check_identical(str(prev), str(new))
    assert len(moved) == 1 and 'configurations (MOVED)' in moved[0]


def test_an_incomplete_pattern_is_reported(dirs):
    prev, new = dirs
    _write(prev, 'tier3_configs.json', {'patterns': [
        {'placed': [0, 2, 3], 'count': 14, 'complete': True}]})
    _write(new, 'tier3_configs.json', {'patterns': [
        {'placed': [0, 2, 3], 'count': 14, 'complete': False}]})
    assert any('not complete' in m for m in check_identical(str(prev),
                                                            str(new)))


def test_a_changed_sweep_verdict_is_reported(dirs):
    prev, new = dirs
    _write(prev, 'blank_penalty_tier2.json', [
        {'placed': [0, 2, 3], 'old': 1790.0, 'new': 1787.0, 'dies': False}])
    _write(new, 'blank_penalty_tier2.json', [
        {'placed': [0, 2, 3], 'old': 1790.0, 'new': 1786.0, 'dies': True}])
    moved = check_identical(str(prev), str(new))
    assert len(moved) == 1 and 'dies=' in moved[0]


def test_a_six_tile_file_of_the_wrong_shape_is_reported_not_a_traceback(dirs):
    """`tighten --six-tiles` writes a per-mask dictionary; the ordinary
    candidate path writes a list. Running the wrong command used to reach
    the comparison and raise AttributeError from inside a loop, which
    names neither the file nor the mistake. It was the documented
    reproduction command that was wrong, so this is not hypothetical.
    """
    from scrabble_max.check_rerun import check_six_tiles
    prev, new = dirs
    _write(prev, 'bound_six_tiles.json', {'row0_max6': 1730.0})
    _write(new, 'bound_six_tiles.json', [{'word': 'X', 'tight_bound': 1.0}])
    bad, moved = check_six_tiles(str(prev), str(new))
    assert bad and 'not the per-mask dictionary' in bad[0]
    assert moved == {}


def test_missing_files_are_skipped_not_fabricated(dirs):
    """A partial re-run must not be reported as a pile of regressions."""
    prev, new = dirs
    _write(prev, 'tight_bounds.json', _bounds(1798.0))
    new.mkdir(parents=True, exist_ok=True)
    assert check_identical(str(prev), str(new)) == []


def test_the_committed_archive_compares_clean_against_itself():
    """Guards the comparison against vacuity: if it reported nothing
    because it reads nothing, this would still pass -- so it is paired
    with the cases above, which require it to speak up."""
    assert check_identical('results/pre_hardening',
                           'results/pre_hardening') == []
