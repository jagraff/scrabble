"""Rack and bag feasibility for the constructed 25-move sequence.

`reachability.py` shows the record's pre-move position can be built by a
sequence of legal *board* moves, but it models no bag, no per-player
racks and no alternation -- it treats draws as unconstrained.  That makes
its result constructibility, not reachability in a real game.

This module closes that gap.  Given the move sequence, it asks: can the
moves be dealt to two alternating players, and can the bag be shuffled,
so that every player physically holds the tiles they play, in a rack of
at most 7, at the moment they play them?

The shuffle is ours to choose -- any permutation of the bag is a legal
shuffle -- so this is an existence question, and we answer it
constructively by exhibiting the draws.  The simulation is demand-driven:
whenever a player draws, they take the tiles their *soonest* upcoming
move needs and does not already hold, then arbitrary filler.  If every
move finds its tiles in hand, the schedule is a witness.

What is checked:

  * each move places 1..7 tiles (rack capacity);
  * every tile played comes from the bag and the bag never goes negative,
    so the official 100-tile distribution is respected;
  * a player never holds more than 7 tiles;
  * at each move the mover's rack contains that move's exact tiles,
    blanks included (a blank is its own tile, distinct from the letter it
    represents).

Draw timing follows the rules: seven tiles to start, and after each move
the mover refills to seven while the bag lasts.
"""

from __future__ import annotations

import re
from collections import Counter

from .rules import DISTRIBUTION, N, Tile

RACK = 7
BLANK = '?'


def full_bag() -> Counter:
    bag = Counter(DISTRIBUTION)
    bag[BLANK] = 2
    return bag


def parse_coord(name):
    """`I3` -> (row 2, column 8). The inverse of `rules.coord_name`."""
    m = re.fullmatch(r'([A-O])(\d{1,2})', name.strip())
    if not m:
        raise ValueError(f'not a board coordinate: {name!r}')
    r = int(m.group(2)) - 1
    c = ord(m.group(1)) - ord('A')
    if not (0 <= r < N and 0 <= c < N):
        raise ValueError(f'coordinate off the board: {name!r}')
    return r, c


def parse_reachability_placements(path='results/reachability.log'):
    """The move sequence, as a list of {cell: Tile}.

    Keeping the cells -- rather than only the tile counts -- is what lets
    the same parsed sequence be checked against the board it claims to
    build. A rack schedule that balances the bag but describes a different
    set of moves is not a certificate for this position."""
    moves = []
    for line in open(path):
        m = re.match(r'\s*\d+\.\s+(.+?)\s+->', line)
        if not m:
            continue
        placements = {}
        for cell in m.group(1).split(','):
            where, face = cell.split('=')
            face = face.strip()
            blank = face.endswith('?')
            placements[parse_coord(where)] = Tile(face[0], is_blank=blank)
        moves.append(placements)
    return moves


def parse_reachability_log(path='results/reachability.log'):
    """The move sequence, as a list of tile multisets.

    A cell written `I3=S?` is a blank played as S, so the tile consumed is
    a blank, not an S."""
    return [tiles_of(p) for p in parse_reachability_placements(path)]


def tiles_of(placements):
    """The multiset of physical tiles a placement consumes."""
    tiles = Counter()
    for t in placements.values():
        tiles[BLANK if t.is_blank else t.letter] += 1
    return tiles


def final_move_tiles():
    """The record play itself, from the transcribed move."""
    from . import known
    tiles = Counter()
    for _, t in known.MOVE.placements.items():
        tiles[BLANK if t.is_blank else t.letter] += 1
    return tiles


