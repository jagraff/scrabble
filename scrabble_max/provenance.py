"""Environment stamp for result files.

A computational proof is only checkable if you know what produced it.
`stamp()` records the pieces that can change a recorded number without
changing the argument: the solver version (CP-SAT's presolve and search
heuristics move between releases, and a timeout-derived
`BestObjectiveBound` moves with them), the interpreter, the exact
lexicon, the commit, and the hash seed the run used.

The hash seed matters here for a specific reason: `lexicon.load()`
returns a frozenset, so anything that iterates it without sorting is
order-dependent.  That is not merely cosmetic — it once made
`cross_options` retain a hash-seed-dependent representative of each
anagram class.  Runs should set PYTHONHASHSEED explicitly.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys

LEXICON_PATH = 'data/NWL2023.txt'


def _git(*args) -> str | None:
    try:
        out = subprocess.run(('git',) + args, capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def lexicon_digest(path: str = LEXICON_PATH) -> dict:
    """SHA-256 of the lexicon file plus its word count."""
    h = hashlib.sha256()
    n = 0
    with open(path, 'rb') as f:
        for line in f:
            h.update(line)
            if line.strip():
                n += 1
    return {'path': path, 'sha256': h.hexdigest(), 'words': n}


def stamp() -> dict:
    """Everything needed to say which run produced a result file."""
    try:
        from ortools.sat.python import cp_model
        ortools_version = cp_model.CpSolver().solver_version
    except Exception:                                    # pragma: no cover
        try:
            import ortools
            ortools_version = getattr(ortools, '__version__', 'unknown')
        except Exception:
            ortools_version = 'unknown'

    dirty = _git('status', '--porcelain')
    return {
        'git_commit': _git('rev-parse', 'HEAD'),
        'git_dirty': bool(dirty) if dirty is not None else None,
        'python': sys.version.split()[0],
        'platform': f'{platform.system()}/{platform.machine()}',
        'ortools': ortools_version,
        'pythonhashseed': os.environ.get('PYTHONHASHSEED'),
        'lexicon': lexicon_digest(),
    }


def write(path: str = 'results/PROVENANCE.json') -> dict:
    s = stamp()
    with open(path, 'w') as f:
        json.dump(s, f, indent=1)
    return s


if __name__ == '__main__':
    print(json.dumps(write(), indent=1))
