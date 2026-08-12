import pytest

from scrabble_max import known
from scrabble_max.board import (IllegalMove, IllegalPosition, Move,
                                apply_move, check_static_position,
                                parse_board, runs, tile_usage)
from scrabble_max.lexicon import load
from scrabble_max.rules import (DISTRIBUTION, DL, TL, TW, DW, VALUES, N,
                                Tile, letter_multiplier, word_multiplier)

LEX = load()


def empty():
    return {}


def test_tile_values_and_distribution():
    assert sum(DISTRIBUTION.values()) == 100
    # total face value of the full bag is the well-known 187
    assert sum(VALUES[k] * n for k, n in DISTRIBUTION.items()) == 187


def test_premium_layout_spot_checks():
    # canonical squares (row, col) 0-indexed
    assert (0, 0) in TW and (0, 7) in TW and (7, 0) in TW and (14, 14) in TW
    assert (7, 7) in DW and (1, 1) in DW and (13, 13) in DW
    assert (1, 5) in TL and (5, 5) in TL and (9, 13) in TL and (13, 9) in TL
    assert (0, 3) in DL and (0, 11) in DL and (3, 0) in DL and (7, 3) in DL
    assert (2, 8) in DL and (6, 6) in DL and (8, 8) in DL and (14, 11) in DL
    assert word_multiplier((0, 0)) == 3
    assert word_multiplier((7, 7)) == 2
    assert word_multiplier((5, 5)) == 1
    assert letter_multiplier((5, 5)) == 3
    assert letter_multiplier((0, 3)) == 2
    assert letter_multiplier((0, 0)) == 1
    # counts
    assert len(TW) == 8 and len(DW) == 17 and len(TL) == 12 and len(DL) == 24


def test_first_move_scoring_simple():
    # QUIZ played at H8-K8 (row 7, cols 7..10), first move.
    mv = Move({(7, 7): Tile('Q'), (7, 8): Tile('U'), (7, 9): Tile('I'),
               (7, 10): Tile('Z')})
    res = apply_move(empty(), mv, LEX)
    # Q10 U1 I1 Z10 = 22, center doubles the word -> 44
    assert res.total == 44
    assert not res.bingo


def test_first_move_must_cover_center():
    mv = Move({(0, 0): Tile('A'), (0, 1): Tile('T')})
    with pytest.raises(IllegalMove):
        apply_move(empty(), mv, LEX)


def test_bingo_bonus_and_double_letter():
    # MUZJIKS placed at cols 7..13 of row 8: I lands on the (7,11) DLS.
    letters = 'MUZJIKS'
    mv = Move({(7, 7 + i): Tile(ch) for i, ch in enumerate(letters)})
    res = apply_move(empty(), mv, LEX)
    base = 3 + 1 + 10 + 8 + 1 + 5 + 1  # 29
    assert res.total == (base + 1) * 2 + 50  # I doubled -> 60 + bingo = 110


def test_muzjiks_canonical_128_opening():
    # The famous maximum legal opening: MUZJIKS with Z on the (7,3) DLS.
    letters = 'MUZJIKS'
    mv = Move({(7, 1 + i): Tile(ch) for i, ch in enumerate(letters)})
    res = apply_move(empty(), mv, LEX)
    assert res.total == 128
    assert res.bingo


def test_blank_scores_zero():
    mv = Move({(7, 7): Tile('Q'), (7, 8): Tile('U'), (7, 9): Tile('I'),
               (7, 10): Tile('Z', is_blank=True)})
    res = apply_move(empty(), mv, LEX)
    # Q10 U1 I1 z0 = 12 doubled = 24
    assert res.total == 24


def test_cross_word_scoring_and_premium_shared():
    # Set up HORN at F8-I8 (row 7, cols 5-8) ... simpler: use a canonical
    # two-move sequence and check the second move's score.
    # Move 1: BOAT at H8-H11 vertical? Keep it simple horizontally.
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['.....BOAT......'] +
                                 ['.' * 15] * 7))
    # BOAT occupies (7,5)-(7,8). Play OX vertically: O at (8,8) under T? that
    # makes TO down... Instead play "AB" ... use a clean case:
    # place 'S' at (7,9) making BOATS.
    res = apply_move(grid, Move({(7, 9): Tile('S')}), LEX)
    # B3 O1 A1 T1 S1 = 7, no premium under (7,9)
    assert res.total == 7
    assert [w.word for w in res.words] == ['BOATS']


def test_cross_words_all_scored():
    # Board with CAT horizontally at (7,6)-(7,8); play "TAB" vertically? Use
    # a known simple crossing: play HA with H at (6,7) A at (8,7)? not one line
    # contiguous through existing A at (7,7).
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['......CAT......'] +
                                 ['.' * 15] * 7))
    # CAT at cols 6,7,8. Place H at (6,7) and S at (8,7): vertical H-A-S
    # through the A of CAT. Wait A is at (7,7). H(6,7), A(7,7) existing,
    # S(8,7) -> HAS.
    res = apply_move(grid, Move({(6, 7): Tile('H'), (8, 7): Tile('S')}), LEX)
    # HAS: H4 A1 S1 = 6; (6,7) no premium... (6,7)? row6 col7: not premium.
    # (8,7): not premium. But A sits on center DW — premium NOT re-used
    # because it's not a newly placed tile.
    assert res.total == 6
    assert [w.word for w in res.words] == ['HAS']


