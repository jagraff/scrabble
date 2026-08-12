"""Board representation, move application, scoring, and full-legality verification.

Board text format used throughout: 15 lines of 15 chars.
  '.'          empty square
  'A'..'Z'     a normal tile
  'a'..'z'     a blank designated as that letter
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .rules import (CENTER, DISTRIBUTION, N, Tile, coord_name,
                    letter_multiplier, word_multiplier)


class IllegalPosition(Exception):
    pass


class IllegalMove(Exception):
    pass


def parse_board(text: str) -> dict[tuple[int, int], Tile]:
    rows = [ln.strip() for ln in text.strip().splitlines()]
    if len(rows) != N or any(len(r) != N for r in rows):
        raise ValueError("board text must be 15 lines of 15 chars")
    grid = {}
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == '.':
                continue
            if ch.isupper():
                grid[(r, c)] = Tile(ch, is_blank=False)
            elif ch.islower():
                grid[(r, c)] = Tile(ch.upper(), is_blank=True)
            else:
                raise ValueError(f"bad char {ch!r}")
    return grid


def board_text(grid: dict[tuple[int, int], Tile]) -> str:
    out = []
    for r in range(N):
        line = []
        for c in range(N):
            t = grid.get((r, c))
            if t is None:
                line.append('.')
            else:
                line.append(t.letter.lower() if t.is_blank else t.letter)
        out.append(''.join(line))
    return '\n'.join(out)


def runs(grid: dict[tuple[int, int], Tile]):
    """Yield every maximal run of >=2 consecutive tiles, as (cells, word)."""
    for horiz in (True, False):
        for a in range(N):
            b = 0
            while b < N:
                cell = (a, b) if horiz else (b, a)
                if cell in grid:
                    cells = []
                    while b < N:
                        cell = (a, b) if horiz else (b, a)
                        if cell not in grid:
                            break
                        cells.append(cell)
                        b += 1
                    if len(cells) >= 2:
                        yield cells, ''.join(grid[c].letter for c in cells)
                else:
                    b += 1


def tile_usage(grid: dict[tuple[int, int], Tile]) -> Counter:
    return Counter(t.inventory_key for t in grid.values())


def check_inventory(grid: dict[tuple[int, int], Tile]) -> None:
    usage = tile_usage(grid)
    for k, n in usage.items():
        if n > DISTRIBUTION[k]:
            raise IllegalPosition(
                f"uses {n} x {k!r} but only {DISTRIBUTION[k]} exist")


def check_connected(grid: dict[tuple[int, int], Tile]) -> None:
    if not grid:
        return
    if CENTER not in grid:
        raise IllegalPosition("center square is empty")
    seen = {CENTER}
    stack = [CENTER]
    while stack:
        r, c = stack.pop()
        for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nb in grid and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    if len(seen) != len(grid):
        raise IllegalPosition("board tiles are not all connected to center")


def check_static_position(grid: dict[tuple[int, int], Tile], lexicon: set[str],
                          allow_empty: bool = True) -> None:
    """A static position is legal iff every maximal run of >=2 is a word,
    no tile is isolated (every tile is in some run, unless it is the only
    tile... which is itself illegal since first move needs 2 tiles), tiles
    are connected through the center, and tile usage fits the bag."""
    if not grid:
        if allow_empty:
            return
        raise IllegalPosition("empty board")
    check_inventory(grid)
    check_connected(grid)
    if len(grid) == 1:
        raise IllegalPosition("a single tile can never be a legal position")
    for cells, word in runs(grid):
        if word not in lexicon:
            raise IllegalPosition(
                f"invalid word {word} at {coord_name(cells[0])}-"
                f"{coord_name(cells[-1])}")


@dataclass
class Move:
    """Tiles placed in a single turn."""
    placements: dict[tuple[int, int], Tile]

    def __post_init__(self):
        if not (1 <= len(self.placements) <= 7):
            raise IllegalMove("must place between 1 and 7 tiles")


@dataclass
class ScoredWord:
    cells: list[tuple[int, int]]
    word: str
    score: int


@dataclass
class MoveResult:
    total: int
    words: list[ScoredWord]
    bingo: bool
    new_grid: dict[tuple[int, int], Tile] = field(repr=False, default=None)


def score_word(cells, grid, placed_cells) -> int:
    s = 0
    wm = 1
    for cell in cells:
        t = grid[cell]
        if cell in placed_cells:
            s += t.value * letter_multiplier(cell)
            wm *= word_multiplier(cell)
        else:
            s += t.value
    return s * wm


def apply_move(grid: dict[tuple[int, int], Tile], move: Move,
               lexicon: set[str]) -> MoveResult:
    """Validate the move against the pre-move position and score it.

    The pre-move position itself is NOT validated here; call
    check_static_position first when that matters.
    """
    placed = move.placements
    for cell, t in placed.items():
        r, c = cell
        if not (0 <= r < N and 0 <= c < N):
            raise IllegalMove(f"cell {cell} off board")
        if cell in grid:
            raise IllegalMove(f"cell {coord_name(cell)} already occupied")

    rows = {r for r, _ in placed}
    cols = {c for _, c in placed}
    if len(rows) > 1 and len(cols) > 1:
        raise IllegalMove("placed tiles must lie in one row or one column")

    new_grid = dict(grid)
    new_grid.update(placed)

    # combined inventory check (pre-board tiles + placed tiles <= bag)
    check_inventory(new_grid)

    # The main line: if a single tile, prefer whichever direction forms a run.
    if len(rows) == 1 and (len(cols) > 1 or len(placed) == 1):
        horiz_candidates = [True, False] if len(placed) == 1 else [True]
    else:
        horiz_candidates = [False]

    def line_run(cell, horiz):
        r, c = cell
        cells = [cell]
        if horiz:
            cc = c - 1
            while (r, cc) in new_grid:
                cells.insert(0, (r, cc)); cc -= 1
            cc = c + 1
            while (r, cc) in new_grid:
                cells.append((r, cc)); cc += 1
        else:
            rr = r - 1
            while (rr, c) in new_grid:
                cells.insert(0, (rr, c)); rr -= 1
            rr = r + 1
            while (rr, c) in new_grid:
                cells.append((rr, c)); rr += 1
        return cells

    # main run must contain all placed cells and be contiguous
    any_cell = next(iter(placed))
    main_cells = None
    for horiz in horiz_candidates:
        cand = line_run(any_cell, horiz)
        if all(c in cand for c in placed):
            main_cells = cand
            main_horiz = horiz
            break
    if main_cells is None:
        raise IllegalMove("placed tiles do not form a single contiguous run")

    first_move = not grid
    if first_move:
        if CENTER not in placed:
            raise IllegalMove("first move must cover the center square")
    else:
        # must connect: main run includes a pre-existing tile, or some placed
        # tile is adjacent to a pre-existing tile
        touches = any(c in grid for c in main_cells)
        if not touches:
            for (r, c) in placed:
                for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                    if nb in grid:
                        touches = True
        if not touches:
            raise IllegalMove("move does not connect to existing tiles")

    # collect all new words: the main run (if >=2) plus cross runs at placed
    new_words: list[list[tuple[int, int]]] = []
    if len(main_cells) >= 2:
        new_words.append(main_cells)
    for cell in placed:
        cross = line_run(cell, not main_horiz)
        if len(cross) >= 2 and cross != main_cells:
            new_words.append(cross)
    # dedupe (single-tile play can rediscover same run)
    seen = set()
    uniq = []
    for cells in new_words:
        key = (cells[0], cells[-1])
        if key not in seen:
            seen.add(key)
            uniq.append(cells)
    new_words = uniq

    if not new_words:
        raise IllegalMove("move forms no word of length >= 2")

    scored = []
    total = 0
    placed_set = set(placed)
    for cells in new_words:
        word = ''.join(new_grid[c].letter for c in cells)
        if word not in lexicon:
            raise IllegalMove(f"word {word} not in lexicon")
        s = score_word(cells, new_grid, placed_set)
        scored.append(ScoredWord(cells, word, s))
        total += s

    bingo = len(placed) == 7
    if bingo:
        total += 50
    return MoveResult(total=total, words=scored, bingo=bingo,
                      new_grid=new_grid)