def schedule(moves, n_players=2, log=print, owner=None):
    """Deal `moves` to `n_players` in turn and try to supply every rack.

    Returns (ok, witness) where witness lists, per move, the tiles drawn
    beforehand and the rack held.

    `owner` overrides who takes each move. It exists so that a
    *non*-alternating schedule can be constructed on purpose and fed to
    `verify_witness`, which is the only way to show that the verifier
    enforces alternation rather than merely recording it. Production
    callers leave it alone and get strict alternation."""
    if owner is None:
        owner = [i % n_players for i in range(len(moves))]
    elif len(owner) != len(moves):
        raise ValueError('owner must name a player for every move')
    bag = full_bag()
    racks = [Counter() for _ in range(n_players)]
    upcoming =[[moves[i] for i in range(len(moves)) if owner[i] == p]
                for p in range(n_players)]
    nxt = [0] * n_players
    witness = []

    def draw(p, k):
        """Draw up to k tiles for player p, nearest demand first."""
        got = Counter()
        for demand in upcoming[p][nxt[p]:]:
            if sum(got.values()) >= k:
                break
            missing = demand - racks[p] - got
            for ch in sorted(missing.elements()):
                if sum(got.values()) >= k or sum(racks[p].values()) + \
                        sum(got.values()) >= RACK:
                    break
                if bag[ch] > 0:
                    bag[ch] -= 1
                    got[ch] += 1
        # filler: any remaining tile, most plentiful first
        while (sum(got.values()) < k
               and sum(racks[p].values()) + sum(got.values()) < RACK
               and sum(bag.values()) > 0):
            ch = max((c for c in bag if bag[c] > 0), key=lambda c: bag[c])
            bag[ch] -= 1
            got[ch] += 1
        racks[p] += got
        return got

    opening = []
    for p in range(n_players):
        opening.append(dict(draw(p, RACK)))

    for i, tiles in enumerate(moves):
        p = owner[i]
        if sum(tiles.values()) > RACK:
            log(f'move {i + 1}: places {sum(tiles.values())} tiles > rack')
            return False, witness
        short = tiles - racks[p]
        if short:
            log(f'move {i + 1} (player {p}): rack lacks {dict(short)}; '
                f'holds {dict(racks[p])}')
            return False, witness
        if sum(racks[p].values()) > RACK:
            log(f'move {i + 1}: rack over capacity')
            return False, witness
        racks[p] -= tiles
        nxt[p] += 1          # this demand is satisfied; aim at the next one
        got = draw(p, sum(tiles.values()))
        witness.append({'move': i + 1, 'player': p,
                        'plays': dict(tiles), 'drew_after': dict(got),
                        'rack_after': dict(racks[p]),
                        'bag_left': sum(bag.values())})
    return True, {'opening': opening, 'moves': witness}


def verify_witness(moves, wit, n_players=2):
    """Independently re-check a schedule produced by `schedule`.

    Deliberately does not reuse the generator's logic: it replays the
    recorded draws against a fresh bag and derives every quantity it
    checks.  Nothing the witness records about its own state is taken as
    authoritative -- `rack_after` and `bag_left` are recomputed and
    compared, and the mover is derived from the move index rather than
    read out of the record.

    That last one is the rule the file exists to establish. Reading
    `rec['player']` accepted a witness that dealt every move to a single
    player, which is precisely the "two alternating players" claim the
    schedule is supposed to certify.
    """
    bag = full_bag()
    racks = [Counter() for _ in range(n_players)]

    def take(p, drawn):
        for ch, n in drawn.items():
            if n < 0:
                return f'negative draw {n}x{ch}'
            if bag[ch] < n:
                return f'drew {n}x{ch} but bag holds {bag[ch]}'
            bag[ch] -= n
            racks[p][ch] += n
        if sum(racks[p].values()) > RACK:
            return f'player {p} holds {sum(racks[p].values())} > {RACK}'
        return None

    if len(wit['opening']) != n_players:
        return False, (f"{len(wit['opening'])} opening draws for "
                       f'{n_players} players')
    for p, drawn in enumerate(wit['opening']):
        want = min(RACK, sum(bag.values()))
        if sum(drawn.values()) != want:
            return False, (f'opening draw for player {p}: '
                           f'{sum(drawn.values())} tiles, must be {want}')
        err = take(p, drawn)
        if err:
            return False, f'opening draw: {err}'

    # A truncated witness is caught by the tile accounting below, but only
    # because every move places at least one tile; an explicit length check
    # does not depend on that coincidence, and a witness longer than the
    # move list would otherwise be silently ignored by the zip.
    if len(wit['moves']) != len(moves):
        return False, (f"witness has {len(wit['moves'])} moves, the sequence "
                       f'has {len(moves)}')

    for i, (rec, tiles) in enumerate(zip(wit['moves'], moves)):
        # Derived, not read. See the docstring.
        p = i % n_players
        if rec.get('player') != p:
            return False, (f"move {i + 1}: witness assigns player "
                           f"{rec.get('player')}, alternation requires {p}")
        if rec.get('move') != i + 1:
            return False, (f"move {i + 1}: witness numbers it "
                           f"{rec.get('move')}")
        if Counter(rec['plays']) != tiles:
            return False, f'move {i + 1}: witness plays != actual move'
        if not 1 <= sum(tiles.values()) <= RACK:
            return False, (f'move {i + 1}: places {sum(tiles.values())} '
                           f'tiles')
        if tiles - racks[p]:
            return False, (f'move {i + 1}: rack lacks '
                           f'{dict(tiles - racks[p])}')
        racks[p] -= tiles
        # Refill to seven while the bag lasts -- the rule, not a choice.
        # Under-drawing would not help a constructed game (the shuffle is
        # ours, so a chosen refill is at least as good as none), but a
        # certificate that skips a rule does not certify that rule.
        want = min(RACK - sum(racks[p].values()), sum(bag.values()))
        if sum(rec['drew_after'].values()) != want:
            return False, (f"move {i + 1}: drew "
                           f"{sum(rec['drew_after'].values())}, must refill "
                           f'to {RACK} while the bag lasts ({want})')
        err = take(p, rec['drew_after'])
        if err:
            return False, f'move {i + 1}: {err}'
        # Recorded state is checked against derived state, never trusted.
        if Counter(rec.get('rack_after', {})) != racks[p]:
            return False, (f'move {i + 1}: rack_after says '
                           f"{dict(rec.get('rack_after', {}))}, derived "
                           f'{dict(racks[p])}')
        if rec.get('bag_left') != sum(bag.values()):
            return False, (f"move {i + 1}: bag_left says "
                           f"{rec.get('bag_left')}, derived "
                           f'{sum(bag.values())}')

    drawn_total = sum(sum(racks[p].values()) for p in range(n_players)) \
        + sum(sum(t.values()) for t in moves)
    if drawn_total + sum(bag.values()) != 100:
        return False, (f'tile accounting: {drawn_total} accounted + '
                       f'{sum(bag.values())} in bag != 100')
    return True, (f'{sum(sum(t.values()) for t in moves)} played, '
                  f'{sum(sum(racks[p].values()) for p in range(n_players))} '
                  f'on racks, {sum(bag.values())} in bag')


