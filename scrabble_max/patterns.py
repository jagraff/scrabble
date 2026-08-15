"""Pattern-level completeness proof for the final geometry.

Stage A and stage B leave exactly one open case: OXYPHENBUTAZONE played
across row 0.  Within that case a play is determined by

  * which cells carry newly placed tiles (the "placed pattern" S), and
  * what the resulting cross words are.

`finalize.py` enumerated (S, cross-word assignment) pairs and refuted them
one at a time.  That axis is hopeless: cross words are freely
substitutable (ZOOGAMETE / ZOOGAMETES, XYLEM / XYLEMS, ...), so a single
pattern spawns hundreds of configurations that all fail for the same
structural reason -- 1300 configurations turned out to span just 14
patterns.

Here we quantify over S only, in three tiers of increasing cost:

  tier 1  `qualifying_patterns` -- pure arithmetic.  A rack holds 7 tiles
          and stage B caps |S| <= 6 at 1730, so |S| = 7; stage B caps
          every non-full TW mask at 784, so {0, 7, 14} is a subset of S.
          That leaves C(12, 4) = 495 patterns, scored with the stage-A
          relaxation; 165 survive.

  tier 2  `row1_filter` -- the stage-B row-1-exact model with the placed
          set pinned (ceiling 1794 rather than stage A's 2000).  Tens of
          seconds per pattern, and it disposes of most of the 165.

  tier 3  `prove_patterns` -- the full 15x15 tableau with the placed set
          pinned and cross words free, asking for any legal board scoring
          >= threshold + 1.

If every survivor of tier 3 is INFEASIBLE then no legal play in this
geometry beats the threshold, and -- every other geometry having died in
stage A/B -- the threshold is the global maximum.

Soundness notes:

  * tiers 1 and 2 are one-directional relaxations: they only ever enlarge
    the feasible set, so dropping a pattern whose bound falls at or below
    the threshold is safe;
  * tier 2 eliminates only on a *proven* upper bound.  On a solver
    timeout `tighten_candidate` returns `BestObjectiveBound()`, which is
    still a valid upper bound for a maximisation; if the solver cannot
    even produce that it raises, and we keep the pattern;
  * tier 3 deliberately does not pass `known_upper`.  That would add a
    hard `total <= bound` constraint and make the tableau step depend on
    tier 2; leaving it off keeps the steps independent, and a probe
    showed it does not speed the search up anyway;
  * `fixed_blank_loss` does not apply at tier 3 (it needs pinned cross
    words), so the model falls back to its own blank penalty, which
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
    """Tier 1.  Every placed pattern that could still beat `threshold`.

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


def row1_filter(lexicon, patterns, threshold=1786, time_limit=300.0,
                out_path='results/pattern_row1.json', log=print):
    """Tier 2.  Per-pattern row-1-exact bound; returns the survivors."""
    from . import tighten as T
    opts = {(ch, ROW): T.cross_options(lexicon, ch, ROW) for ch in set(WORD)}
    adj = T.adjacent_pairs(lexicon)
    dawg = T.build_line_dawg(lexicon)

    survivors, records = [], []
    for i, (a_bound, S) in enumerate(patterns):
        t0 = time.time()
        try:
            (bound, detail), _ = T.tighten_candidate(
                lexicon, WORD, ROW, opts_cache=opts, adj_pairs=adj,
                row1_exact=True, dawg=dawg, mask_filter=[7],
                pairwise_all_rows=True, fix_placed=set(S),
                time_limit=time_limit, log=lambda s: None)
            proved = bool(detail and detail.get('proved_optimal', False))
        except RuntimeError:
            # solver produced neither a solution nor a bound: keep it
            bound, proved = float('inf'), False
        dt = time.time() - t0
        kept = bound > threshold

        # How the verdict was reached, recorded explicitly.  `proved_optimal`
        # alone is not readable: `detail` is None on INFEASIBLE too, so an
        # infeasibility and a timed-out solve both record False, and a
        # summary that counts them together reports definitive eliminations
        # as if they rested on weak bounds.  The three cases differ in
        # strength -- infeasible and proved_optimum are exact, timeout_bound
        # is only an upper bound -- so name them.
        if bound == float('-inf'):
            verdict = 'infeasible'
        elif proved:
            verdict = 'proved_optimum'
        else:
            verdict = 'timeout_bound'

        records.append({'placed': list(S), 'stage_a_bound': a_bound,
                        'row1_bound': (None if bound in (float('inf'),
                                                         float('-inf'))
                                       else bound),
                        'infeasible': bound == float('-inf'),
                        'proved_optimal': proved,
                        'verdict': verdict,
                        'kept': kept, 'seconds': round(dt, 1)})
        log(f'[{i + 1}/{len(patterns)}] {S} stageA={a_bound} '
            f'row1={bound} -> {"KEEP" if kept else "eliminated"} '
            f'({dt:.0f}s)', flush=True)
        if kept:
            # the tier-2 bound, not the looser stage-A one: this value is
            # reported as the pattern's ceiling and orders tier 3
            # cheapest-first, so using a_bound here mislabelled both
            survivors.append((bound, S))
        with open(out_path, 'w') as f:
            json.dump(records, f, indent=1, default=str)
    return survivors, records


