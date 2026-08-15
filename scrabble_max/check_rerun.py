"""Directional checks for the post-`cross_options`-fix recomputation.

The fix deleted a dedup that was throwing away legal cross-word options,
so the relaxation's feasible region strictly *grows*. That gives every
recomputed quantity a known direction, and a violation indicts the fix
rather than the old data:

  * every bound may only rise (a larger region cannot have a smaller max);
  * the tier-2 survivor set may only grow (patterns are eliminated when
    their bound falls at or below the threshold, and bounds rose);
  * every per-pattern configuration list may only lengthen — the blocking
    loop stops when the model goes infeasible, and a *missing* option made
    it stop earlier.

Run against `results/pre_fix/` (archived at commit abb16c1) and the
current `results/`. Anything that moves the wrong way is a bug in the
fix, not a correction to the old numbers, and should stop the pipeline.

Note the asymmetry in what rising bounds mean for the write-up: they can
only make theorems weaker. Theorem 2 needs the runner-up to stay at or
below 1,778; Theorem 3 needs both `|S| ≤ 6` optima to stay below 1,786.
"""

from __future__ import annotations

import json
import os

OLD = 'results/pre_fix'
NEW = 'results'


def _load(path):
    with open(path) as f:
        return json.load(f)


def _present(*paths):
    return all(os.path.exists(p) for p in paths)


def check_stage_b(old_dir=OLD, new_dir=NEW):
    """Every (word,row) bound may only rise; per-mask cells likewise."""
    o, n = (f'{old_dir}/tight_bounds.json', f'{new_dir}/tight_bounds.json')
    if not _present(o, n):
        return ['stage B: files missing'], {}
    old = {(r['word'], r['row']): r for r in _load(o)}
    new = {(r['word'], r['row']): r for r in _load(n)}
    bad, moved = [], {}
    for k, r in new.items():
        if k not in old:
            continue
        if r['tight_bound'] < old[k]['tight_bound']:
            bad.append(f'stage B {k}: {old[k]["tight_bound"]} -> '
                       f'{r["tight_bound"]} (DECREASED)')
        elif r['tight_bound'] > old[k]['tight_bound']:
            moved[k] = (old[k]['tight_bound'], r['tight_bound'])
        for mask, v in (r.get('per_mask') or {}).items():
            ov = (old[k].get('per_mask') or {}).get(mask)
            if ov is not None and v < ov:
                bad.append(f'stage B {k} mask {mask}: {ov} -> {v} (DECREASED)')
    return bad, moved


def check_six_tiles(old_dir=OLD, new_dir=NEW):
    o, n = (f'{old_dir}/bound_six_tiles.json',
            f'{new_dir}/bound_six_tiles.json')
    if not _present(o, n):
        return ['six-tile: files missing'], {}
    old, new = _load(o), _load(n)
    bad, moved = [], {}
    for k, v in new.items():
        if k not in old:
            continue
        if k.endswith('per_mask'):
            # per-TW-mask cells: check each one.  These are where the bug
            # actually bit -- eight rose while the {0,7,14} mask that
            # Theorem 3 rests on did not.
            for mask, mv in (v or {}).items():
                ov = (old[k] or {}).get(mask)
                if ov is None:
                    continue
                if mv < ov:
                    bad.append(f'six-tile {k}[{mask}]: {ov} -> {mv} '
                               f'(DECREASED)')
                elif mv > ov:
                    moved[f'{k}[{mask}]'] = (ov, mv)
            continue
        if v < old[k]:
            bad.append(f'six-tile {k}: {old[k]} -> {v} (DECREASED)')
        elif v > old[k]:
            moved[k] = (old[k], v)
    return bad, moved


