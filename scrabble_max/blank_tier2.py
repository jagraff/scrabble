"""The blank-penalty sweep over the tier-2 survivors.

`results/blank_penalty_tier2.json` is the input to tier 3 -- `tier3.py`
reads it to decide which patterns still need enumerating -- and it had no
entry point. It was produced once by an ad-hoc script and committed, so the
last stage of the proof rested on a file that no documented command could
regenerate. Everything downstream of it was reproducible; the thing that
selected the work was not.

What it computes, per surviving pattern: the row-1-exact bound with the
blank penalty off (`old`) and on (`new`), and whether the pattern dies at
the threshold under the penalty. The penalty adds a *lower* bound on what a
blank forfeits, so the objective stays an upper bound on the true score and
Lemma 1 still applies; a pattern whose penalised bound falls to the
threshold or below cannot beat it and needs no enumeration.

Two directional facts hold by construction, and both are asserted here
rather than assumed, because a tightening that moved the wrong way would be
unsound rather than merely wrong:

  * no bound may rise -- `new <= old` for every pattern;
  * the record play's own placed set must stay at or above 1,786, or the
    model is refuting a play that demonstrably exists.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from . import known
from . import tighten as T
from .lexicon import load
from .provenance import stamp

WORD = 'OXYPHENBUTAZONE'
ROW = 0
KNOWN_PLACED = tuple(sorted(c for (_, c) in known.MOVE.placements))
OUT = 'results/blank_penalty_tier2.json'
SURVIVORS = 'results/pattern_row1.json'


def survivors(path=SURVIVORS):
    """The patterns tier 2 kept, in the order it recorded them."""
    with open(path) as f:
        rows = json.load(f)
    return [tuple(r['placed']) for r in rows if r.get('kept')]


def bound(ctx, S, penalty, time_limit=600.0):
    lex, opts, adj, dawg = ctx
    (b, _), _ = T.tighten_candidate(
        lex, WORD, ROW, opts_cache=opts, adj_pairs=adj, row1_exact=True,
        dawg=dawg, mask_filter=[7], pairwise_all_rows=True,
        fix_placed=set(S), time_limit=time_limit, blank_penalty=penalty,
        log=lambda s: None)
    return b


def sweep(patterns, threshold=1786, time_limit=600.0, log=print):
    lex = load()
    ctx = (lex,
           {(c, ROW): T.cross_options(lex, c, ROW) for c in set(WORD)},
           T.adjacent_pairs(lex),
           T.build_line_dawg(lex))
    rows = []
    for i, S in enumerate(patterns, 1):
        t0 = time.time()
        old = bound(ctx, S, penalty=False, time_limit=time_limit)
        new = bound(ctx, S, penalty=True, time_limit=time_limit)
        dies = new <= threshold
        rows.append({'placed': list(S), 'old': old, 'new': new,
                     'dies': bool(dies)})
        log(f'[{i}/{len(patterns)}] {S}: {old:.0f} -> {new:.0f}'
            f'{"  DIES" if dies else ""}  ({time.time() - t0:.0f}s)')
    return rows


def check(rows, threshold=1786):
    """The two directional facts. Returned rather than asserted so the
    caller can print all of them instead of stopping at the first."""
    problems = []
    for r in rows:
        if r['new'] > r['old']:
            problems.append(
                f"{tuple(r['placed'])}: penalised bound ROSE "
                f"{r['old']:.0f} -> {r['new']:.0f}; a tightening may lower a "
                f"bound, never raise it")
    rec = [r for r in rows if tuple(r['placed']) == KNOWN_PLACED]
    if not rec:
        problems.append(f'the record pattern {KNOWN_PLACED} is not in the '
                        f'sweep; it must be, as the soundness check')
    elif rec[0]['new'] < known.EXPECTED_SCORE:
        problems.append(
            f"{KNOWN_PLACED}: penalised bound {rec[0]['new']:.0f} < "
            f'{known.EXPECTED_SCORE}, which refutes a play that exists')
    elif rec[0]['dies']:
        problems.append(f'{KNOWN_PLACED} is marked dead, but it is the '
                        f'record play')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--survivors', default=SURVIVORS)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--time-limit', type=float, default=600.0)
    a = ap.parse_args()

    prov = stamp()
    print(f"provenance: commit {prov['git_commit']} "
          f"ortools {prov['ortools']} seed {prov['pythonhashseed']} "
          f"lexicon {prov['lexicon']['sha256'][:12]}", flush=True)

    pats = survivors(a.survivors)
    print(f'{len(pats)} tier-2 survivors to sweep\n')
    t0 = time.time()
    rows = sweep(pats, threshold=a.threshold, time_limit=a.time_limit)

    problems = check(rows, a.threshold)
    dead = sum(1 for r in rows if r['dies'])
    print(f'\n{dead} of {len(rows)} die under the penalty; '
          f'{len(rows) - dead} go to tier 3  ({(time.time() - t0) / 60:.1f} '
          f'min)')
    if problems:
        print(f'\n{len(problems)} DIRECTIONAL VIOLATION(S) -- not written:')
        for p in problems:
            print('   ', p)
        return 1

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(rows, f, indent=1)
    print(f'-> {a.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
