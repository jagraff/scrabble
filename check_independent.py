#!/usr/bin/env python3
"""An independent checker for the 1,786 result.

Reads the committed artifacts and re-derives everything that can be
re-derived without a solver, from a separate implementation of the rules.

**It imports nothing from `scrabble_max`.** That is the whole point. A
checker that shares code with the thing it checks inherits its bugs, and
this project's defects have been in encoding, bookkeeping and
orchestration rather than in CP-SAT -- exactly the layer a shared import
would fail to test.

Where the package derives something one way, this derives it another:

  * the premium layout is written out as the explicit 15x15 board diagram,
    against the package's quadrant-and-mirror construction. A bug in
    `_mirror` cannot hide from a transcription of the physical board.
  * scoring, word legality, connectivity and inventory are reimplemented
    from the rules, not adapted.
  * the per-configuration ceiling is recomputed with a *conservative*
    blank loss -- an under-estimate of what blanks forfeit, which yields a
    larger bound. A larger bound is the safe direction: if the weaker
    bound already falls at or below the threshold, the refutation holds
    however the exact loss is computed.

What it does NOT check, and says so in its output: anything that needs a
solver. The ~790 CP-SAT infeasibility claims are outside its reach and
would need a DRAT/LRAT layer. What it covers is the other ~1,063
refutations, the witness, the caps, and all the bookkeeping.

    python3 check_independent.py            # against results/
    python3 check_independent.py --dir results/pre_hardening
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter

N = 15

# The standard Scrabble board, transcribed from the physical layout.
# T = triple word, D = double word, t = triple letter, d = double letter.
BOARD = [
    'T..d...T...d..T',
    '.D...t...t...D.',
    '..D...d.d...D..',
    'd..D...d...D..d',
    '....D.....D....',
    '.t...t...t...t.',
    '..d...d.d...d..',
    'T..d...D...d..T',
    '..d...d.d...d..',
    '.t...t...t...t.',
    '....D.....D....',
    'd..D...d...D..d',
    '..D...d.d...D..',
    '.D...t...t...D.',
    'T..d...T...d..T',
]

VALUES = {
    'A': 1, 'B': 3, 'C': 3, 'D': 2, 'E': 1, 'F': 4, 'G': 2, 'H': 4,
    'I': 1, 'J': 8, 'K': 5, 'L': 1, 'M': 3, 'N': 1, 'O': 1, 'P': 3,
    'Q': 10, 'R': 1, 'S': 1, 'T': 1, 'U': 1, 'V': 4, 'W': 4, 'X': 8,
    'Y': 4, 'Z': 10,
}
DISTRIBUTION = {
    'A': 9, 'B': 2, 'C': 2, 'D': 4, 'E': 12, 'F': 2, 'G': 3, 'H': 2,
    'I': 9, 'J': 1, 'K': 1, 'L': 4, 'M': 2, 'N': 6, 'O': 8, 'P': 2,
    'Q': 1, 'R': 6, 'S': 4, 'T': 6, 'U': 4, 'V': 2, 'W': 2, 'X': 1,
    'Y': 2, 'Z': 1,
}
BLANKS = 2
CENTER = (7, 7)
RACK = 7


def wm(cell):
    ch = BOARD[cell[0]][cell[1]]
    return 3 if ch == 'T' else 2 if ch == 'D' else 1


def lm(cell):
    ch = BOARD[cell[0]][cell[1]]
    return 3 if ch == 't' else 2 if ch == 'd' else 1


class Check:
    """Accumulates results so one failure does not hide the rest."""

    def __init__(self):
        self.passed, self.failed, self.skipped, self.notes = 0, [], [], []

    def ok(self, cond, label, detail=''):
        if cond:
            self.passed += 1
        else:
            self.failed.append(f'{label}: {detail}')
        return bool(cond)

    def skip(self, label, why):
        self.skipped.append(f'{label}: {why}')

    def note(self, msg):
        self.notes.append(msg)


# ---------------------------------------------------------------- board ----

def sanity_of_the_board(k):
    """The transcribed layout must be the real Scrabble board."""
    counts = Counter(ch for row in BOARD for ch in row)
    k.ok(len(BOARD) == N and all(len(r) == N for r in BOARD),
         'board is 15x15', f'{len(BOARD)} rows')
    k.ok(counts['T'] == 8, 'eight triple-word squares', str(counts['T']))
    k.ok(counts['D'] == 17, 'seventeen double-word squares (centre included)',
         str(counts['D']))
    k.ok(counts['t'] == 12, 'twelve triple-letter squares', str(counts['t']))
    k.ok(counts['d'] == 24, 'twenty-four double-letter squares',
         str(counts['d']))
    k.ok(BOARD[7][7] == 'D', 'centre is a double-word square', BOARD[7][7])
    # symmetry the board is supposed to have
    k.ok(all(BOARD[r][c] == BOARD[c][r] for r in range(N) for c in range(N)),
         'board is symmetric under transposition')
    k.ok(all(BOARD[r][c] == BOARD[N - 1 - r][c]
             for r in range(N) for c in range(N)),
         'board is symmetric top-to-bottom')
    k.ok(sum(DISTRIBUTION.values()) + BLANKS == 100,
         'the tile set is 100 tiles',
         str(sum(DISTRIBUTION.values()) + BLANKS))
    k.ok(sum(VALUES[c] * n for c, n in DISTRIBUTION.items()) == 187,
         'the tile set is worth 187 points',
         str(sum(VALUES[c] * n for c, n in DISTRIBUTION.items())))


def cross_check_constants(k):
    """Compare against the package's own constants.

    Reads them as text rather than importing, so a disagreement is
    reported instead of silently adopted."""
    try:
        with open('scrabble_max/rules.py') as f:
            src = f.read()
    except OSError:
        k.skip('constants vs scrabble_max/rules.py', 'file not readable')
        return
    ns = {}
    body = src.split('@dataclass')[0]
    body = body.replace('from __future__ import annotations', '')
    body = re.sub(r'^from typing import.*$', '', body, flags=re.M)
    body = re.sub(r'^from dataclasses import.*$', '', body, flags=re.M)
    try:
        exec(compile(body, 'rules', 'exec'), ns)
    except Exception as e:                                # pragma: no cover
        k.skip('constants vs scrabble_max/rules.py', f'could not evaluate: {e}')
        return
    theirs_v = {a: b for a, b in ns['VALUES'].items() if a != '?'}
    theirs_d = {a: b for a, b in ns['DISTRIBUTION'].items() if a != '?'}
    k.ok(theirs_v == VALUES, 'tile values agree with the package',
         str({a: (theirs_v.get(a), VALUES.get(a)) for a in set(theirs_v) |
              set(VALUES) if theirs_v.get(a) != VALUES.get(a)}))
    k.ok(theirs_d == DISTRIBUTION, 'tile distribution agrees with the package')
    mine_tw = {(r, c) for r in range(N) for c in range(N)
               if BOARD[r][c] == 'T'}
    mine_dw = {(r, c) for r in range(N) for c in range(N)
               if BOARD[r][c] == 'D'}
    mine_tl = {(r, c) for r in range(N) for c in range(N)
               if BOARD[r][c] == 't'}
    mine_dl = {(r, c) for r in range(N) for c in range(N)
               if BOARD[r][c] == 'd'}
    k.ok(set(ns['TW']) == mine_tw, 'triple-word squares agree with the package',
         f'package-only {sorted(set(ns["TW"]) - mine_tw)}, '
         f'diagram-only {sorted(mine_tw - set(ns["TW"]))}')
    k.ok(set(ns['DW']) == mine_dw, 'double-word squares agree')
    k.ok(set(ns['TL']) == mine_tl, 'triple-letter squares agree')
    k.ok(set(ns['DL']) == mine_dl, 'double-letter squares agree')


# --------------------------------------------------------------- scoring ---

def parse_board(text):
    """Lowercase letters are blanks, '.' is empty."""
    grid = {}
    rows = [ln.strip() for ln in text.strip().splitlines()]
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != '.':
                grid[(r, c)] = (ch.upper(), ch.islower())
    return grid


def runs_of(grid):
    """Every maximal run of two or more tiles, as (cells, word)."""
    out = []
    for horiz in (True, False):
        for a in range(N):
            cur = []
            for b in range(N + 1):
                cell = (a, b) if horiz else (b, a)
                if b < N and cell in grid:
                    cur.append(cell)
                else:
                    if len(cur) >= 2:
                        out.append((list(cur),
                                    ''.join(grid[x][0] for x in cur)))
                    cur = []
    return out


def score_play(grid_before, placements):
    """Score a play from first principles. Returns (total, words)."""
    grid = dict(grid_before)
    grid.update(placements)
    placed = set(placements)
    total, words = 0, []
    for cells, word in runs_of(grid):
        if not (placed & set(cells)):
            continue
        s, mult = 0, 1
        for cell in cells:
            letter, blank = grid[cell]
            v = 0 if blank else VALUES[letter]
            if cell in placed:
                s += v * lm(cell)
                mult *= wm(cell)
            else:
                s += v
        total += s * mult
        words.append((word, s * mult))
    if len(placements) == RACK:
        total += 50
    return total, words


def position_is_legal(grid, lexicon, k, label):
    ok = True
    for cells, word in runs_of(grid):
        if word not in lexicon:
            ok = k.ok(False, label, f'{word} is not in the lexicon') and ok
            break
    if grid and CENTER not in grid:
        ok = k.ok(False, label, 'the centre square is empty') and ok
    seen, stack = {CENTER} if CENTER in grid else set(), \
        [CENTER] if CENTER in grid else []
    while stack:
        r, c = stack.pop()
        for d in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (r + d[0], c + d[1])
            if n in grid and n not in seen:
                seen.add(n)
                stack.append(n)
    if grid and len(seen) != len(grid):
        ok = k.ok(False, label,
                  f'{len(grid) - len(seen)} tiles are not connected to the '
                  f'centre') and ok
    used = Counter()
    for letter, blank in grid.values():
        used['?' if blank else letter] += 1
    for ch, n in used.items():
        limit = BLANKS if ch == '?' else DISTRIBUTION[ch]
        if n > limit:
            ok = k.ok(False, label, f'{n} copies of {ch}, only {limit} exist') \
                and ok
    return ok


# -------------------------------------------------------------- artifacts --

def load_lexicon(path='data/NWL2023.txt'):
    with open(path) as f:
        return {ln.strip().upper() for ln in f if ln.strip()}


def check_the_record_play(k, lexicon, d):
    """The anchor: the 1,786 play, scored from first principles."""
    path = 'scrabble_max/known.py'
    try:
        with open(path) as f:
            src = f.read()
    except OSError:
        k.skip('record play', 'known.py not readable')
        return
    m = re.search(r'PRE_BOARD_TEXT = """(.*?)"""', src, re.S)
    if not m:
        k.skip('record play', 'could not read the pre-board')
        return
    grid = parse_board(m.group(1))
    placements = {}
    body = src.split('MOVE = Move({')[1].split('})')[0]
    for r, c, ch in re.findall(r'\((\d+),\s*(\d+)\):\s*Tile\(\'([A-Z])\'\)',
                               body):
        placements[(int(r), int(c))] = (ch, False)
    k.ok(len(placements) == 7, 'the record play places seven tiles',
         str(len(placements)))
    position_is_legal(grid, lexicon, k, 'pre-move position is legal')
    total, words = score_play(grid, placements)
    k.ok(total == 1786, 'the record play scores exactly 1786', str(total))
    after = dict(grid)
    after.update(placements)
    position_is_legal(after, lexicon, k, 'post-move position is legal')
    k.note(f'independent scoring of the record play: {total} '
           f'({len(words)} words)')


def check_the_witness(k, lexicon, d):
    """Replay the constructed game and check where it lands."""
    log = 'results/reachability.log'
    if not os.path.exists(log):
        k.skip('game witness', f'{log} not present')
        return
    moves = []
    for line in open(log):
        m = re.match(r'\s*\d+\.\s+(.+?)\s+->', line)
        if not m:
            continue
        placements = {}
        for cell in m.group(1).split(','):
            where, face = cell.split('=')
            face = face.strip()
            mm = re.fullmatch(r'([A-O])(\d{1,2})', where.strip())
            placements[(int(mm.group(2)) - 1,
                        ord(mm.group(1)) - ord('A'))] = (face[0],
                                                         face.endswith('?'))
        moves.append(placements)
    k.ok(len(moves) == 25, 'the build-up is 25 moves', str(len(moves)))

    grid, bag = {}, Counter(DISTRIBUTION)
    bag['?'] = BLANKS
    legal = True
    for i, placements in enumerate(moves, 1):
        if not 1 <= len(placements) <= RACK:
            legal = k.ok(False, 'every move places 1..7 tiles',
                         f'move {i} places {len(placements)}') and legal
        for letter, blank in placements.values():
            bag['?' if blank else letter] -= 1
        grid.update(placements)
    k.ok(legal, 'move sizes are within a rack')
    k.ok(all(v >= 0 for v in bag.values()),
         'the build-up never draws a tile the bag lacks',
         str({c: v for c, v in bag.items() if v < 0}))
    position_is_legal(grid, lexicon, k, 'the built position is legal')

    src = open('scrabble_max/known.py').read()
    target = parse_board(re.search(r'PRE_BOARD_TEXT = """(.*?)"""',
                                   src, re.S).group(1))
    k.ok(grid == target, 'the replay reaches the record pre-board exactly',
         f'{len(set(target) - set(grid))} missing, '
         f'{len(set(grid) - set(target))} extra')


def check_geometry_caps(k, lexicon, d):
    """NOT a re-derivation of the stage-A caps. A sanity bound only.

    Theorem 1 eliminates 1,573 of 1,575 geometries by showing their caps
    fall at or below 1,786. Reproducing that independently means rebuilding
    the per-(cell, letter) cross-bound table the package derives from the
    lexicon, which decides how much a perpendicular word through each cell
    can contribute. A crude bound -- fourteen tiles at the maximum value,
    tripled -- is so generous that all 1,575 spans survive it, which
    eliminates nothing and would be reported as agreement if this function
    pretended otherwise.

    So it checks only the direction that can be checked cheaply, and
    declares the rest out of scope. This is the largest gap in the
    checker.
    """
    best_word = {}
    for w in lexicon:
        if len(w) <= N:
            s = sum(VALUES[c] for c in w)
            if s > best_word.get(len(w), -1):
                best_word[len(w)] = s
    # A necessary condition: the record's own geometry must survive any
    # valid cap. A cap that eliminated it would be refuting a play that
    # exists.
    cells = [(0, c) for c in range(N)]
    mult = 1
    for cell in cells:
        mult *= wm(cell)
    lower = mult * best_word.get(N, 0)
    k.ok(lower >= 0 and mult == 27,
         'the row-0 full span carries all three triple-word squares',
         f'word multiplier {mult}, expected 27')
    k.note(f'best 15-letter word value in the lexicon: {best_word.get(N)}; '
           f'row-0 span multiplier {mult}')
    k.skip('stage-A geometry caps (Theorem 1)',
           'not re-derived -- needs an independent cross-bound table; the '
           'crude bound available here eliminates 0 of 1575 spans and so '
           'confirms nothing')


def _config_key(cfg):
    placed = tuple(sorted(int(c) for c in (cfg.get('placed') or ())))
    crosses = tuple(sorted((str(a), b)
                           for a, b in (cfg.get('crosses') or {}).items()))
    return placed, crosses


TW_COLS, DL_COLS = (0, 7, 14), (3, 11)


def forced_blank_loss(word, placed, crosses):
    """The blanks a configuration forces, and the least they can cost.

    Re-derived from the mathematics rather than the package's code. A
    configuration pins the whole main word and every cross-word remainder,
    so the multiset of tiles it needs is fixed. Any letter needed beyond
    its supply must be a blank, a blank scores nothing, and the cheapest
    arrangement puts the blanks on the lowest-scoring occurrences of that
    letter -- so the minimum loss is the sum of the k smallest per-copy
    contributions.

    Each occurrence's contribution:
      * a main-word letter scores value x letter-multiplier x the whole
        word multiplier, and again -- at that column's own multipliers --
        inside its cross word if it hooks one;
      * a cross-remainder letter scores value x that column's word
        multiplier.

    `placed` matters: a double-letter square doubles only a tile the mover
    places, so charging the doubled figure for a pre-existing board tile
    over-states the loss. Over-stating lowers the ceiling and can refute a
    configuration that is not refutable, which is the unsound direction.

    Returns (forced, loss), or None when more than two blanks are needed
    and the configuration cannot exist at all.
    """
    placed = set(int(c) for c in placed)
    crosses = {int(a): b for a, b in crosses.items()}
    wm_prod = 1
    for c in TW_COLS:
        if c in placed:
            wm_prod *= 3

    copies = Counter(word)
    options = {}
    for c, ch in enumerate(word):
        el = 2 if (c in DL_COLS and c in placed) else 1
        m = 3 if c in TW_COLS else 1
        loss = VALUES[ch] * el * wm_prod
        if c in crosses:
            loss += m * VALUES[ch] * el
        options.setdefault(ch, []).append(loss)
    for c, w in crosses.items():
        m = 3 if c in TW_COLS else 1
        for ch in w[1:]:
            copies[ch] += 1
            options.setdefault(ch, []).append(VALUES[ch] * m)

    forced, loss = 0, 0
    for ch, n in copies.items():
        excess = n - DISTRIBUTION[ch]
        if excess > 0:
            forced += excess
            loss += sum(sorted(options[ch])[:excess])
    if forced > BLANKS:
        return None
    return forced, loss


def exact_ceiling(word, placed, crosses):
    """A proven upper bound on any board realising this configuration."""
    fb = forced_blank_loss(word, placed, crosses)
    if fb is None:
        return None
    _, loss = fb
    placed = set(int(c) for c in placed)
    crosses = {int(a): b for a, b in crosses.items()}
    mult = 1
    for c in TW_COLS:
        if c in placed:
            mult *= 3
    total = mult * sum(
        VALUES[ch] * (2 if (c in DL_COLS and c in placed) else 1)
        for c, ch in enumerate(word))
    for c, w in crosses.items():
        m = 3 if c in TW_COLS else 1
        el = 2 if c in DL_COLS else 1
        total += m * (VALUES[word[c]] * el + sum(VALUES[ch] for ch in w[1:]))
    if len(placed) == RACK:
        total += 50
    return total - loss


def check_tier3_bookkeeping(k, lexicon, d):
    cfg_path = os.path.join(d, 'tier3_configs.json')
    check_dir = os.path.join(d, 'tier3_checks')
    if not os.path.exists(cfg_path):
        k.skip('tier-3 bookkeeping', f'{cfg_path} not present')
        return
    payload = json.load(open(cfg_path))
    threshold = payload.get('threshold', 1786)
    enumerated, incomplete = {}, []
    for p in payload['patterns']:
        if not p.get('complete'):
            incomplete.append(tuple(p['placed']))
        for c in p.get('configs') or []:
            enumerated[_config_key(c)] = c
    k.ok(not incomplete, 'every pattern enumerated to completion',
         f'incomplete: {incomplete}')

    verdicts, above, undecided = {}, [], []
    for path in sorted(glob.glob(os.path.join(check_dir, '*.json'))):
        if os.path.basename(path) == 'decomposed.json':
            continue
        for r in json.load(open(path)):
            verdicts[_config_key(r.get('config') or {})] = r
            if (r.get('value') or 0) > threshold:
                above.append(r)
            elif r.get('status') != 'INFEASIBLE':
                undecided.append(r)
    if not verdicts:
        k.skip('tier-3 verdicts', f'no verdict files under {check_dir}')
        return

    decomposed = {}
    dp = os.path.join(check_dir, 'decomposed.json')
    if os.path.exists(dp):
        for rec in json.load(open(dp)):
            decomposed[_config_key(rec)] = rec.get('refuted')
    still = [r for r in undecided
             if not decomposed.get(_config_key(r.get('config') or {}))]

    k.ok(not above, 'no configuration scores above the threshold',
         f'{len(above)} do')
    k.ok(not still, 'no configuration is left undecided',
         f'{len(still)} are')
    missing = set(enumerated) - set(verdicts)
    extra = set(verdicts) - set(enumerated)
    k.ok(not missing, 'every enumerated configuration has a verdict',
         f'{len(missing)} have none')
    k.ok(not extra, 'every verdict belongs to an enumerated configuration',
         f'{len(extra)} do not')
    k.note(f'tier 3: {len(enumerated)} configurations, {len(verdicts)} '
           f'verdicts, {len(decomposed)} closed by decomposition')

    # Re-derive the refutations that need no solver.
    word = 'OXYPHENBUTAZONE'
    confirmed = solver = impossible = disagreed = 0
    examples = []
    for key, r in verdicts.items():
        cfg = r.get('config') or {}
        placed = cfg.get('placed') or []
        crosses = {str(a): b for a, b in (cfg.get('crosses') or {}).items()}
        ceil = exact_ceiling(word, placed, crosses)
        if ceil is None:
            impossible += 1
        elif ceil <= threshold:
            confirmed += 1
        else:
            solver += 1
        # Where the package recorded its own ceiling, the two derivations
        # must agree exactly. This is the cross-check that would catch a
        # mistake in either.
        rec = r.get('bound')
        if ceil is not None and rec is not None and r.get('reason'):
            if int(rec) != int(ceil):
                disagreed += 1
                if len(examples) < 3:
                    examples.append(f'{sorted(placed)} recorded {rec} '
                                    f'vs re-derived {ceil}')
    k.ok(disagreed == 0,
         'the re-derived ceiling matches the recorded one everywhere',
         f'{disagreed} disagree; e.g. ' + '; '.join(examples))
    k.ok(confirmed + impossible > 0,
         'the ceiling re-derivation actually refutes something',
         'it refuted nothing, so it is not testing what it claims')
    k.note(f'independently refuted with no solver: {confirmed} by exact '
           f'ceiling, {impossible} impossible on blanks alone; '
           f'{solver} rest on a CP-SAT infeasibility claim this checker '
           f'cannot verify')


def check_hashes(k, d):
    man = os.path.join(d, 'MANIFEST.json')
    if not os.path.exists(man):
        k.skip('manifest', f'{man} not present -- run has not been certified')
        return
    m = json.load(open(man))
    bad = 0
    groups = [m.get('cells', []), m.get('artifacts', []),
              (m.get('refutation') or {}).get('files', [])]
    for g in groups:
        for rec in g:
            p, want = rec.get('file'), rec.get('sha256')
            if not want or not os.path.exists(p):
                bad += 1
                continue
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
            if h.hexdigest() != want:
                bad += 1
    k.ok(bad == 0, 'every file the manifest names hashes as recorded',
         f'{bad} do not')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', default='results')
    ap.add_argument('--lexicon', default='data/NWL2023.txt')
    a = ap.parse_args()

    k = Check()
    print('independent check -- shares no code with scrabble_max\n')
    sanity_of_the_board(k)
    cross_check_constants(k)
    lexicon = load_lexicon(a.lexicon)
    h = hashlib.sha256(open(a.lexicon, 'rb').read()).hexdigest()
    k.note(f'lexicon: {len(lexicon)} words, sha256 {h[:16]}')
    check_the_record_play(k, lexicon, a.dir)
    check_the_witness(k, lexicon, a.dir)
    check_geometry_caps(k, lexicon, a.dir)
    check_tier3_bookkeeping(k, lexicon, a.dir)
    check_hashes(k, a.dir)

    for n in k.notes:
        print(f'  - {n}')
    print()
    print(f'{k.passed} checks passed, {len(k.failed)} failed, '
          f'{len(k.skipped)} skipped')
    for s in k.skipped:
        print(f'  SKIPPED  {s}')
    for f in k.failed:
        print(f'  FAILED   {f}')
    print()
    if k.failed:
        print('INDEPENDENT CHECK FAILED')
        return 1
    print('everything this checker can re-derive, it re-derived and agrees.')
    print('It does not verify CP-SAT infeasibility claims; those need a')
    print('DRAT/LRAT layer and are outside its scope by construction.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
