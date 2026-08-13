"""Pattern-level completeness proof for the final geometry.

Stage A and stage B leave exactly one open case: OXYPHENBUTAZONE played
across row 0.  Within that case a play is determined by

  * which cells carry newly placed tiles (the "placed pattern" S), and
  * what the resulting cross words are.

`finalize.py` enumerated (S, cross-word assignment) pairs and refuted them
one at a time.  That axis is hopeless: cross words are freely
substitutable (ZOOGAMETE / ZOOGAMETES, XYLEM / XYLEMS, ...), so a single
pattern spawns hundreds of configurations that all fail for the same
structural reason.

Here we quantify over S only.  Two facts make the set of S tiny:

  * a rack holds 7 tiles and stage B caps |S| <= 6 at 1730, so |S| = 7;
  * stage B caps every non-full TW mask at 784, so {0, 7, 14} subset S.

That leaves C(12, 4) = 495 patterns.  `qualifying_patterns` scores each
one with the *same* one-directional relaxation stage A uses, discarding
those that cannot reach the threshold even optimistically; only 165
survive.  `prove_patterns` then hands each survivor to the full 15x15
tableau model with the placed set pinned and the cross words left free,
asking for any legal board scoring >= threshold + 1.

If every survivor comes back INFEASIBLE, no legal play in this geometry
beats the threshold, and -- since every other geometry died in stage A/B
-- the threshold is the global maximum.

Soundness notes:

  * the pattern filter only ever *enlarges* the feasible set (it is the
    stage-A relaxation, which ignores supports, glue and the tile bag),
    so discarding a pattern below the threshold is safe;
  * we deliberately do not pass `known_upper`.  That would add a hard
    `total <= bound` constraint, making this proof depend on the
    row-1-exact machinery; leaving it off keeps the chain short at the
    cost of a slower search;
  * `fixed_blank_loss` does not apply here (it needs pinned cross words),
    so the model falls back to its own blank penalty, which
    under-estimates the loss and is therefore safe for refutation.
"""

from __future__ import annotations

import json
import time
from itertools import combinations

from .bounds import adjusted_sum, best_rest_table, cross_bound_table
from .rules import N, VALUES, letter_multiplier, word_multiplier

WORD = 'OXYPHENBUTAZONE'
ROW = 0
RACK = 7


def pattern_bound(S, word=WORD, row=ROW, cb=None) -> int:
    """Stage-A relaxed upper bound on the score of playing `word` with
    exactly the cells in S newly placed."""
    wm = 1
    for c in S:
        wm *= word_multiplier((row, c))
    total = wm * adjusted_sum(word)
    for c in S:
        lm = letter_multiplier((row, c))
        total += wm * VALUES[word[c]] * (lm - 1) + cb[word[c]][row][c]
    if len(S) == RACK:
        total += 50
    return total


def qualifying_patterns(lexicon, word=WORD, row=ROW, threshold=1786):
    """Every placed pattern that could still beat `threshold`.

    Returns (survivors, n_total) where survivors is a list of
    (bound, S) sorted by descending bound."""
    cb = cross_bound_table(best_rest_table(lexicon))
    wm_cols = [c for c in range(N) if word_multiplier((row, c)) > 1]
    assert len(wm_cols) == 3, wm_cols
    rest = [c for c in range(N) if c not in wm_cols]
    out = []
    n_total = 0
    for extra in combinations(rest, RACK - len(wm_cols)):
        S = tuple(sorted(wm_cols + list(extra)))
        n_total += 1
        b = pattern_bound(S, word, row, cb)
        if b > threshold:
            out.append((b, S))
    out.sort(reverse=True)
    return out, n_total


def prove_patterns(lexicon, patterns, threshold=1786, time_limit=300.0,
                   out_path='results/pattern_proof.json', log=print):
    """Decide each pattern exactly with the pinned-placed-set tableau."""
    from .cstage import solve_tableau
    results = []
    for i, (bound, S) in enumerate(patterns):
        t0 = time.time()
        name, val, ub, sol = solve_tableau(
            lexicon, WORD, ROW, time_limit=time_limit,
            fix_placed_exact=set(S), min_score=threshold + 1,
            verbose=False, log=lambda s: None)
        dt = time.time() - t0
        log(f'[{i + 1}/{len(patterns)}] {S} relaxed={bound} -> {name} '
            f'val={val} ({dt:.0f}s)', flush=True)
        results.append({'placed': list(S), 'relaxed_bound': bound,
                        'status': name, 'value': val, 'seconds': round(dt, 1),
                        'solution': sol})
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    return results


def main():
    import argparse
    import os
    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--time-limit', type=float, default=300.0)
    ap.add_argument('--out', default='results/pattern_proof.json')
    ap.add_argument('--only-unknown-from', default=None,
                    help='re-run just the unresolved patterns of a prior run')
    args = ap.parse_args()
    lex = load()
    pats, n_total = qualifying_patterns(lex, threshold=args.threshold)
    print(f'{n_total} placed patterns with |S|=7 covering all three TWs; '
          f'{len(pats)} can reach {args.threshold + 1} under the stage-A '
          f'relaxation')
    if args.only_unknown_from:
        prior = json.load(open(args.only_unknown_from))
        todo = {tuple(r['placed']) for r in prior
                if r['status'] != 'INFEASIBLE'}
        pats = [(b, S) for b, S in pats if S in todo]
        print(f'  restricted to {len(pats)} unresolved patterns')
    os.makedirs('results', exist_ok=True)
    res = prove_patterns(lex, pats, threshold=args.threshold,
                         time_limit=args.time_limit, out_path=args.out)
    bad = [r for r in res if r['status'] != 'INFEASIBLE']
    print(f'\n{len(res)} patterns decided; {len(bad)} not refuted')
    for r in bad:
        print('  ', r['status'], r['value'], tuple(r['placed']))
    if not bad:
        print(f'\nCOMPLETE: no legal play in this geometry beats '
              f'{args.threshold}.')


if __name__ == '__main__':
    main()
