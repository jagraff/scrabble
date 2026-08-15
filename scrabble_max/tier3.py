"""Tier 3: enumerate and refute every surviving pattern.

The ten patterns that survive tier 2 are the last open case. For each,
enumerate every configuration whose row-1-exact relaxed score could still
beat the threshold, then decide each one exactly with the full tableau.

Enumeration goes through `partition.enumerate_many`, so all patterns'
cells share one queue and the cores stay busy to the last cell rather than
finishing nine patterns and waiting on the tenth.

Killable at any point: every cell checkpoints per solve, and re-running
resumes. Watch it with

    python -m scrabble_max.status --dir results/enum_cells --by-pattern

Completeness is only claimed when every cell of a pattern ended in
INFEASIBLE. A pattern with an unfinished cell is reported as such and
refutes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from .lexicon import load
from .partition import enumerate_many

SURVIVORS_FILE = 'results/blank_penalty_tier2.json'


def survivors(path=SURVIVORS_FILE):
    """The patterns tier 2 could not eliminate."""
    rows = json.load(open(path))
    return [tuple(r['placed']) for r in rows if not r['dies']]


def main():
    ap = argparse.ArgumentParser()
    # Four, not more. Measured on (0,2,3,7,11,13,14): all 14 of its
    # configurations use the same cross word at the pivot column, so they
    # land in one cell however finely the option indices are split. Extra
    # blocks would then buy nothing but an extra closing infeasibility
    # proof each. Cross-pattern parallelism carries the run either way;
    # the cells are insurance against a straggler, not the main mechanism.
    ap.add_argument('--blocks', type=int, default=4,
                    help='partition cells per pattern (default 4 + 1)')
    ap.add_argument('--workers', type=int, default=4,
                    help='concurrent cells; this machine has 4 performance '
                         'cores, so 4 by default')
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--ckpt-dir', default='results/enum_cells')
    ap.add_argument('--out', default='results/tier3_configs.json')
    ap.add_argument('--enumerate-only', action='store_true')
    ap.add_argument('--check-time-limit', type=float, default=600.0)
    a = ap.parse_args()

    pats = survivors()
    print(f'{len(pats)} surviving patterns:')
    for S in pats:
        print('   ', S)
    print()

    t0 = time.time()
    res = enumerate_many(pats, n_blocks=a.blocks, threshold=a.threshold,
                         max_workers=a.workers, ckpt_dir=a.ckpt_dir)
    t_enum = time.time() - t0

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    payload = {'threshold': a.threshold,
               'enumeration_seconds': round(t_enum, 1),
               'patterns': []}
    for S, (cfgs, complete) in sorted(res.items()):
        payload['patterns'].append({
            'placed': list(S), 'complete': complete, 'count': len(cfgs),
            'configs': [{'placed': list(c['placed']),
                         'crosses': {str(k): v
                                     for k, v in c['crosses'].items()},
                         'relaxed_score': c['relaxed_score']}
                        for c in cfgs]})
    with open(a.out, 'w') as f:
        json.dump(payload, f, indent=1)

    total = sum(len(c) for c, _ in res.values())
    allc = all(ok for _, ok in res.values())
    print()
    print(f'enumeration: {total} configurations across {len(pats)} patterns '
          f'in {t_enum / 60:.1f} min, complete={allc} -> {a.out}')
    if not allc:
        print('NOT exhaustive: some cell did not finish; no pattern with an '
              'unfinished cell may be treated as refuted')
    if a.enumerate_only:
        return

    from .finalize import check_configs
    lex = load()
    print()
    print('refuting...')
    t1 = time.time()
    beat = []
    for S, (cfgs, complete) in sorted(res.items()):
        if not cfgs:
            print(f'  {S}: nothing to refute (0 configurations)')
            continue
        rows = check_configs(lex, cfgs, threshold=a.threshold,
                             time_limit=a.check_time_limit, verbose=False)
        over = [r for r in rows if (r.get('value') or 0) > a.threshold]
        beat += over
        print(f'  {S}: {len(rows)} checked, {len(over)} above threshold')
    print()
    print(f'refutation in {(time.time() - t1) / 60:.1f} min')
    if beat:
        print(f'*** {len(beat)} configurations exceed {a.threshold} ***')
        for r in beat[:10]:
            print('   ', r)
    else:
        print(f'no configuration exceeds {a.threshold}')


if __name__ == '__main__':
    main()
