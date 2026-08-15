"""Parallel enumeration of one pattern, by partitioning the solution space.

The blocking-clause loop is inherently sequential: each solve depends on
the clause the previous one added, so a pattern cannot be spread across
cores by running its solves concurrently. That is true, and it is why the
only parallel axis recorded so far was running whole patterns side by
side.

But whole-pattern parallelism does not help the thing that actually sets
the finish time. The configuration counts are severely skewed -- 824, 584,
396, then 27, 26, 21, 16, 9 -- so the wall-clock is one pattern's
sequential loop, and adding cores does nothing for it.

The loop is only sequential *within a fixed solution space*. Split that
space into disjoint cells and each cell has its own independent loop:

    every configuration either gives the pivot column no cross word, or
    gives it exactly one of its options; so partitioning the option
    indices into blocks B_1..B_K partitions the configurations into K+1
    cells, and their union is the whole enumeration.

Each cell is enumerated by an ordinary blocking-clause loop that knows
nothing of the others. Two properties make this safe to rely on:

  * *disjoint* -- a configuration's pivot option lands in exactly one
    block, so no cell can emit another's configuration. `enumerate` checks
    this rather than assuming it.
  * *covering* -- every option index is in some block, and the no-cross
    case is its own cell, so nothing falls between the cells. This is the
    half that completeness depends on, and it is asserted below.

A cell is also strictly more constrained than the whole, so its solves
propagate better; the speed-up is not only from the cores.

The cost is one extra closing infeasibility proof per cell. With K well
above the core count and dynamic scheduling, that is bounded and small
against a loop measured in hours.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import tighten as T
from .finalize import enumerate_configs, read_checkpoint, repair_checkpoint
from .lexicon import load
from .rules import N

WORD = 'OXYPHENBUTAZONE'


def _check_passthrough():
    """Fail early and legibly if `enumerate_configs` cannot take a cell.

    Without this the first failure is a TypeError raised inside a
    ProcessPoolExecutor worker, surfacing as an opaque BrokenProcessPool
    or a traceback with no obvious connection to the missing argument."""
    import inspect

    from .finalize import enumerate_configs
    params = inspect.signature(enumerate_configs).parameters
    missing = [p for p in ('partition', 'prune_unplaced') if p not in params]
    if missing:
        raise RuntimeError(
            f'finalize.enumerate_configs is missing {missing}; partitioned '
            f'enumeration needs those arguments passed through to '
            f'tighten_candidate')


def choose_pivot(lexicon, S, word=WORD):
    """The placed column with the most cross options.

    Partitioning on the widest column gives the finest control over cell
    size; a narrow one could not be split into enough cells to balance."""
    best, best_n = None, -1
    for c in sorted(S):
        n = len(T.cross_options(lexicon, word[c], 0))
        if n > best_n:
            best, best_n = c, n
    return best, best_n


def make_cells(n_options, n_blocks):
    """Round-robin option indices into blocks, plus the no-cross cell.

    Round-robin rather than contiguous ranges: the option lists are built
    in a systematic order, so contiguous blocks would concentrate the
    high-scoring options -- and hence nearly all the configurations -- in
    a few cells, leaving the rest to finish instantly and the loaded ones
    to set the finish time anyway."""
    n_blocks = max(1, min(n_blocks, n_options))
    blocks = [frozenset(range(k, n_options, n_blocks)) for k in
              range(n_blocks)]
    covered = set().union(*blocks) if blocks else set()
    assert covered == set(range(n_options)), (
        'blocks must cover every option index, or configurations using an '
        'uncovered option would be silently missed')
    assert sum(len(b) for b in blocks) == n_options, 'blocks must be disjoint'
    return [None] + blocks          # None = "pivot column has no cross word"


def _cell_tag(S, pivot, i):
    """Checkpoint name for one cell.

    The pattern has to be in the name. Two patterns can choose the same
    pivot column -- column 3 is placed in all ten survivors and has the
    widest option list, so it is the pivot for most of them -- and with
    only pivot and cell index in the name they would share checkpoint
    files. The resume path pre-blocks whatever it reads, so one pattern
    would silently start from another's configurations, and the completion
    marker would end its loop early with a list that is not its own."""
    tag = ''.join(f'{c:02d}' for c in sorted(S))
    return f'{tag}_p{pivot:02d}c{i:03d}'


_LEX = None


def _lexicon():
    """One lexicon per worker process, not one per cell.

    `enumerate_configs` still rebuilds `cross_options` and the DAWG on
    every call (~6s), which is charged once per cell rather than once per
    process. Against cells that run for minutes that is tolerable; it
    would be worth threading a prebuilt cache through if cells ever get
    small enough for it to show."""
    global _LEX
    if _LEX is None:
        _LEX = load()
    return _LEX


def _run_cell(args):
    S, pivot, cell_index, block, threshold, ckpt_dir, time_limit = args
    lexicon = _lexicon()
    path = (os.path.join(ckpt_dir, f'{_cell_tag(S, pivot, cell_index)}.jsonl')
            if ckpt_dir else None)
    if path:
        repair_checkpoint(path)
        known, complete, _, corrupt = read_checkpoint(path)
        if complete and not corrupt:
            return cell_index, known, True, 0.0, True
        if corrupt:
            known, complete = [], False
    else:
        known = []
    t0 = time.time()
    new, done = enumerate_configs(
        lexicon, threshold=threshold, fix_placed=set(S), known_configs=known,
        checkpoint_path=path, workers=1, blank_penalty=True,
        prune_unplaced=True, partition=(pivot, block),
        time_limit=time_limit, log=lambda *a, **k: None)
    return cell_index, known + new, done, time.time() - t0, False


def _key(cfg):
    return (tuple(sorted(cfg['placed'])),
            tuple(sorted((int(k), v) for k, v in cfg['crosses'].items())))


def enumerate_pattern(S, n_blocks=24, threshold=1786, max_workers=4,
                      ckpt_dir=None, time_limit=3600.0, log=print):
    """Enumerate pattern `S` across cells in parallel.

    Returns (configs, complete). `complete` is True only if every cell
    finished -- a single unfinished cell means the enumeration is not
    exhaustive and no completeness claim may be made from it."""
    _check_passthrough()
    lexicon = load()
    pivot, n_options = choose_pivot(lexicon, S)
    cells = make_cells(n_options, n_blocks)
    log(f'pattern {tuple(sorted(S))}: pivot column {pivot} '
        f'({n_options} options) -> {len(cells)} cells, '
        f'{max_workers} workers')
    if ckpt_dir:
        os.makedirs(ckpt_dir, exist_ok=True)

    jobs = [(tuple(sorted(S)), pivot, i, block, threshold, ckpt_dir,
             time_limit) for i, block in enumerate(cells)]
    found, seen, incomplete = [], {}, []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_run_cell, j): j[2] for j in jobs}
        for done_n, fut in enumerate(as_completed(futs), 1):
            i, cfgs, complete, dt, cached = fut.result()
            if not complete:
                incomplete.append(i)
            for cfg in cfgs:
                k = _key(cfg)
                if k in seen:
                    # cells are disjoint by construction; if two ever emit
                    # the same configuration the partition is wrong and
                    # every count derived from it is wrong with it
                    raise AssertionError(
                        f'cells {seen[k]} and {i} both emitted {k}')
                seen[k] = i
                found.append(cfg)
            log(f'  [{done_n}/{len(cells)}] cell {i}: {len(cfgs)} configs, '
                f'complete={complete} {"(cached)" if cached else f"{dt:.0f}s"}'
                f' | running total {len(found)}', flush=True)

    complete = not incomplete
    log(f'pattern {tuple(sorted(S))}: {len(found)} configs, '
        f'complete={complete}, {time.time() - t0:.0f}s wall')
    if incomplete:
        log(f'  UNFINISHED cells {incomplete}: not exhaustive')
    return found, complete


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--pattern', required=True,
                    help='comma-separated placed columns, e.g. 0,2,3,7,11,13,14')
    ap.add_argument('--blocks', type=int, default=24)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--ckpt-dir', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    S = tuple(int(x) for x in a.pattern.split(','))
    cfgs, complete = enumerate_pattern(
        S, n_blocks=a.blocks, threshold=a.threshold,
        max_workers=a.workers, ckpt_dir=a.ckpt_dir)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w') as f:
            json.dump({'pattern': list(S), 'complete': complete,
                       'count': len(cfgs),
                       'configs': [{'placed': list(c['placed']),
                                    'crosses': {str(k): v for k, v
                                                in c['crosses'].items()},
                                    'relaxed_score': c['relaxed_score']}
                                   for c in cfgs]}, f, indent=1)
        print(f'-> {a.out}')


if __name__ == '__main__':
    main()