def test_premium_only_counts_for_new_tiles():
    # Word crossing center: center DW must not double a later word.
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['......CAT......'] +
                                 ['.' * 15] * 7))
    # extend CAT to CATS: S at (7,9)
    res = apply_move(grid, Move({(7, 9): Tile('S')}), LEX)
    assert res.total == 3 + 1 + 1 + 1  # no doubling


def test_disconnected_move_illegal():
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['......CAT......'] +
                                 ['.' * 15] * 7))
    with pytest.raises(IllegalMove):
        apply_move(grid, Move({(0, 0): Tile('A'), (0, 1): Tile('T')}), LEX)


def test_gap_fill_move():
    # Existing: C..T in a row with gaps; placing A,R to make CART? Use
    # C(7,5) T(7,8): place A(7,6) R(7,7)? CART: C A R T.
    row = ['.'] * 15
    row[5] = 'C'
    row[8] = 'T'
    grid_txt = ['.' * 15] * 7 + [''.join(row)] + ['.' * 15] * 7
    grid = parse_board('\n'.join(grid_txt))
    res = apply_move(grid, Move({(7, 6): Tile('A'), (7, 7): Tile('R')}), LEX)
    # C3 A1 R1 T1 = 6, R on center DW -> 12
    assert res.total == 12
    assert [w.word for w in res.words] == ['CART']


def test_noncontiguous_result_illegal():
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['......CAT......'] +
                                 ['.' * 15] * 7))
    with pytest.raises(IllegalMove):
        # leaves a hole at (7,10)
        apply_move(grid, Move({(7, 9): Tile('S'), (7, 11): Tile('A')}), LEX)


def test_two_directions_illegal():
    with pytest.raises(IllegalMove):
        apply_move(empty(), Move({(7, 7): Tile('A'), (8, 8): Tile('B')}), LEX)


def test_inventory_enforced():
    # three Zs total (one placed + two on board as non-blanks) is impossible
    row = ['.'] * 15
    row[6] = 'Z'
    row[7] = 'A'
    grid_txt = ['.' * 15] * 6 + [''.join(row)] + ['.' * 15] * 8
    grid = parse_board('\n'.join(grid_txt))  # ZA at (6,6),(6,7)
    grid[(8, 6)] = Tile('Z')  # artificial second Z
    with pytest.raises(IllegalPosition):
        apply_move(grid, Move({(7, 6): Tile('Z')}), LEX)


def test_static_position_checks():
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['......QQT......'] +
                                 ['.' * 15] * 7))
    with pytest.raises(IllegalPosition):
        check_static_position(grid, LEX)  # QQT not a word + two Qs

    ok = parse_board('\n'.join(['.' * 15] * 7 +
                               ['......CAT......'] +
                               ['.' * 15] * 7))
    check_static_position(ok, LEX)

    off_center = parse_board('\n'.join(['CAT............'] +
                                       ['.' * 15] * 14))
    with pytest.raises(IllegalPosition):
        check_static_position(off_center, LEX)


def test_one_tile_play_scores_both_directions():
    # AH vertical + AB horizontal sharing the placed tile? Construct:
    # A at (7,7), B at (7,8) => AB. H existing at (8,7)? then placing A...
    # Simpler: existing words BOA (7,5)-(7,7) and place T at (7,8) with
    # existing vertical (6,8)=A? Let's do explicit:
    grid = parse_board('\n'.join(['.' * 15] * 7 +
                                 ['.....BOA.......'] +
                                 ['.' * 15] * 7))
    grid[(6, 8)] = Tile('U')
    grid[(8, 8)] = Tile('B')  # vertical U _ B at col 8 rows 6..8
    # not a legal static position (U and B floating) but apply_move doesn't
    # care; placing T at (7,8) forms BOAT and TUB? no: vertical is U,T,B = UTB
    # not a word. Use S: vertical U S B no. Pick better: vertical run should
    # form C_B? Let's place T with vertical neighbors making "UTB" fail ->
    # choose grid vertical letters so cross word is real: O above, E below ->
    # OTE? no. Use existing (6,8)='E' (8,8)='A': E T A = ETA? valid? yes ETA.
    del grid[(6, 8)], grid[(8, 8)]
    grid[(6, 8)] = Tile('E')
    grid[(8, 8)] = Tile('A')
    res = apply_move(grid, Move({(7, 8): Tile('T')}), LEX)
    words = sorted(w.word for w in res.words)
    assert words == ['BOAT', 'ETA']
    # BOAT = 3+1+1+1 = 6; ETA = 1+1+1 = 3
    assert res.total == 9


def test_seven_distinct_runs():
    grid = known.pre_board()
    # sanity: every run on the pre-board is a valid word
    check_static_position(grid, LEX)


def test_known_1786_construction():
    grid = known.pre_board()
    check_static_position(grid, LEX)
    res = apply_move(grid, known.MOVE, LEX)
    assert res.bingo
    got = {w.word: w.score for w in res.words}
    assert got == known.EXPECTED_WORDS
    assert res.total == known.EXPECTED_SCORE
    # rack check
    rack = sorted(t.letter for t in known.MOVE.placements.values())
    assert ''.join(rack) == known.RACK
    # post-move inventory
    from scrabble_max.board import check_inventory
    check_inventory(res.new_grid)
