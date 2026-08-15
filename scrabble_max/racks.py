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

from .rules import DISTRIBUTION

RACK = 7
BLANK = '?'


def full_bag() -> Counter:
    bag = Counter(DISTRIBUTION)
    bag[BLANK] = 2
    return bag


def parse_reachability_log(path='results/reachability.log'):
    """The move sequence, as a list of tile multisets.

    A cell written `I3=S?` is a blank played as S, so the tile consumed is
    a blank, not an S."""
    moves = []
    for line in open(path):
        m = re.match(r'\s*\d+\.\s+(.+?)\s+->', line)
        if not m:
            continue
        tiles = Counter()
        for cell in m.group(1).split(','):
            face = cell.split('=')[1].strip()
            tiles[BLANK if face.endswith('?') else face] += 1
        moves.append(tiles)
    return moves


def final_move_tiles():
    """The record play itself, from the transcribed move."""
    from . import known
    tiles = Counter()
    for _, t in known.MOVE.placements.items():
        tiles[BLANK if t.is_blank else t.letter] += 1
    return tiles


def schedule(moves, n_players=2, log=print):
    """Deal `moves` to `n_players` in turn and try to supply every rack.

    Returns (ok, witness) where witness lists, per move, the tiles drawn
    beforehand and the rack held."""
    bag = full_bag()
    racks = [Counter() for _ in range(n_players)]
    owner = [i % n_players for i in range(len(moves))]
    upcoming = [[moves[i] for i in range(len(moves)) if owner[i] == p]
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
    recorded draws against a fresh bag and asserts every rule at each
    step.  A witness that passes this is a self-contained certificate."""
    bag = full_bag()
    racks = [Counter() for _ in range(n_players)]

    def take(p, drawn):
        for ch, n in drawn.items():
            if bag[ch] < n:
                return f'drew {n}x{ch} but bag holds {bag[ch]}'
            bag[ch] -= n
            racks[p][ch] += n
        if sum(racks[p].values()) > RACK:
            return f'player {p} holds {sum(racks[p].values())} > {RACK}'
        return None

    for p, drawn in enumerate(wit['opening']):
        err = take(p, drawn)
        if err:
            return False, f'opening draw: {err}'

    for rec, tiles in zip(wit['moves'], moves):
        p = rec['player']
        if Counter(rec['plays']) != tiles:
            return False, f"move {rec['move']}: witness plays != actual move"
        if tiles - racks[p]:
            return False, (f"move {rec['move']}: rack lacks "
                           f"{dict(tiles - racks[p])}")
        racks[p] -= tiles
        err = take(p, rec['drew_after'])
        if err:
            return False, f"move {rec['move']}: {err}"

    drawn_total = sum(sum(racks[p].values()) for p in range(n_players)) \
        + sum(sum(t.values()) for t in moves)
    if drawn_total + sum(bag.values()) != 100:
        return False, (f'tile accounting: {drawn_total} accounted + '
                       f'{sum(bag.values())} in bag != 100')
    return True, (f'{sum(sum(t.values()) for t in moves)} played, '
                  f'{sum(sum(racks[p].values()) for p in range(n_players))} '
                  f'on racks, {sum(bag.values())} in bag')


def main():
    import json
    moves = parse_reachability_log()
    moves.append(final_move_tiles())
    total = sum(sum(t.values()) for t in moves)
    print(f'{len(moves)} moves (25 build-up + the record play), '
          f'{total} tiles played')
    ok, witness = schedule(moves)
    print(f'\nrack/bag feasible with 2 alternating players: {ok}')
    verified, detail = (False, 'no schedule')
    if ok:
        verified, detail = verify_witness(moves, witness)
        print(f'witness independently re-verified: {verified}  ({detail})')
    json.dump({'feasible': ok, 'verified': verified, 'detail': detail,
               'n_moves': len(moves), 'tiles_played': total,
               'witness': witness},
              open('results/rack_schedule.json', 'w'), indent=1)
    print('  witness -> results/rack_schedule.json')


if __name__ == '__main__':
    main()
