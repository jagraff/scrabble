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

    man = {
        'schema': 1,
        'environment': stamp(),
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
        },
    }
    return man


def expected_cells(patterns, run, ckpt_dir='results/enum_cells'):
    """Every (pattern, cell) the partition defines, as identity digests.

    Coverage is checked against this rather than against the file listing:
    a cell that was never launched writes no file, and a short directory is
    otherwise indistinguishable from a complete one."""
    from .lexicon import load
    from .partition import _cell_tag, choose_pivot, make_cells

    lex = load()
    out = {}
    for S in patterns:
        S = tuple(sorted(S))
        pivot, n_options = choose_pivot(lex, S)
        for i, block in enumerate(make_cells(n_options, run['n_blocks'])):
            cell = ID.cell_manifest(run, pattern=S, pivot=pivot,
                                    cell_index=i, block=block)
            out[ID.digest(cell)] = os.path.join(
                ID.run_dir(ckpt_dir, run), f'{_cell_tag(S, pivot, i)}.jsonl')
    return out


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


def verify(path=DEFAULT_PATH) -> list[str]:
    """Re-hash everything the manifest names and report what moved."""
    with open(path) as f:
        man = json.load(f)
    problems = []
    for group in ('cells', 'artifacts'):
        for rec in man.get(group, []):
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
    if s['mixed_environment']:
        print(f"MIXED ENVIRONMENT: {s['mixed_environment']}")
    print(f"artifacts    : {len(man['artifacts'])}")
    print(f'-> {a.path}')
    print(f'manifest digest: {digest}')

    try:
        from .tier3 import survivors
        problems = check_coverage(man, survivors())
    except (OSError, ValueError) as e:
        print(f'coverage not checked: {e}')
        return 0
    if problems:
        print(f'\n{len(problems)} COVERAGE PROBLEM(S):')
        for p in problems[:20]:
            print('   ', p)
        return 1
    print('coverage: every cell of every surviving pattern is present and '
          'complete')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
