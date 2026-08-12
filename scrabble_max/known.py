"""The known 1786-point construction (Bob Lucassen, NWL2023, May 2024).

Transcribed from the board screenshot in
https://blog.woogles.io/posts/2024-05-27-new-theoretical-highest-play-discovered/
Lowercase letters are blanks. The move: rack BENOPXZ, playing
OXYPHENBUTAZONE across row 1 (placing O,X,P,N,B,Z,E on A1,B1,D1,G1,H1,L1,O1).
"""

from .board import Move, parse_board
from .rules import Tile

PRE_BOARD_TEXT = """
..Y.HE..UTA.ON.
PEAR.hALT.WO.OS
AD.E..RAs..O..T
C..Q.URD...G..A
I..U..OD...A..B
F..AVOWER..MERL
I..L..IRE..E..I
C..I.UNLED.T..S
A..F..GI...E..H
T..Y...K......M
I..I...E......E
O..N..........N
N..G..........T
S.............S
...............
"""

MOVE = Move({
    (0, 0): Tile('O'),
    (0, 1): Tile('X'),
    (0, 3): Tile('P'),
    (0, 6): Tile('N'),
    (0, 7): Tile('B'),
    (0, 11): Tile('Z'),
    (0, 14): Tile('E'),
})

RACK = 'BENOPXZ'
EXPECTED_SCORE = 1786
EXPECTED_WORDS = {
    'OXYPHENBUTAZONE': 1458,
    'OPACIFICATIONS': 69,
    'XED': 11,
    'PREQUALIFYING': 34,
    'NARROWING': 13,
    'BLADDERLIKE': 57,
    'ZOOGAMETE': 31,
    'ESTABLISHMENTS': 63,
}


def pre_board():
    return parse_board(PRE_BOARD_TEXT)
