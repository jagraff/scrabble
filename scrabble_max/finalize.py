"""Endgame: enumerate every scoring configuration that could still beat
1786, then decide each one exactly with the full-tableau model.

A "configuration" is (placed set, chosen cross word per placed column).
Under the stage-B row-1-exact relaxation these determine the claimed
score; supports/glue/blanks only make it harder. We:

1. enumerate all configurations with relaxed score >= threshold+1
   (blocking-clause loop over the row-1-exact CP-SAT model);
2. for each, run the full 15x15 tableau model (cstage) with the cross
   columns' contents fixed to the chosen words and everything else free,
   maximizing the true score.

If no configuration reaches threshold+1 in step 2, no legal play beats
the threshold in this geometry — closing the last open case.
"""

from __future__ import annotations

import json
from collections import Counter

from ortools.sat.python import cp_model

from .rules import DISTRIBUTION, N, VALUES
from . import tighten as T

LETTERS = [chr(ord('A') + i) for i in range(26)]


def enumerate_configs(lexicon, word='OXYPHENBUTAZONE', row=0,
                      threshold=1786, time_limit=900.0, max_configs=100000,
                      known_configs=(), log=print, fix_placed=None):
    """All (placed, crosses) configs with row-1-exact relaxed score
    > threshold, for the all-TWs mask."""
    # Build the same model as tighten_candidate(row1_exact=True) for
    # mask 7, but as a feasibility enumeration.  We reuse
    # tighten_candidate by monkey-scoping: simplest is to rebuild here
    # with its helpers.
    opts_cache = {}
    for ch in set(word):
        opts_cache[(ch, row)] = T.cross_options(lexicon, ch, row)
    adj = T.adjacent_pairs(lexicon)
    dawg = T.build_line_dawg(lexicon)

    configs = []

    def block_and_collect(model, handles):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        placed, x, opt_lists, has_cross, total = handles

        def add_block(placed_cols, crosses):
            clause = []
            for c, wrd in crosses.items():
                c = int(c)
                for oi, o in enumerate(opt_lists[c]):
                    if o[3] == wrd:
                        clause.append(x[(c, oi)].Not())
                        break
                else:
                    return  # word not in option list: cannot recur, skip
            for c in range(N):
                if c not in {int(k) for k in crosses}:
                    clause.append(has_cross[c])
                clause.append(placed[c].Not() if c in placed_cols
                              else placed[c])
            model.AddBoolOr(clause)

        for kc in known_configs:
            add_block(set(kc['placed']), kc['crosses'])
        if known_configs:
            log(f'  pre-blocked {len(known_configs)} known configs')

        while len(configs) < max_configs:
            status = solver.Solve(model)
            if status == cp_model.INFEASIBLE:
                return True
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                log(f'  enumeration solver stalled: '
                    f'{solver.StatusName(status)}')
                return False
            chosen = {}
            for (c, oi), v in x.items():
                if solver.Value(v):
                    chosen[c] = opt_lists[c][oi][3]
            placed_cols = tuple(c for c in range(N)
                                if solver.Value(placed[c]))
            val = solver.Value(total)
            configs.append({'placed': placed_cols, 'crosses': chosen,
                            'relaxed_score': val})
            log(f"  config #{len(configs)}: {val} placed={placed_cols} "
                f"{chosen}", flush=True)
            # blocking clause: differ in some chosen x, some cross-less
            # column gaining a cross, or the placed pattern
            clause = []
            for (c, oi), v in x.items():
                if solver.Value(v):
                    clause.append(v.Not())
            for c in range(N):
                if not solver.Value(has_cross[c]):
                    clause.append(has_cross[c])
                clause.append(placed[c].Not() if solver.Value(placed[c])
                              else placed[c])
            model.AddBoolOr(clause)
        return False

    complete = T.tighten_candidate(
        lexicon, word, row, opts_cache=opts_cache, adj_pairs=adj,
        row1_exact=True, dawg=dawg, mask_filter=[7],
        pairwise_all_rows=True, enumerate_above=threshold,
        enumerate_cb=block_and_collect, fix_placed=fix_placed)
    return configs, complete