def check_tier2(old_dir=OLD, new_dir=NEW):
    """Bounds may only rise; the survivor set may only grow."""
    o, n = (f'{old_dir}/pattern_row1.json', f'{new_dir}/pattern_row1.json')
    if not _present(o, n):
        return ['tier 2: files missing'], {}, set(), set()
    old = {tuple(r['placed']): r for r in _load(o)}
    new = {tuple(r['placed']): r for r in _load(n)}
    bad, moved = [], {}
    for S, r in new.items():
        if S not in old:
            continue
        ob, nb = old[S]['row1_bound'], r['row1_bound']
        # None means infeasible, i.e. -inf: any finite bound is a rise
        if ob is None and nb is None:
            continue
        if ob is None:
            moved[S] = ('infeasible', nb)
        elif nb is None:
            bad.append(f'tier 2 {S}: {ob} -> infeasible (DECREASED)')
        elif nb < ob:
            bad.append(f'tier 2 {S}: {ob} -> {nb} (DECREASED)')
        elif nb > ob:
            moved[S] = (ob, nb)
    old_keep = {S for S, r in old.items() if r['kept']}
    new_keep = {S for S, r in new.items() if r['kept']}
    # Only judge the survivor set once the rerun has actually visited every
    # pattern.  On a partial run the unvisited ones are simply absent, which
    # is not the same as eliminated -- comparing early reports every
    # not-yet-reached survivor as a spurious shrink.
    complete = len(new) >= len(old)
    if complete:
        for S in old_keep - new_keep:
            bad.append(f'tier 2 {S}: was a survivor, now eliminated (SHRANK)')
    return bad, moved, old_keep, new_keep, complete, len(new), len(old)


def check_tier3_configs(old_dir=OLD, new_dir=NEW):
    """Each pattern's configuration list may only lengthen, and the old
    entries must all reappear."""
    od, nd = f'{old_dir}/pattern_configs', f'{new_dir}/pattern_configs'
    if not os.path.isdir(od) or not os.path.isdir(nd):
        return ['tier 3: config dirs missing'], {}
    bad, grew = [], {}
    for fn in sorted(os.listdir(od)):
        if not fn.endswith('.json') or not os.path.exists(f'{nd}/{fn}'):
            continue

        def key(rec):
            cr = {int(k): v for k, v in dict(rec['config']['crosses']).items()}
            return tuple(sorted(cr.items()))

        o = {key(r) for r in _load(f'{od}/{fn}')}
        n = {key(r) for r in _load(f'{nd}/{fn}')}
        missing = o - n
        if missing:
            bad.append(f'tier 3 {fn}: {len(missing)} configs from the old '
                       f'list are absent (SHRANK)')
        if len(n) != len(o):
            grew[fn] = (len(o), len(n))
    return bad, grew


def verdict_breakdown(path):
    """How tier-2 verdicts were reached. Derived rather than read, because
    `proved_optimal` is recorded False on infeasibility too."""
    recs = _load(path)
    out = {'infeasible': 0, 'proved_optimum': 0, 'timeout_bound': 0}
    for r in recs:
        if r['infeasible']:
            out['infeasible'] += 1
        elif r['proved_optimal']:
            out['proved_optimum'] += 1
        else:
            out['timeout_bound'] += 1
    return out, len(recs), sum(r['kept'] for r in recs)


def main():
    violations = []

    bad, moved = check_stage_b()
    violations += bad
    print(f'stage B      : {len(bad)} violations, {len(moved)} bounds rose')
    for k, (a, b) in sorted(moved.items()):
        print(f'               {k}: {a} -> {b}')

    bad, moved = check_six_tiles()
    violations += bad
    print(f'six-tile     : {len(bad)} violations, {len(moved)} bounds rose')

    bad, moved, old_keep, new_keep, complete, n_new, n_old = check_tier2()
    violations += bad
    print(f'tier 2       : {len(bad)} violations, {len(moved)} bounds rose')
    if not complete:
        print(f'               PARTIAL: {n_new} of {n_old} patterns computed; '
              f'survivor-set comparison deferred')
    else:
        print(f'               survivors {len(old_keep)} -> {len(new_keep)}'
              f'  (new: {sorted(new_keep - old_keep)})')
    if os.path.exists(f'{NEW}/pattern_row1.json'):
        vb, total, kept = verdict_breakdown(f'{NEW}/pattern_row1.json')
        print(f'               {total} patterns: {vb["infeasible"]} infeasible,'
              f' {vb["proved_optimum"]} proved optima,'
              f' {vb["timeout_bound"]} timeout-derived')
        if vb['timeout_bound']:
            print('               WARNING: a timeout-derived bound is a '
                  'weaker claim; raise --row1-time-limit and re-run those')

    bad, grew = check_tier3_configs()
    violations += bad
    print(f'tier 3 lists : {len(bad)} violations, {len(grew)} lists changed')

    print()
    if violations:
        print(f'{len(violations)} DIRECTIONAL VIOLATION(S) — the fix is '
              f'suspect, not the old data:')
        for v in violations:
            print('   ', v)
        return 1
    print('all directional checks pass: nothing moved the wrong way')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