def prove_patterns(lexicon, patterns, threshold=1786, time_limit=300.0,
                   out_path='results/pattern_proof.json', log=print):
    """Tier 3.  Decide each pattern exactly with the pinned tableau."""
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


def prove_pattern_by_score(lexicon, S, upper, threshold=1786,
                           time_limit=1800.0, log=print):
    """Tier 3b.  Refute one pattern by case-splitting on the exact score.

    `upper` must be a *proven* upper bound on the score achievable with
    this placed set -- in practice the tier-2 row-1-exact bound.  Asking
    `total == v` for each v in [threshold + 1, upper] prunes far harder
    than the single `total >= threshold + 1` query, which the solver
    struggles with on the surviving patterns.

    Sound because the cases are exhaustive: any board scoring above the
    threshold has some integer total in that closed range, `upper` being
    an upper bound.  Returns a list of per-score records."""
    from .cstage import solve_tableau
    out = []
    for v in range(threshold + 1, int(upper) + 1):
        t0 = time.time()
        name, val, ub, sol = solve_tableau(
            lexicon, WORD, ROW, time_limit=time_limit,
            fix_placed_exact=set(S), min_score=v, known_upper=v,
            verbose=False, log=lambda s: None)
        dt = time.time() - t0
        log(f'    score={v}: {name} ({dt:.0f}s)', flush=True)
        out.append({'score': v, 'status': name, 'value': val,
                    'seconds': round(dt, 1), 'solution': sol})
        if name != 'INFEASIBLE':
            break
    return out


def prove_patterns_split(lexicon, survivors, uppers, threshold=1786,
                         time_limit=1800.0,
                         out_path='results/pattern_proof_split.json',
                         log=print):
    """Tier 3b driver: score-split refutation for every survivor."""
    results = []
    for i, (_, S) in enumerate(survivors):
        upper = uppers[S]
        log(f'[{i + 1}/{len(survivors)}] {S} upper={upper:.0f}', flush=True)
        cases = prove_pattern_by_score(lexicon, S, upper, threshold=threshold,
                                       time_limit=time_limit, log=log)
        refuted = all(c['status'] == 'INFEASIBLE' for c in cases)
        results.append({'placed': list(S), 'upper': upper,
                        'refuted': refuted, 'cases': cases})
        log(f'    -> {"refuted" if refuted else "NOT REFUTED"}', flush=True)
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    return results