def exact_fixed_blank_loss(word, placed, crosses):
    """For a pinned configuration, the number of forced blanks among the
    *fixed, scored* tiles is a constant, and so is the minimum score loss:
    every copy of an over-subscribed letter sits in a known word with a
    known multiplier.  Returns (num_forced, min_loss) or None if the
    configuration needs more than 2 blanks and is impossible outright."""
    from .rules import VALUES as V, DISTRIBUTION as D
    copies = Counter(word)
    loss_opts = {ch: [] for ch in copies}
    # main-word copies: value x letter-mult x 27, plus the cross word's
    # share if the cell is a hook with a cross word
    for c, ch in enumerate(word):
        lm = 2 if c in (3, 11) else 1
        wm = 3 if c in (0, 7, 14) else 1
        loss = V[ch] * lm * 27
        if c in crosses:
            loss += wm * V[ch] * lm
        loss_opts.setdefault(ch, []).append(loss)
    for c, w in crosses.items():
        wm = 3 if c in (0, 7, 14) else 1
        for ch in w[1:]:
            copies[ch] += 1
            loss_opts.setdefault(ch, []).append(V[ch] * wm)
    total_forced = 0
    total_loss = 0
    for ch, n in copies.items():
        k = n - D[ch]
        if k > 0:
            total_forced += k
            total_loss += sum(sorted(loss_opts[ch])[:k])
    if total_forced > 2:
        return None
    return total_forced, total_loss


def check_configs(lexicon, configs, threshold=1786, time_limit=600.0,
                  out_path='results/config_checks.json', log=print):
    """Decide each configuration exactly with the pinned tableau model."""
    from .cstage import solve_tableau
    results = []
    for i, cfg in enumerate(configs):
        placed = set(cfg['placed'])
        crosses = {int(c): w for c, w in cfg['crosses'].items()} \
            if isinstance(next(iter(cfg['crosses']), None), str) \
            else dict(cfg['crosses'])
        import time as _t
        t0 = _t.time()
        fb = exact_fixed_blank_loss('OXYPHENBUTAZONE', placed, crosses)
        if fb is None:
            log(f"[{i+1}/{len(configs)}] needs >2 blanks -> IMPOSSIBLE")
            results.append({'config': cfg, 'status': 'INFEASIBLE',
                            'value': None, 'bound': None, 'solution': None,
                            'reason': 'needs more than 2 blanks'})
            with open(out_path, 'w') as f:
                json.dump(results, f, indent=1, default=str)
            continue
        name, val, bound, sol = solve_tableau(
            lexicon, 'OXYPHENBUTAZONE', 0, time_limit=time_limit,
            fix_placed_exact=placed, fix_crosses=crosses,
            min_score=threshold + 1, known_upper=1794,
            fixed_blank_loss=fb, log=lambda s: None)
        log(f"[{i+1}/{len(configs)}] relaxed={cfg['relaxed_score']} "
            f"placed={sorted(placed)} -> {name} "
            f"val={val} bound={bound} ({_t.time()-t0:.0f}s)", flush=True)
        results.append({'config': cfg, 'status': name, 'value': val,
                        'bound': bound, 'solution': sol})
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    return results


def main():
    import argparse
    import os
    import time
    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--out', default='results/configs.json')
    ap.add_argument('--check', action='store_true',
                    help='run the per-config tableau checks')
    ap.add_argument('--check-time-limit', type=float, default=600.0)
    args = ap.parse_args()
    lex = load()
    if args.check:
        data = json.load(open(args.out))
        assert data['complete'], 'enumeration was not proved complete'
        res = check_configs(lex, data['configs'],
                            threshold=data['threshold'],
                            time_limit=args.check_time_limit)
        bad = [r for r in res if r['status'] not in ('INFEASIBLE',)]
        print(f"\n{len(res)} configs checked; "
              f"{len(bad)} not proved infeasible")
        for r in bad:
            print(' ', r['status'], r['value'], r['config']['placed'])
        return
    t0 = time.time()
    known = []
    import ast
    import re
    try:
        for line in open('results/configs.log'):
            mm = re.match(r'\s*config #(\d+): (\d+) placed=(\([^)]*\)) (\{.*\})',
                          line)
            if mm:
                known.append({'relaxed_score': int(mm.group(2)),
                              'placed': ast.literal_eval(mm.group(3)),
                              'crosses': ast.literal_eval(mm.group(4))})
    except FileNotFoundError:
        pass
    configs, complete = enumerate_configs(lex, threshold=args.threshold,
                                          known_configs=known)
    configs = known + configs
    configs.sort(key=lambda c: -c['relaxed_score'])
    os.makedirs('results', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump({'threshold': args.threshold, 'complete': complete,
                   'count': len(configs), 'configs': configs}, f, indent=1)
    print(f"{len(configs)} configs above {args.threshold} "
          f"(complete={complete}) in {time.time()-t0:.0f}s -> {args.out}")
    for c in configs[:20]:
        print(' ', c['relaxed_score'], c['placed'], c['crosses'])


if __name__ == '__main__':
    main()
