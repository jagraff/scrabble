"""A machine-verifiable record of what a pipeline run actually produced.

`provenance.stamp()` says what the environment was. It does not say which
files came out of it, and the committed stamp had drifted thirty commits
behind the results sitting next to it -- which is the failure this exists to
prevent. A reader could not tell whether `tier3_configs.json` was produced
by the code in the tree or by something three weeks older.

The manifest binds the two together: the environment, the parameters, and a
SHA-256 of every artifact and every cell checkpoint, in one file whose own
digest can be quoted in the write-up. `verify()` re-hashes everything and
reports what moved.

Two properties it asserts that no individual checkpoint can:

  * *coverage* -- every cell the partition defines has a file, and every
    file corresponds to a cell that was asked for. A cell that was never
    launched leaves no checkpoint, and a directory of 49 files where 50
    were expected otherwise looks exactly like a directory of 50.
  * *uniformity* -- every cell was produced under one solver build, one
    interpreter, one commit. Checkpoint identity deliberately does not gate
    on the solver version, because an infeasibility proof is a fact about
    the model rather than about the prover; the cost of that choice is that
    a mixed-solver artifact is possible, and this is where it is caught.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os

from . import identity as ID
from .provenance import LEXICON_PATH, stamp

DEFAULT_PATH = 'results/MANIFEST.json'


def source_dirty() -> bool | None:
    """Whether any *source* file is uncommitted.

    `stamp()['git_dirty']` is true for the whole of any run, because the
    results it is regenerating are themselves tracked files -- so it cannot
    answer the question that matters, which is whether the code that
    produced them was committed. This looks only at the package and its
    tests. None if git is unavailable.
    """
    from .provenance import _git

    out = _git('status', '--porcelain', '--', 'scrabble_max', 'tests')
    return None if out is None else bool(out.strip())


def file_digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _cell_record(path: str) -> dict:
    """One checkpoint, as the manifest sees it.

    Reads the header for identity and the body for the outcome. The two are
    kept side by side deliberately: `complete` without an identity is not a
    certificate, and an identity without `complete` is an unfinished cell.
    """
    from .finalize import checkpoint_header, read_checkpoint

    header, ident = checkpoint_header(path)
    configs, complete, timings, corrupt = read_checkpoint(path)
    rec = {
        'file': os.path.relpath(path),
        'sha256': file_digest(path),
        'identity': ident,
        'configs': len(configs),
        'complete': bool(complete),
        'corrupt': bool(corrupt),
        'seconds': round(sum(timings), 1),
    }
    if header is not None:
        rec['pattern'] = header.get('pattern')
        rec['cell_index'] = header.get('cell_index')
        rec['block'] = header.get('block')
    return rec


def _environment_of(path: str) -> dict | None:
    """The environment stamp a checkpoint recorded, for the uniformity
    check. Absent on unstamped legacy files."""
    try:
        with open(path) as f:
            first = json.loads(f.readline() or '{}')
    except (OSError, json.JSONDecodeError):
        return None
    return first.get('environment') if 'header' in first else None


def build(*, threshold=1786, n_blocks=4, ckpt_dir='results/enum_cells',
          artifacts=(), run=None) -> dict:
    """Assemble the manifest for a completed run.

    `artifacts` are the pipeline's result files; each is hashed as it
    stands. `run` is the run manifest whose namespaced directory holds the
    cells -- passing it lets coverage be checked against the partition that
    was actually asked for rather than against whatever happens to be on
    disk."""
    if run is None:
        run = ID.run_manifest(lexicon_path=LEXICON_PATH, threshold=threshold,
                              word='OXYPHENBUTAZONE', n_blocks=n_blocks)
    cell_dir = ID.run_dir(ckpt_dir, run)
    cells = [_cell_record(p)
             for p in sorted(glob.glob(os.path.join(cell_dir, '*.jsonl')))]

    envs, mixed = {}, {}
    for p in sorted(glob.glob(os.path.join(cell_dir, '*.jsonl'))):
        e = _environment_of(p) or {}
        for k in ('ortools', 'python', 'platform', 'git_commit'):
            envs.setdefault(k, set()).add(e.get(k))
    for k, vs in envs.items():
        if len(vs) > 1:
            mixed[k] = sorted(str(v) for v in vs)

    files = []
    for a in artifacts:
        if os.path.exists(a):
            files.append({'file': a, 'sha256': file_digest(a),
                          'bytes': os.path.getsize(a)})
        else:
            files.append({'file': a, 'sha256': None, 'missing': True})

    refutation = refutation_summary()

    man = {
        'schema': 1,
        'environment': stamp(),
        'source_dirty': source_dirty(),
        'refutation': refutation,
        'run': run,
        'run_digest': ID.digest(run),
        'cell_dir': cell_dir,
        'cells': cells,
        'artifacts': files,
        'summary': {
            'cells': len(cells),
            'cells_complete': sum(1 for c in cells if c['complete']),
            'cells_corrupt': sum(1 for c in cells if c['corrupt']),
            'cells_unstamped': sum(1 for c in cells if not c['identity']),
            'configurations': sum(c['configs'] for c in cells),
            'solver_seconds': round(sum(c['seconds'] for c in cells), 1),
            'mixed_environment': mixed,
            'refuted': refutation['refuted'],
            'undecided': refutation['undecided'],
            'above_threshold': refutation['above_threshold'],
        },
    }
    return man


def expected_cells(patterns, run, ckpt_dir='results/enum_cells'):
    """Every (pattern, cell) the partition defines, as identity digests.

    Coverage is checked against this rather than against the file listing:
    a cell that was never launched writes no file, and a short directory is
    otherwise indistinguishable from a complete one."""
    from .lexicon import load
    from .partition import _cell_tag, choose_pivots, make_product_cells

    lex = load()
    out = {}
    for S in patterns:
        S = tuple(sorted(S))
        pivots = choose_pivots(lex, S)
        cols = [c for c, _ in pivots]
        for i, constraints in enumerate(make_product_cells(pivots,
                                                           run['n_blocks'])):
            cell = ID.cell_manifest(run, pattern=S, cell_index=i,
                                    constraints=constraints)
            out[ID.digest(cell)] = os.path.join(
                ID.run_dir(ckpt_dir, run), f'{_cell_tag(S, cols, i)}.jsonl')
    return out


def _config_key(cfg):
    """A configuration's identity, independent of how it was serialised.

    Cross-word keys are column numbers that survive a JSON round trip as
    strings, so both sides are normalised to strings before comparing.
    """
    placed = tuple(sorted(int(c) for c in (cfg.get('placed') or ())))
    crosses = tuple(sorted((str(k), v)
                           for k, v in (cfg.get('crosses') or {}).items()))
    return placed, crosses


def refutation_summary(check_dir='results/tier3_checks',
                       configs_path='results/tier3_configs.json') -> dict:
    """Every enumerated configuration must have a verdict, and every
    verdict must be a refutation.

    The enumeration's completeness is what the cell checkpoints certify.
    This is the other half, and it was certified by nothing: the refutation
    phase writes per-pattern verdict files that no manifest hashed and no
    check counted, so "every configuration refuted" rested on a line of
    console output. A configuration that was enumerated and then never
    checked would leave no trace at all.

    `decomposed.json` records configurations CP-SAT left undecided and the
    decomposition then closed; those count as refuted only when the
    decomposition reports every branch refuted.
    """
    out = {'checked': 0, 'refuted': 0, 'undecided': 0, 'above_threshold': 0,
           'enumerated': 0, 'missing_verdicts': 0, 'unmatched_verdicts': 0,
           'files': []}
    enumerated_keys = set()
    if os.path.exists(configs_path):
        with open(configs_path) as f:
            payload = json.load(f)
        out['enumerated'] = sum(p['count'] for p in payload['patterns'])
        out['threshold'] = payload.get('threshold')
        for p in payload['patterns']:
            # A pattern may record only its count. Then identity matching
            # is not available for it and the comparison falls back to
            # counts below, rather than crashing or -- worse -- silently
            # treating the missing entries as absent verdicts.
            for c in (p.get('configs') or []):
                enumerated_keys.add(_config_key(c))
    verdict_keys = set()

    decomposed = {}
    dpath = os.path.join(check_dir, 'decomposed.json')
    if os.path.exists(dpath):
        with open(dpath) as f:
            for rec in json.load(f):
                key = json.dumps(rec['crosses'], sort_keys=True)
                decomposed[(tuple(rec['placed']), key)] = rec['refuted']
        out['decomposed'] = len(decomposed)
        out['decomposed_refuted'] = sum(1 for v in decomposed.values() if v)

    for path in sorted(glob.glob(os.path.join(check_dir, '*.json'))):
        if os.path.basename(path) == 'decomposed.json':
            # Hashed like the rest -- it is the record that the undecided
            # configurations were closed -- but it holds decomposition
            # outcomes, not per-configuration verdicts, so it is not
            # counted as one.
            out['files'].append({'file': os.path.relpath(path),
                                 'sha256': file_digest(path),
                                 'rows': len(decomposed)})
            continue
        with open(path) as f:
            rows = json.load(f)
        out['files'].append({'file': os.path.relpath(path),
                             'sha256': file_digest(path), 'rows': len(rows)})
        for r in rows:
            out['checked'] += 1
            verdict_keys.add(_config_key(r.get('config') or {}))
            value = r.get('value') or 0
            thresh = out.get('threshold') or 1786
            if value > thresh:
                out['above_threshold'] += 1
            elif r.get('status') == 'INFEASIBLE':
                out['refuted'] += 1
            else:
                cfg = r.get('config') or {}
                key = (tuple(cfg.get('placed') or ()),
                       json.dumps(cfg.get('crosses') or {}, sort_keys=True))
                if decomposed.get(key):
                    out['refuted'] += 1
                else:
                    out['undecided'] += 1
    # By identity, not by count. Two sets of the same size can be disjoint,
    # so counting verdicts against enumerated configurations would accept a
    # directory of verdicts left over from a different enumeration -- which
    # is exactly how a stale checkpoint went unnoticed on the archived run.
    if len(enumerated_keys) == out['enumerated'] and out['enumerated']:
        out['matched_by'] = 'identity'
        out['missing_verdicts'] = len(enumerated_keys - verdict_keys)
        out['unmatched_verdicts'] = len(verdict_keys - enumerated_keys)
    else:
        # Not every configuration was listed, so identity matching would
        # report the unlisted ones as missing. Say which comparison was
        # actually made rather than letting the weaker one pass for the
        # stronger.
        out['matched_by'] = 'count'
        out['missing_verdicts'] = max(0, out['enumerated'] - out['checked'])
    return out


def check_refutation(summary: dict) -> list[str]:
    """Complaints about the refutation phase."""
    problems = []
    if summary['above_threshold']:
        problems.append(f"{summary['above_threshold']} configuration(s) "
                        f'scored above the threshold')
    if summary['undecided']:
        problems.append(f"{summary['undecided']} configuration(s) are "
                        f'UNDECIDED and were not closed by decomposition')
    if summary['missing_verdicts']:
        problems.append(
            f"{summary['missing_verdicts']} enumerated configuration(s) have "
            f"no verdict: {summary['enumerated']} enumerated against "
            f"{summary['checked']} checked")
    if summary.get('unmatched_verdicts'):
        problems.append(
            f"{summary['unmatched_verdicts']} verdict(s) are for "
            f'configurations this enumeration never produced, so they were '
            f'left by a different run and cannot certify this one')
    if summary['enumerated'] and not summary['checked']:
        problems.append('no verdict files at all, but configurations were '
                        'enumerated')
    return problems


def check_coverage(man: dict, patterns) -> list[str]:
    """Complaints about cells that are missing, extra, or not finished."""
    want = expected_cells(patterns, man['run'],
                          os.path.dirname(man['cell_dir']))
    got = {c['identity']: c for c in man['cells'] if c['identity']}
    problems = []
    for ident, path in want.items():
        if ident not in got:
            problems.append(f'cell missing entirely: {path}')
        elif not got[ident]['complete']:
            problems.append(f"cell not complete: {got[ident]['file']}")
    for ident, c in got.items():
        if ident not in want:
            problems.append(f"cell not in the partition: {c['file']}")
    for c in man['cells']:
        if not c['identity']:
            problems.append(f"cell has no identity header: {c['file']}")
        if c['corrupt']:
            problems.append(f"cell has an unparseable line: {c['file']}")
    return problems


def check_witness(path='results/rack_schedule.json', expect_score=1786):
    """The 1,786 board must still be shown reachable.

    The upper-bound half of the theorem says nothing beats 1,786; the other
    half says 1,786 is attained *and* reachable in a legal two-player game.
    That half is a file on disk like any other, and a run in which the
    witness quietly stopped verifying would otherwise be certified as
    happily as one in which it did.
    """
    problems = []
    if not os.path.exists(path):
        return [f'{path}: the reachability witness is missing']
    with open(path) as f:
        w = json.load(f)
    if not w.get('feasible'):
        problems.append(f'{path}: no rack/bag schedule was found')
    if not w.get('verified'):
        problems.append(f"{path}: the witness did not re-verify "
                        f"({w.get('detail')})")
    if not w.get('board_replay_ok'):
        problems.append(f"{path}: the move sequence does not replay to the "
                        f"record board ({w.get('board_replay')})")
    if w.get('final_move_score') != expect_score:
        problems.append(f"{path}: the final move scores "
                        f"{w.get('final_move_score')}, expected "
                        f'{expect_score}')
    return problems


def verify(path=DEFAULT_PATH) -> list[str]:
    """Re-hash everything the manifest names and report what moved.

    Includes the refutation verdict files: recording a hash that nothing
    re-checks is worse than not recording it, because it reads as coverage
    while providing none."""
    with open(path) as f:
        man = json.load(f)
    problems = []
    groups = [man.get('cells', []), man.get('artifacts', []),
              (man.get('refutation') or {}).get('files', [])]
    for group in groups:
        for rec in group:
            f_ = rec['file']
            if rec.get('sha256') is None:
                problems.append(f'{f_}: recorded as missing')
                continue
            if not os.path.exists(f_):
                problems.append(f'{f_}: gone since the manifest was written')
                continue
            now = file_digest(f_)
            if now != rec['sha256']:
                problems.append(f'{f_}: changed since the manifest was '
                                f'written ({rec["sha256"][:12]} -> '
                                f'{now[:12]})')
    mixed = man.get('summary', {}).get('mixed_environment') or {}
    for k, vs in mixed.items():
        problems.append(f'cells were produced under mixed {k}: {vs}')
    if man.get('source_dirty'):
        problems.append('the run was made with uncommitted source changes, '
                        'so its commit does not identify the code')
    return problems


def write(man: dict, path=DEFAULT_PATH) -> str:
    """Write the manifest and return its own digest.

    The digest is computed over the canonical serialisation, not over the
    file, so the value quoted in the write-up does not change if the file is
    later reformatted."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(man, f, indent=1, sort_keys=True, default=str)
    return ID.digest(man)


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true',
                    help='re-hash what an existing manifest names')
    ap.add_argument('--path', default=DEFAULT_PATH)
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--blocks', type=int, default=4)
    ap.add_argument('--ckpt-dir', default='results/enum_cells')
    ap.add_argument('--artifacts', default=','.join([
        'results/candidates.json', 'results/tight_bounds.json',
        'results/bound_six_tiles.json', 'results/pattern_row1.json',
        'results/blank_penalty_tier2.json', 'results/tier3_configs.json',
        'results/rack_schedule.json', 'results/reachability.log',
    ]))
    a = ap.parse_args()

    if a.verify:
        problems = verify(a.path)
        if problems:
            print(f'{len(problems)} PROBLEM(S):')
            for p in problems:
                print('   ', p)
            return 1
        print(f'{a.path}: everything it names is unchanged')
        return 0

    man = build(threshold=a.threshold, n_blocks=a.blocks,
                ckpt_dir=a.ckpt_dir,
                artifacts=[s for s in a.artifacts.split(',') if s])
    digest = write(man, a.path)
    s = man['summary']
    print(f"run {man['run_digest'][:12]} -> {man['cell_dir']}")
    print(f"cells        : {s['cells']} ({s['cells_complete']} complete, "
          f"{s['cells_corrupt']} corrupt, {s['cells_unstamped']} unstamped)")
    print(f"configurations: {s['configurations']}")
    print(f"solver time  : {s['solver_seconds'] / 3600:.1f} h")
    r = man['refutation']
    print(f"refutation   : {r['checked']} checked, {r['refuted']} refuted, "
          f"{r['undecided']} undecided, {r['above_threshold']} above the "
          f"threshold")
    if r.get('decomposed'):
        print(f"  of which    {r['decomposed_refuted']}/{r['decomposed']} "
              f"closed by decomposition")
    if s['mixed_environment']:
        print(f"MIXED ENVIRONMENT: {s['mixed_environment']}")
    print(f"artifacts    : {len(man['artifacts'])}")
    print(f'-> {a.path}')
    print(f'manifest digest: {digest}')

    problems = check_refutation(man['refutation']) + check_witness()
    try:
        from .tier3 import survivors
        problems += check_coverage(man, survivors())
    except (OSError, ValueError) as e:
        print(f'coverage not checked: {e}')
        problems.append(f'coverage could not be checked: {e}')
    if problems:
        print(f'\n{len(problems)} PROBLEM(S):')
        for p in problems[:20]:
            print('   ', p)
        return 1
    print('coverage: every cell of every surviving pattern is present and '
          'complete; every enumerated configuration has a refutation; the '
          '1786 witness verifies and replays to the record board')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