def prove_pattern_by_configs(lexicon, S, threshold=1786,
                             enum_time_limit=1800.0, check_time_limit=600.0,
                             out_dir='results/pattern_configs', log=print):
    """Tier 3c.  Refute one pattern by enumerating *its* configurations.

    The global configuration enumeration in `finalize.py` never terminates
    because it ranges over every placed set at once.  Restricted to a
    single placed set the blocking loop closes: the easiest survivor has
    just 16 configurations and exhausts in 8 minutes.

    Sound and exhaustive: any legal board with this placed set scoring
    above `threshold` realises some configuration, and its row-1-exact
    relaxed score is at least its true score, so it appears in the list.
    `complete=True` means the loop ended in INFEASIBLE, i.e. the list is
    the whole of it; refuting every entry then refutes the pattern.
    """
    import os
    from .finalize import check_configs, enumerate_configs
    os.makedirs(out_dir, exist_ok=True)
    tag = ''.join(f'{c:02d}' for c in S)

    # Stream the running configuration count.  Without it a pattern is a
    # black box until it finishes, so there is no early warning that one is
    # heading for millions rather than hundreds.
    t0 = time.time()
    seen = [0]

    def enum_log(msg='', **kw):
        if 'config #' in str(msg):
            seen[0] += 1
            if seen[0] % 25 == 0 or seen[0] <= 5:
                log(f'      ...{seen[0]} configs so far '
                    f'({(time.time() - t0) / 60:.0f}m)', flush=True)

    cfgs, complete = enumerate_configs(
        lexicon, threshold=threshold, time_limit=enum_time_limit,
        fix_placed=set(S), log=enum_log)
    t_enum = time.time() - t0
    log(f'    enumerated {len(cfgs)} configs, complete={complete} '
        f'({t_enum:.0f}s)', flush=True)
    if not complete:
        return {'placed': list(S), 'complete': False,
                'n_configs': len(cfgs), 'refuted': False,
                'enum_seconds': round(t_enum, 1)}

    t1 = time.time()
    res = check_configs(lexicon, cfgs, threshold=threshold,
                        time_limit=check_time_limit,
                        out_path=f'{out_dir}/{tag}.json',
                        log=lambda *a, **k: None)
    t_check = time.time() - t1
    left = [r for r in res if r['status'] != 'INFEASIBLE']
    log(f'    refuted {len(res) - len(left)}/{len(res)} configs '
        f'({t_check:.0f}s)', flush=True)
    return {'placed': list(S), 'complete': True, 'n_configs': len(cfgs),
            'refuted': not left, 'enum_seconds': round(t_enum, 1),
            'check_seconds': round(t_check, 1),
            'survivors': [r['config'] for r in left]}


def prove_patterns_by_configs(lexicon, survivors, threshold=1786,
                              enum_time_limit=1800.0, check_time_limit=600.0,
                              out_path='results/pattern_proof_configs.json',
                              log=print):
    """Tier 3c driver over every surviving pattern.

    Resumes: patterns already recorded as refuted in `out_path` are kept
    and skipped, so a restart does not redo finished enumerations."""
    import os
    results, done = [], {}
    if os.path.exists(out_path):
        for r in json.load(open(out_path)):
            if r.get('refuted'):
                done[tuple(r['placed'])] = r
        if done:
            log(f'resuming: {len(done)} patterns already refuted', flush=True)
    for i, (upper, S) in enumerate(survivors):
        if S in done:
            results.append(done[S])
            log(f'[{i + 1}/{len(survivors)}] {S} already refuted, skipping',
                flush=True)
            continue
        log(f'[{i + 1}/{len(survivors)}] {S} ceiling={upper:.0f}', flush=True)
        rec = prove_pattern_by_configs(
            lexicon, S, threshold=threshold, enum_time_limit=enum_time_limit,
            check_time_limit=check_time_limit, log=log)
        rec['row1_ceiling'] = upper
        results.append(rec)
        log(f'    -> {"REFUTED" if rec["refuted"] else "OPEN"}', flush=True)
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    return results


def load_row1_uppers(path='results/pattern_row1.json'):
    """Proven per-pattern upper bounds produced by tier 2."""
    recs = json.load(open(path))
    return {tuple(r['placed']): r['row1_bound']
            for r in recs if r['kept'] and r['row1_bound'] is not None}


