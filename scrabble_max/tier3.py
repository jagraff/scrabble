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
from .partition import DEFAULT_BLOCKS, enumerate_many

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
    ap.add_argument('--blocks', type=int, default=DEFAULT_BLOCKS,
                    help=f'partition cells per pattern '
                         f'(default {DEFAULT_BLOCKS} + 1)')
    ap.add_argument('--workers', type=int, default=4,
                    help='concurrent cells; this machine has 4 performance '
                         'cores, so 4 by default')
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--ckpt-dir', default='results/enum_cells')
    ap.add_argument('--out', default='results/tier3_configs.json')
    ap.add_argument('--enumerate-only', action='store_true')
    ap.add_argument('--allow-unstamped', action='store_true',
                    help='accept checkpoints with no identity header. Only '
                         'for reading archived pre-hardening runs; a '
                         'certified run must not use it')
    ap.add_argument('--check-time-limit', type=float, default=600.0)
    ap.add_argument('--decompose-time-limit', type=float, default=60.0,
                    help='per-branch limit for the decomposition that '
                         'closes configurations CP-SAT leaves undecided')
    ap.add_argument('--no-decompose', action='store_true',
                    help='report undecided configurations instead of '
                         'decomposing them; the run then fails, because an '
                         'undecided configuration leaves the proof open')
    a = ap.parse_args()

    pats = survivors()
    print(f'{len(pats)} surviving patterns:')
    for S in pats:
        print('   ', S)
    print()

    t0 = time.time()
    res = enumerate_many(pats, n_blocks=a.blocks, threshold=a.threshold,
                         max_workers=a.workers, ckpt_dir=a.ckpt_dir,
                         allow_unstamped=a.allow_unstamped)
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
        return 0 if allc else 1

    from .finalize import check_configs
    lex = load()
    print()
    print('refuting...')
    t1 = time.time()
    beat = []
    unresolved = []
    check_dir = os.path.join(os.path.dirname(a.out) or '.', 'tier3_checks')
    os.makedirs(check_dir, exist_ok=True)
    for S, (cfgs, complete) in sorted(res.items()):
        if not cfgs:
            print(f'  {S}: nothing to refute (0 configurations)')
            continue
        # A distinct out_path per pattern. check_configs rewrites its whole
        # output file after every configuration, so a shared path would
        # leave only the last pattern's results on disk.
        tag = ''.join(f'{c:02d}' for c in S)
        seen = [0]

        def tick(msg='', **kw):
            seen[0] += 1
            if seen[0] % 50 == 0:
                print(f'    {tag}: {seen[0]}/{len(cfgs)} checked '
                      f'({(time.time() - t1) / 60:.0f}m)', flush=True)

        rows = check_configs(lex, cfgs, threshold=a.threshold,
                             time_limit=a.check_time_limit,
                             out_path=os.path.join(check_dir, f'{tag}.json'),
                             log=tick)
        over = [r for r in rows if (r.get('value') or 0) > a.threshold]
        beat += over
        by_ceiling = sum(1 for r in rows
                         if r.get('status') == 'INFEASIBLE' and r.get('reason'))
        undecided = [r for r in rows if r.get('status') != 'INFEASIBLE']
        print(f'  {S}: {len(rows)} checked, {by_ceiling} by exact ceiling, '
              f'{len(rows) - by_ceiling - len(undecided)} by CP-SAT proof, '
              f'{len(undecided)} UNDECIDED, {len(over)} above threshold',
              flush=True)
        unresolved.extend((S, r) for r in undecided)
    print()
    print(f'refutation in {(time.time() - t1) / 60:.1f} min')

    # An UNDECIDED configuration is not a refuted one. CP-SAT leaves a
    # handful undecided at any finite time limit -- one, on the recorded
    # run -- and those were closed by decomposition: pin one board cell,
    # recurse on whatever survives, and refute every branch. That step was
    # run by hand and committed as prose, so the pipeline could finish
    # "successfully" with the last case still open. It runs here instead.
    decomposed = []
    if unresolved and not a.no_decompose:
        print()
        print(f'decomposing {len(unresolved)} undecided configuration(s)')
        from .decompose import refute_parallel
        still_open = []
        for S, r in unresolved:
            crosses = {int(k): v for k, v in r['config']['crosses'].items()}
            t2 = time.time()
            refuted, branches = refute_parallel(
                lex, tuple(r['config']['placed']), crosses,
                threshold=a.threshold, workers=a.workers,
                time_limit=a.decompose_time_limit, log=lambda *x: None)
            print(f'    {S}: refuted={refuted} '
                  f'({len(branches)} open, {time.time() - t2:.0f}s)',
                  flush=True)
            decomposed.append({'placed': list(S), 'crosses': r['config'][
                'crosses'], 'refuted': bool(refuted),
                'open_branches': len(branches)})
            if not refuted:
                still_open.append((S, r))
        unresolved = still_open
        with open(os.path.join(check_dir, 'decomposed.json'), 'w') as f:
            json.dump(decomposed, f, indent=1)

    if beat:
        print(f'*** {len(beat)} configurations exceed {a.threshold} ***')
        for r in beat[:10]:
            print('   ', r)
        return 1
    if unresolved:
        # Not the same sentence as "nothing exceeds the threshold". An
        # undecided configuration is not a refuted one, and the proof is
        # open until it is settled.
        print(f'no configuration was SHOWN to exceed {a.threshold}, but '
              f'{len(unresolved)} is/are UNDECIDED -- the proof is not '
              f'closed for these:')
        for S, r in unresolved:
            print(f'    {S} {json.dumps(r["config"]["crosses"])}')
        return 1
    if not allc:
        # Reachable only if every configuration found so far was refuted
        # while some cell never finished: nothing was shown to exceed the
        # threshold, but the list it was shown over is not exhaustive.
        print('every configuration found was refuted, but the enumeration '
              'is NOT exhaustive -- no completeness claim may be made')
        return 1
    print(f'every configuration refuted: no legal play exceeds '
          f'{a.threshold}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