def verify_board_sequence(placements, lexicon, target=None):
    """Replay the move sequence on a real board and check where it lands.

    `verify_witness` proves the tiles could have been held. It says nothing
    about where they went: it consumes tile *counts*, so a schedule for a
    different set of moves entirely would satisfy it. This closes that gap
    by replaying the same parsed sequence through the rules engine, which
    re-derives legality, word validity and score at every step, and
    confirms the result is the position actually claimed.

    Returns (ok, detail, scores)."""
    from .board import IllegalMove, IllegalPosition, Move, apply_move
    from .board import check_static_position

    grid, scores = {}, []
    for i, placed in enumerate(placements, 1):
        try:
            res = apply_move(grid, Move(dict(placed)), lexicon)
        except (IllegalMove, IllegalPosition) as e:
            return False, f'move {i} is illegal: {e}', scores
        grid = res.new_grid
        scores.append(res.total)
    try:
        check_static_position(grid, lexicon)
    except IllegalPosition as e:
        return False, f'final position is illegal: {e}', scores
    if target is not None:
        got = {c: (t.letter, t.is_blank) for c, t in grid.items()}
        want = {c: (t.letter, t.is_blank) for c, t in target.items()}
        if got != want:
            missing = {c: want[c] for c in set(want) - set(got)}
            extra = {c: got[c] for c in set(got) - set(want)}
            wrong = {c: (got[c], want[c]) for c in set(got) & set(want)
                     if got[c] != want[c]}
            return False, (f'final board differs from the target: '
                           f'{len(missing)} missing, {len(extra)} extra, '
                           f'{len(wrong)} wrong'), scores
    return True, f'{len(placements)} moves replayed, final move scored ' \
                 f'{scores[-1]}', scores


def full_sequence(path='results/reachability.log'):
    """The 25-move build-up plus the record play, cells and all."""
    from . import known
    return parse_reachability_placements(path) + [dict(known.MOVE.placements)]


def main():
    import json

    from . import known
    from .lexicon import load

    placements = full_sequence()
    moves = [tiles_of(p) for p in placements]
    total = sum(sum(t.values()) for t in moves)
    print(f'{len(moves)} moves (25 build-up + the record play), '
          f'{total} tiles played')

    # The board first: a rack schedule certifies that the tiles could be
    # held, not that they were played where the position says. Both halves
    # are needed, and they must be checked against the *same* parsed
    # sequence or neither constrains the other.
    grid = known.pre_board()
    target = dict(grid)
    for c, t in known.MOVE.placements.items():
        target[c] = t
    board_ok, board_detail, scores = verify_board_sequence(
        placements, load(), target=target)
    print(f'board replay: {board_ok}  ({board_detail})')
    if board_ok and scores[-1] != known.EXPECTED_SCORE:
        board_ok = False
        board_detail = (f'final move scored {scores[-1]}, expected '
                        f'{known.EXPECTED_SCORE}')
        print(f'  MISMATCH: {board_detail}')

    ok, witness = schedule(moves)
    print(f'rack/bag feasible with 2 alternating players: {ok}')
    verified, detail = (False, 'no schedule')
    if ok:
        verified, detail = verify_witness(moves, witness)
        print(f'witness independently re-verified: {verified}  ({detail})')
    json.dump({'feasible': ok, 'verified': verified, 'detail': detail,
               'board_replay_ok': board_ok, 'board_replay': board_detail,
               'final_move_score': scores[-1] if scores else None,
               'n_moves': len(moves), 'tiles_played': total,
               'witness': witness},
              open('results/rack_schedule.json', 'w'), indent=1)
    print('  witness -> results/rack_schedule.json')
    return 0 if (ok and verified and board_ok) else 1


if __name__ == '__main__':
    raise SystemExit(main())
