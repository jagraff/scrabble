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
import os
import time as _time
from collections import Counter

from ortools.sat.python import cp_model

from .rules import DISTRIBUTION, N, VALUES
from . import tighten as T

LETTERS = [chr(ord('A') + i) for i in range(26)]


def _append_checkpoint(path, rec, seconds, complete=False):
    """Append one line of enumeration progress.

    Line-delimited JSON, appended and flushed per solve, so a kill at any
    moment leaves a readable prefix -- a rewritten whole-file snapshot
    could be truncated mid-write and lose everything."""
    if path is None:
        return
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    entry = {'seconds': round(seconds, 2)}
    if complete:
        entry['complete'] = True
    else:
        entry['config'] = {'placed': list(rec['placed']),
                           'crosses': {str(k): v
                                       for k, v in rec['crosses'].items()},
                           'relaxed_score': rec['relaxed_score']}
    with open(path, 'a') as f:
        f.write(json.dumps(entry) + '\n')
        f.flush()


def repair_checkpoint(path):
    """Drop a trailing partial line so the next append starts cleanly.

    Without this, appending after a torn write concatenates the new record
    onto the broken one, producing a single unparseable line that swallows
    *both* -- the torn record and a perfectly good one after it. Observed:
    a 17-line file yielding 15 configurations. Returns True if it repaired
    anything."""
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    with open(path, 'rb') as f:
        f.seek(-1, os.SEEK_END)
        if f.read(1) == b'\n':
            return False
        f.seek(0)
        data = f.read()
    cut = data.rfind(b'\n')
    with open(path, 'wb') as f:
        f.write(data[:cut + 1] if cut >= 0 else b'')
    return True


def read_checkpoint(path):
    """(configs, complete, timings, corrupt) from a checkpoint file.

    `corrupt` is True if any line failed to parse. A caller must not
    honour `complete` when it is set: a lost line could have been a
    configuration, and returning a short list while claiming exhaustiveness
    is the one failure mode that would make checkpointing worse than not
    having it. Re-running the closing infeasibility proof is cheap
    insurance against that."""
    configs, complete, timings, corrupt = [], False, [], False
    if not path or not os.path.exists(path):
        return configs, complete, timings, corrupt
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                corrupt = True
                continue
            timings.append(e.get('seconds', 0.0))
            if e.get('complete'):
                complete = True
            elif 'config' in e:
                c = e['config']
                configs.append({'placed': tuple(c['placed']),
                                'crosses': {int(k): v
                                            for k, v in c['crosses'].items()},
                                'relaxed_score': c['relaxed_score']})
    return configs, complete, timings, corrupt


def resume_enumeration(lexicon, S, threshold=1786, time_limit=900.0,
                       checkpoint_dir='results/enum_ckpt', log=print,
                       workers=1):
    """Enumerate one pattern's configurations, resuming if interrupted.

    Returns (configs, complete, resumed_from). Safe to call repeatedly:
    if the checkpoint already records completion it does no solving at
    all, and otherwise it pre-blocks what is already known so no work is
    repeated."""
    tag = ''.join(f'{c:02d}' for c in sorted(S))
    path = f'{checkpoint_dir}/{tag}.jsonl'
    if repair_checkpoint(path):
        log('  repaired a torn final line in the checkpoint')
    known, complete, timings, corrupt = read_checkpoint(path)
    if complete and corrupt:
        # a lost line may have been a configuration; re-run rather than
        # return a short list that claims to be exhaustive
        log('  checkpoint claims complete but has an unparseable line: '
            're-verifying instead of trusting it')
        complete = False
    if complete:
        log(f'  checkpoint complete: {len(known)} configs, no solving needed')
        return known, True, len(known)
    if known:
        log(f'  resuming from {len(known)} checkpointed configs '
            f'({sum(timings) / 60:.0f} min already spent)')
    new, done = enumerate_configs(
        lexicon, threshold=threshold, time_limit=time_limit,
        fix_placed=set(S), known_configs=known, log=log,
        checkpoint_path=path, workers=workers)
    return known + new, done, len(known)


