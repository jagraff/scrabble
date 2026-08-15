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


def _append_checkpoint(path, rec, seconds, complete=False,
                       blank_penalty=None, started=False):
    """Append one line of enumeration progress.

    Line-delimited JSON, appended and flushed per solve, so a kill at any
    moment leaves a readable prefix -- a rewritten whole-file snapshot
    could be truncated mid-write and lose everything.

    Each entry records `blank_penalty`, the charging scale that produced
    it. Resuming pre-blocks whatever it reads, so a penalty-off checkpoint
    picked up under the penalty-on default would continue one enumeration
    from another's configurations, mixing two score scales in a single
    list with nothing in the file to reveal it. The scores are only a
    point or two apart, so the result would look entirely ordinary.
    `read_checkpoint` reports the scales it saw and `resume_enumeration`
    refuses to cross them."""
    if path is None:
        return
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    entry = {'seconds': round(seconds, 2)}
    if blank_penalty is not None:
        entry['blank_penalty'] = bool(blank_penalty)
    if started:
        entry['started'] = _time.time()
    elif complete:
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


def checkpoint_scales(path):
    """The set of charging scales recorded in a checkpoint.

    Values are True (penalty on), False (penalty off), or None for an
    entry written before the scale was stamped. A set with more than one
    member means the file already mixes scales; `{None}` means the file
    cannot vouch for itself. Either way it must not be resumed blind.

    Kept separate from `read_checkpoint` rather than widening its tuple:
    callers that only want the configurations should not have to know this
    exists, and every one of them would otherwise need editing to keep
    unpacking.
    """
    scales = set()
    if not path or not os.path.exists(path):
        return scales
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            scales.add(e.get('blank_penalty'))
    return scales


def resume_enumeration(lexicon, S, threshold=1786, time_limit=900.0,
                       checkpoint_dir='results/enum_ckpt', log=print,
                       workers=1, blank_penalty=True):
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
    scales = checkpoint_scales(path) - {None} if known or complete else set()
    if scales and scales != {bool(blank_penalty)}:
        # The recorded configurations were scored on a different scale, so
        # pre-blocking them would continue this enumeration from another
        # one's results and leave the list mixing two scales. The scores
        # differ by only a point or two, so nothing downstream would look
        # wrong.
        raise ValueError(
            f'{path} was written with blank_penalty={sorted(scales)} but '
            f'this run uses blank_penalty={bool(blank_penalty)}; delete the '
            f'checkpoint or re-run on the original scale rather than '
            f'resuming across the two')
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
        checkpoint_path=path, workers=workers,
        blank_penalty=blank_penalty)
    return known + new, done, len(known)


def enumerate_configs(lexicon, word='OXYPHENBUTAZONE', row=0,
                      threshold=1786, time_limit=900.0, max_configs=100000,
                      known_configs=(), log=print, fix_placed=None,
                      checkpoint_path=None, workers=1,
                      blank_penalty=True, prune_unplaced=True,
                      partition=None):
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

    # Mark the checkpoint the moment work starts, before any solving.
    # Otherwise a cell that has not yet found a configuration writes
    # nothing at all -- and a cell grinding through a long infeasibility
    # proof may never find one -- so a directory of busy workers is
    # indistinguishable from a run that never started. The whole point of
    # the checkpoints as a progress record is that silence should be
    # readable, and it is not readable if the file does not exist.
    _append_checkpoint(checkpoint_path, None, 0.0, started=True,
                       blank_penalty=blank_penalty)

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
                _append_checkpoint(checkpoint_path, None, _dt, complete=True,
                                   blank_penalty=blank_penalty)
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
            _append_checkpoint(checkpoint_path, rec, _dt,
                               blank_penalty=blank_penalty)
            log(f"  config #{len(configs)}: {val} placed={placed_cols} "
                f"{chosen}", flush=True)
            # Blocking clause: the next solution must differ in some chosen
            # option, or give a cross word to a column that had none, or
            # change the placed pattern.
            #
            # When `fix_placed` pins the pattern, every `placed[c]` literal
            # is a fixed constant that can never satisfy the clause, and
            # `has_cross[c]` for an unplaced column is forced to 0 for the
            # same reason.  Emitting them adds ~30 dead literals per clause
            # -- roughly 24,000 over an 800-configuration run -- for
            # propagation to chew through and discard.
            clause = []
            for (c, oi), v in x.items():
                if solver.Value(v):
                    clause.append(v.Not())
            for c in range(N):
                if fix_placed is not None and c not in fix_placed:
                    continue          # placed[c]=0 pinned; both literals dead
                if not solver.Value(has_cross[c]):
                    clause.append(has_cross[c])
                if fix_placed is None:
                    clause.append(placed[c].Not() if solver.Value(placed[c])
                                  else placed[c])
            model.AddBoolOr(clause)
        return False

    complete = T.tighten_candidate(
        lexicon, word, row, opts_cache=opts_cache, adj_pairs=adj,
        row1_exact=True, dawg=dawg, mask_filter=[7],
        pairwise_all_rows=True, enumerate_above=threshold,
        enumerate_cb=block_and_collect, fix_placed=fix_placed,
        blank_penalty=blank_penalty, prune_unplaced=prune_unplaced,
        partition=partition)
    return configs, complete