def main():
    import argparse
    import os
    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--row1-time-limit', type=float, default=300.0)
    ap.add_argument('--tableau-time-limit', type=float, default=3600.0)
    ap.add_argument('--stop-after-row1', action='store_true')
    ap.add_argument('--tier3', choices=('configs', 'tableau'),
                    default='configs',
                    help='configs: per-pattern configuration enumeration '
                         '(terminates); tableau: single free-cross-word '
                         'solve per pattern (does not scale)')
    ap.add_argument('--enum-time-limit', type=float, default=1800.0)
    ap.add_argument('--resume-row1', default=None,
                    help='skip tiers 1-2 and take survivors from this JSON')
    ap.add_argument('--out', default='results/pattern_proof.json')
    ap.add_argument('--only', default=None,
                    help='semicolon-separated placed sets to run, e.g. '
                         '"0,1,3,7,10,11,14;0,1,3,7,9,11,14".  Lets disjoint '
                         'subsets run as parallel processes -- give each its '
                         'own --configs-out.')
    ap.add_argument('--configs-out',
                    default='results/pattern_proof_configs.json')
    args = ap.parse_args()
    lex = load()
    os.makedirs('results', exist_ok=True)

    from .provenance import write as write_provenance
    prov = write_provenance()
    print(f"provenance: commit {prov['git_commit']} "
          f"ortools {prov['ortools']} seed {prov['pythonhashseed']} "
          f"lexicon {prov['lexicon']['sha256'][:12]}", flush=True)

    if args.resume_row1:
        uppers = load_row1_uppers(args.resume_row1)
        survivors = [(uppers[S], S) for S in uppers]
        print(f'resumed {len(survivors)} tier-2 survivors from '
              f'{args.resume_row1}', flush=True)
    else:
        pats, n_total = qualifying_patterns(lex, threshold=args.threshold)
        print(f'tier 1: {n_total} placed patterns with |S|=7 covering all '
              f'three TWs; {len(pats)} can reach {args.threshold + 1} under '
              f'the stage-A relaxation', flush=True)
        survivors, _ = row1_filter(lex, pats, threshold=args.threshold,
                                   time_limit=args.row1_time_limit)
        print(f'\ntier 2: {len(survivors)} of {len(pats)} patterns survive '
              f'the row-1-exact bound', flush=True)
        if args.stop_after_row1:
            for b, S in survivors:
                print('   ', S)
            return

    if args.only:
        want = {tuple(int(c) for c in grp.split(','))
                for grp in args.only.split(';') if grp.strip()}
        survivors = [(b, S) for b, S in survivors if S in want]
        missing = want - {S for _, S in survivors}
        assert not missing, f'unknown patterns: {missing}'

    # easiest first: a lower proven ceiling means fewer scores to rule out,
    # so we bank cheap verdicts and isolate the genuinely hard residue.
    survivors.sort(key=lambda bs: (bs[0], bs[1]))
    print('tier 3 order (bound, pattern):', flush=True)
    for b, S in survivors:
        print(f'    {b:.0f}  {S}', flush=True)

    if args.tier3 == 'configs':
        res = prove_patterns_by_configs(
            lex, survivors, threshold=args.threshold,
            enum_time_limit=args.enum_time_limit,
            check_time_limit=args.tableau_time_limit,
            out_path=args.configs_out)
        bad = [r for r in res if not r['refuted']]
        n_cfg = sum(r['n_configs'] for r in res)
        print(f'\ntier 3: {len(res)} patterns, {n_cfg} configurations '
              f'enumerated and refuted; {len(bad)} patterns still open')
        for r in bad:
            print('  open:', tuple(r['placed']),
                  'complete' if r['complete'] else 'ENUMERATION INCOMPLETE')
    else:
        res = prove_patterns(lex, survivors, threshold=args.threshold,
                             time_limit=args.tableau_time_limit,
                             out_path=args.out)
        bad = [r for r in res if r['status'] != 'INFEASIBLE']
        print(f'\ntier 3: {len(res)} patterns decided; {len(bad)} not refuted')
        for r in bad:
            print('  ', r['status'], r['value'], tuple(r['placed']))
    if not bad:
        print(f'\nCOMPLETE: no legal play in this geometry beats '
              f'{args.threshold}.')


if __name__ == '__main__':
    main()