def enumerate_configs(lexicon, word='OXYPHENBUTAZONE', row=0,
                      threshold=1786, time_limit=900.0, max_configs=100000,
                      known_configs=(), log=print, fix_placed=None,
                      checkpoint_path=None, workers=1):
    """All (placed, crosses) configs with row-1-exact relaxed score
    > threshold, for the all-TWs mask.

    `checkpoint_path` makes the loop killable. Each configuration is
    appended to that file as it is found, together with the seconds the
    solve took, and a terminal `complete` marker is written when the model
    finally goes infeasible. Resuming means loading the file and passing
    its configurations back as `known_configs`, which pre-blocks them so
    the loop continues from where it stopped rather than rediscovering
    them. `resume_enumeration` does both halves.

    The per-solve timings exist to answer where the time goes: whether the
    cost is spread over many solves or concentrated in the final
    infeasibility proof. That determines which optimisation is worth
    doing, and the loop was previously silent about it.
    """
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
        # One worker, deliberately.  Measured on pattern (0,2,3,7,11,13,14),
        # four seeds each: median 14.6s at 1 worker against 24.2s at 8 and
        # 30.1s at 4 -- single-threaded is faster in absolute terms, not
        # merely cheaper, and its spread is far tighter (13.7-17.4 against
        # 18.2-36.9).  CP-SAT's portfolio does not help this model, so the
        # extra workers duplicate effort and pay coordination cost.
        # Parallelism belongs at the pattern level instead: eight
        # single-worker patterns on eight cores is ~13x the throughput of
        # one eight-worker pattern.  The enumeration loop within a pattern
        # is inherently sequential -- each solve depends on the blocking
        # clauses added by the previous one -- so this is the only axis
        # available.
        solver.parameters.num_search_workers = workers
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
            _t0 = _time.time()
            status = solver.Solve(model)
            _dt = _time.time() - _t0
            if status == cp_model.INFEASIBLE:
                # the closing solve: its cost is the infeasibility proof
                _append_checkpoint(checkpoint_path, None, _dt, complete=True)
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
            rec = {'placed': placed_cols, 'crosses': chosen,
                   'relaxed_score': val}
            configs.append(rec)
            _append_checkpoint(checkpoint_path, rec, _dt)
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


def blank_cost_gap(word, placed, crosses):
    """How much the relaxation *under-charges* this configuration's blanks.

    The stage-B⁺ objective subtracts only each blank's face value, but a
    blank actually forfeits whatever it would have scored in place. For a
    pinned configuration both quantities are determined, so the difference

        (true minimum loss) − (face value charged)

    is a constant that may be subtracted from the relaxed score to give a
    still-valid upper bound on the true score. Returns that difference, or
    None if the configuration needs more than 2 blanks (impossible).

    Only the *excess* is subtractable. Taking the whole exact loss would
    double-count the face value the relaxation already charged, and would
    refute configurations that are not refutable.

    Soundness of the face-value figure: the inventory constraint is
    `scored usage <= distribution + bs[ch]`, and only `bs` (blanks on
    scored cells) is charged, so an over-subscribed *scored* letter cannot
    be covered by an uncharged blank. The optimiser therefore sets `bs` to
    exactly the forced excess and pays `k · value` for it.
    """
    from .rules import VALUES as V, DISTRIBUTION as D
    fb = exact_fixed_blank_loss(word, placed, crosses)
    if fb is None:
        return None
    _, exact = fb
    copies = Counter(word)
    for _, w in crosses.items():
        for ch in w[1:]:
            copies[ch] += 1
    charged = sum((n - D[ch]) * V[ch] for ch, n in copies.items()
                  if n > D[ch])
    return exact - charged


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
        # Cheap exact-blank filter before the solver.  The relaxation
        # charges blanks only face value; subtracting the excess of their
        # true cost keeps the bound valid, and on the archived runs this
        # disposes of ~95% of configurations with no tableau solve at all.
        gap = blank_cost_gap('OXYPHENBUTAZONE', placed, crosses)
        if gap is not None and cfg['relaxed_score'] - gap <= threshold:
            log(f"[{i+1}/{len(configs)}] relaxed={cfg['relaxed_score']} "
                f"-blank_gap={gap} -> {cfg['relaxed_score'] - gap} "
                f"<= {threshold}: INFEASIBLE (no solve)")
            results.append({'config': cfg, 'status': 'INFEASIBLE',
                            'value': None, 'bound': cfg['relaxed_score'] - gap,
                            'solution': None,
                            'reason': f'exact blank cost exceeds the charge by '
                                      f'{gap}; corrected bound '
                                      f'{cfg["relaxed_score"] - gap} '
                                      f'<= {threshold}'})
            with open(out_path, 'w') as f:
                json.dump(results, f, indent=1, default=str)
            continue
        name, val, bound, sol = solve_tableau(
            lexicon, 'OXYPHENBUTAZONE', 0, time_limit=time_limit,
            fix_placed_exact=placed, fix_crosses=crosses,
            min_score=threshold + 1, known_upper=1794,
            fixed_blank_loss=fb, log=lambda s: None, verbose=False)
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