TW_COLS = (0, 7, 14)
DL_COLS = (3, 11)


def _normalise(placed, crosses):
    """(placed set, crosses with int keys), with the model's own invariant
    -- a cross word exists only where a tile was newly placed (`x <=
    placed` in `tighten_candidate`) -- checked rather than assumed."""
    placed = set(placed)
    crosses = {int(c): w for c, w in crosses.items()}
    assert set(crosses) <= placed, (
        f'cross words at unplaced columns {sorted(set(crosses) - placed)}')
    return placed, crosses


def exact_fixed_blank_loss(word, placed, crosses):
    """For a pinned configuration, the number of forced blanks among the
    *fixed, scored* tiles is a constant, and so is the minimum score loss:
    every copy of an over-subscribed letter sits in a known word with a
    known multiplier.  Returns (num_forced, min_loss) or None if the
    configuration needs more than 2 blanks and is impossible outright.

    `placed` is load-bearing: a double-letter square only doubles a tile
    the mover *places*, so a main-word copy at column 3 or 11 loses
    `2 x value x WM` when placed and `value x WM` when it is a
    pre-existing board tile.  Charging the doubled figure unconditionally
    over-states the loss, and an over-stated loss is the unsound
    direction -- it lowers the ceiling and can refute a configuration
    that is not refutable."""
    from .rules import VALUES as V, DISTRIBUTION as D
    placed, crosses = _normalise(placed, crosses)
    wm_prod = 1
    for c in TW_COLS:
        if c in placed:
            wm_prod *= 3
    copies = Counter(word)
    loss_opts = {ch: [] for ch in copies}
    # main-word copies: value x letter-mult x WM, plus the cross word's
    # share if the cell is a hook with a cross word
    for c, ch in enumerate(word):
        lm = 2 if (c in DL_COLS and c in placed) else 1
        wm = 3 if c in TW_COLS else 1
        loss = V[ch] * lm * wm_prod
        if c in crosses:
            loss += wm * V[ch] * lm
        loss_opts.setdefault(ch, []).append(loss)
    for c, w in crosses.items():
        wm = 3 if c in TW_COLS else 1
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


def config_ceiling(word, placed, crosses):
    """A proven upper bound on the true score of a pinned configuration,
    computed in closed form.  Returns None if it needs more than 2 blanks.

    This is what the pre-tableau filter compares against the threshold,
    and it deliberately does *not* read the `relaxed_score` the
    enumeration recorded, for two independent reasons:

      * that value comes from a *feasibility* solve.  The enumeration
        model asserts `total >= threshold + 1` and sets no objective, so
        the solver is free to return any feasible point -- including one
        with `bs` above the forced minimum, whose `total` sits strictly
        below the configuration's ceiling.  Measured on the archived
        lists: 47 of 1903 configurations recorded a value 1 point low.
        Treating a non-maximal value as a ceiling is unsound.
      * the recorded value is on whichever charging scale the enumeration
        used.  With `blank_penalty=True` the model already subtracts face
        value *and* the 2x shortfall, so subtracting the full excess
        again double-charges the same blanks -- 1581 of those 1903
        configurations sit in the region where both fire.

    Recomputing from (placed set, cross words) alone is immune to both:
    every term is determined by the configuration, and the blank loss
    subtracted is the exact minimum from `exact_fixed_blank_loss` rather
    than any relaxed proxy.  Cheaper than a solve, and strictly tighter
    than the value it replaces.
    """
    from .rules import VALUES as V
    placed, crosses = _normalise(placed, crosses)
    fb = exact_fixed_blank_loss(word, placed, crosses)
    if fb is None:
        return None
    _, loss = fb
    wm_prod = 1
    for c in TW_COLS:
        if c in placed:
            wm_prod *= 3
    # main word: letter premiums apply at placed cells only
    total = wm_prod * sum(
        V[ch] * (2 if (c in DL_COLS and c in placed) else 1)
        for c, ch in enumerate(word))
    # cross words: hook tile scored with its own premiums, remainder raw
    for c, w in crosses.items():
        wm = 3 if c in TW_COLS else 1
        lm = 2 if c in DL_COLS else 1
        total += wm * (V[word[c]] * lm + sum(V[ch] for ch in w[1:]))
    if len(placed) == 7:
        total += 50
    return total - loss


