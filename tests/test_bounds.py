import pytest

from scrabble_max import bounds, known
from scrabble_max.board import Move, apply_move, parse_board
from scrabble_max.lexicon import load
from scrabble_max.rules import DL, DW, N, TL, TW, Tile, VALUES

LEX = load()


@pytest.fixture(scope='module')
def cb():
    br = bounds.best_rest_table(LEX)
    return bounds.cross_bound_table(br), br


def test_board_transpose_symmetry():
    # The completeness argument reduces vertical moves to horizontal ones
    # via transposition; that requires the premium layout to be symmetric.
    for s in (TW, DW, TL, DL):
        assert {(c, r) for r, c in s} == set(s)


def test_word_playability():
    assert bounds.word_playable('OXYPHENBUTAZONE')
    assert bounds.word_playable('PIZZAZZY') is False  # needs 4 Zs, only 1+2
    assert bounds.word_excess('ZYZZYVA') == 2  # 3 Zs -> 2 blanks: playable
    assert bounds.word_playable('ZYZZYVA')


def test_adjusted_sum_blanks():
    # ZYZZYVA: Z=10 x3 but only one real Z; two blanks worth 0.
    # letters Z,Y,Z,Z,Y,V,A -> real: Z10 + Y4*2 + V4 + A1 = 23
    assert bounds.adjusted_sum('ZYZZYVA') == 10 + 4 + 4 + 4 + 1
    assert bounds.raw_sum('ZYZZYVA') == 43


def test_best_rest_examples(cb):
    _, br = cb
    # A cross word hanging from row 0 must have its hook at position 0.
    # OXYPHENBUTAZONE starts with O and sums to 41 -> rest 40 available at O.
    assert br['O'][0] >= 40
    # ZOOGAMETE gives rest 21 for Z at row 0.
    assert br['Z'][0] >= 21
    # No lexicon word ENDS in Q... QAT etc start with Q; at row 14 the hook
    # must be the LAST letter. SUQ ends in Q so best_rest['Q'][14] exists.
    assert br['Q'][14] >= bounds.adjusted_sum('SUQ') - VALUES['Q']


def test_cross_bound_is_wm_times_sum(cb):
    table, br = cb
    # (0,0) is TW, lm=1: bound = 3*(v + rest)
    assert table['Z'][0][0] == 3 * (10 + br['Z'][0])
    # (0,3) is DL, wm=1: bound = 2*10 + rest
    assert table['Z'][0][3] == 2 * 10 + br['Z'][0]
    # cells where no cross word fits: bound 0 (never negative)
    for ch in table:
        for r in range(N):
            for c in range(N):
                assert table[ch][r][c] >= 0


def scenario_bound(word, row, c0, cbt):
    val, _ = bounds.relaxed_max_for_span(word, row, c0, cbt)
    return val


def test_bound_dominates_actual_simple_plays(cb):
    cbt, _ = cb
    # MUZJIKS canonical 128 opening: row 7, c0=1
    mv = Move({(7, 1 + i): Tile(ch) for i, ch in enumerate('MUZJIKS')})
    res = apply_move({}, mv, LEX)
    assert res.total == 128
    assert scenario_bound('MUZJIKS', 7, 1, cbt) >= 128

    # CART gap-fill play worth 12 (see test_rules)
    row = ['.'] * 15
    row[5] = 'C'
    row[8] = 'T'
    grid = parse_board('\n'.join(['.' * 15] * 7 + [''.join(row)] +
                                 ['.' * 15] * 7))
    res = apply_move(grid, Move({(7, 6): Tile('A'), (7, 7): Tile('R')}), LEX)
    assert scenario_bound('CART', 7, 5, cbt) >= res.total


def test_bound_dominates_known_1786(cb):
    cbt, _ = cb
    grid = known.pre_board()
    res = apply_move(grid, known.MOVE, LEX)
    assert res.total == 1786
    val, cols = bounds.relaxed_max_for_span('OXYPHENBUTAZONE', 0, 0, cbt)
    assert val >= 1786
    # and the relaxed optimum places on all three TWs
    assert {0, 7, 14} <= set(cols)


def test_geometry_cap_dominates_relaxed_max(cb):
    cbt, _ = cb
    cap, vmax = bounds.geometry_cap_table(LEX, cbt)
    for word, r, c0 in [('OXYPHENBUTAZONE', 0, 0), ('MUZJIKS', 7, 1),
                        ('QUIZZIFY', 0, 7), ('JUKEBOXES', 7, 0)]:
        val, _ = bounds.relaxed_max_for_span(word, r, c0, cbt)
        assert cap[r][c0][len(word)] >= val