def model_blank_charge(word, placed, crosses, *, blank_penalty=False):
    """What the stage-B⁺ objective already subtracted for forced blanks.

    Face value per blank, and -- when the enumeration ran with
    `blank_penalty=True` -- a further `2 x value` for any letter with no
    "cheap cell", i.e. no copy in a cross-word remainder outside a
    triple-word column.  That mirrors `tighten_candidate`'s penalty term
    exactly; for a pinned configuration its `cheap` indicator is
    determined rather than chosen, since the cross words are fixed.

    Soundness of the face-value figure: the inventory constraint is
    `scored usage <= distribution + bs[ch]`, and only `bs` (blanks on
    scored cells) is charged, so an over-subscribed *scored* letter cannot
    be covered by an uncharged blank.  The optimiser therefore sets `bs`
    to exactly the forced excess and pays for it.
    """
    from .rules import VALUES as V, DISTRIBUTION as D
    placed, crosses = _normalise(placed, crosses)
    copies = Counter(word)
    for _, w in crosses.items():
        for ch in w[1:]:
            copies[ch] += 1
    total = 0
    for ch, n in copies.items():
        k = n - D[ch]
        if k <= 0:
            continue
        per_blank = V[ch]
        if blank_penalty:
            cheap = any(c not in TW_COLS and ch in w[1:]
                        for c, w in crosses.items())
            if not cheap:
                per_blank += 2 * V[ch]
        total += k * per_blank
    return total


def blank_cost_gap(word, placed, crosses, *, blank_penalty=False):
    """How much the relaxation *under-charges* this configuration's blanks.

    A blank forfeits whatever it would have scored in place, but the
    stage-B⁺ objective subtracts less than that. For a pinned
    configuration both quantities are determined, so the difference

        (true minimum loss) − (what the model already charged)

    is a constant that may be subtracted from the relaxed score to give a
    still-valid upper bound on the true score. Returns that difference, or
    None if the configuration needs more than 2 blanks (impossible).

    Only the *excess* is subtractable. Taking the whole exact loss would
    double-count what the relaxation already charged, and would refute
    configurations that are not refutable. `blank_penalty` says which
    charge the score being corrected was produced under, and getting it
    wrong is exactly that double-count: with the penalty on, the model
    subtracts face value *and* the 2x shortfall, so passing the default
    here would deduct the same points a second time.

    Prefer `config_ceiling`, which needs no such coordination -- it
    recomputes the whole bound rather than correcting a recorded one.
    """
    fb = exact_fixed_blank_loss(word, placed, crosses)
    if fb is None:
        return None
    _, exact = fb
    charged = model_blank_charge(word, placed, crosses,
                                 blank_penalty=blank_penalty)
    # The model's charge is a lower bound on the true loss, so this is
    # non-negative; clamped rather than asserted so a future over-charge
    # degrades the filter instead of silently raising a bound.
    return max(0, exact - charged)


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
        # Cheap exact-blank filter before the solver.  The ceiling is
        # recomputed from the configuration itself rather than corrected
        # from the recorded `relaxed_score`, which is neither maximal nor
        # of a known charging scale -- see `config_ceiling`.  On the
        # archived runs this disposes of ~95% of configurations with no
        # tableau solve at all.
        ceiling = config_ceiling('OXYPHENBUTAZONE', placed, crosses)
        if ceiling is not None and ceiling <= threshold:
            log(f"[{i+1}/{len(configs)}] relaxed={cfg['relaxed_score']} "
                f"-> exact ceiling {ceiling} <= {threshold}: "
                f"INFEASIBLE (no solve)")
            results.append({'config': cfg, 'status': 'INFEASIBLE',
                            'value': None, 'bound': ceiling,
                            'solution': None,
                            'reason': f'exact blank cost puts this '
                                      f'configuration\'s ceiling at '
                                      f'{ceiling} <= {threshold}'})
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
