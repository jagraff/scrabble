"""Bind a checkpoint to the computation it certifies.

A cell checkpoint makes two claims. The first is a list of configurations,
which is a list of witnesses and re-checkable on its own. The second is
`complete`: the blocking-clause loop reached INFEASIBLE, so no further
configuration in this cell reaches the threshold. That second claim is a
proof obligation discharged, and it is only meaningful about *the model it
was proved for*. Reusing it under a different model is how a run reports
exhaustive coverage of a space it never searched.

Before this module the only thing binding a checkpoint to its computation
was the file name (pattern, pivot, cell index) and the charging scale. The
block count was in neither, and cell `i` under `--blocks 4` covers option
indices `i mod 4` while under `--blocks 8` it covers `i mod 8`. Re-running
a `--blocks 4` directory at `--blocks 8` therefore reused five files whose
union no longer covers the option set, and reported the result complete.

What is gated and what is merely recorded
-----------------------------------------

The asymmetry decides it: rejecting a valid checkpoint costs recomputation,
accepting an invalid one costs a false theorem. So a field is gated unless
there is a positive reason to exempt it.

Gated -- these determine the model instance, so a mismatch means the stored
proof is about a different proposition:

    lexicon digest, threshold, word, row, blank_penalty, prune_unplaced,
    n_blocks, pattern, pivot, cell index, explicit block membership,
    and a digest of the sources that build the model.

Recorded but not gated -- OR-Tools version, Python, platform, git commit:

    An infeasibility proof is a fact about the model, not about the solver
    that found it, so a proof from 9.14 and one from 9.15 establish the
    same proposition. Gating on the solver version would discard sound work
    on every upgrade. The legitimate worry it answers -- "a solver build
    turns out to be buggy and I must find everything it touched" -- is
    served by recording the version in every header and asserting
    *uniformity* across the finished manifest, which is the stronger
    property anyway because it is checked over the whole artifact rather
    than pairwise at resume time.

`PYTHONHASHSEED` is gated, and unset is refused outright rather than
recorded as `None`. `os.environ.get` is a weak proxy: with the variable
unset every worker records `None` and so compares equal to every other,
while each actually runs under a different random seed -- the check would
report a match in exactly the case that is dangerous. `require_hash_seed`
therefore refuses to start.

The source digest covers the modules that build the model rather than the
git commit. Gating on the commit would let a typo fix in a markdown file
invalidate hours of solver output, which trains the operator to pass
`--allow-unstamped`, and a gate that is routinely bypassed protects
nothing.
"""

from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# The modules whose text can change which model gets built. `bounds.py` and
# `board.py` are deliberately absent: neither is on the path that emits a
# cell's CP-SAT model, and including them would invalidate checkpoints for
# edits that cannot reach the proof.
MODEL_SOURCES = ('rules.py', 'lexicon.py', 'tighten.py', 'finalize.py',
                 'partition.py', 'cstage.py')


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def model_source_digest(sources=MODEL_SOURCES, root=HERE) -> str:
    """SHA-256 over the model-building sources, name-tagged and ordered.

    Names are folded in with the contents so that renaming or reordering
    files cannot leave the digest unchanged, and the length prefix keeps
    two files' contents from running together into a single ambiguous
    stream."""
    h = hashlib.sha256()
    for name in sorted(sources):
        with open(os.path.join(root, name), 'rb') as f:
            body = f.read()
        h.update(f'{name}:{len(body)}\n'.encode())
        h.update(body)
    return h.hexdigest()


def lexicon_digest(path: str) -> str:
    """SHA-256 of the lexicon file.

    Byte-for-byte over the file rather than over the parsed word set: a
    reordering or a duplicate line does not change the set but does change
    `build_line_dawg`'s insertion order, and the automaton's state
    numbering with it."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def require_hash_seed() -> str:
    """The pinned hash seed, or refuse to run.

    See the module docstring: an unset seed cannot be checked for
    consistency after the fact, because every process reports the same
    `None` while running under different seeds."""
    seed = os.environ.get('PYTHONHASHSEED')
    if seed is None or seed == 'random':
        raise RuntimeError(
            'PYTHONHASHSEED is not pinned. lexicon.load() returns a '
            'frozenset, and iteration order has twice reached the emitted '
            'model; an unpinned seed cannot be certified after the fact '
            'because every process records the same "unset". '
            'Run with: export PYTHONHASHSEED=0')
    return seed


def digest(manifest: dict) -> str:
    """SHA-256 of a manifest, canonically serialised.

    Sorted keys and no whitespace: the digest must depend on the values,
    not on the order a dict happened to be built in."""
    return _sha256_bytes(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())


def run_manifest(*, lexicon_path, threshold, word, row=0, blank_penalty=True,
                 prune_unplaced=True, n_blocks, sources=MODEL_SOURCES,
                 root=HERE, lexicon_sha=None) -> dict:
    """The gated fields shared by every cell of one enumeration run.

    `lexicon_sha` lets a caller hash the file once and reuse it across the
    cells instead of re-reading a 3 MB lexicon per cell."""
    return {
        'schema': 1,
        'kind': 'enumeration-run',
        'lexicon_sha256': (lexicon_sha if lexicon_sha is not None
                           else lexicon_digest(lexicon_path)),
        'threshold': int(threshold),
        'word': word,
        'row': int(row),
        'blank_penalty': bool(blank_penalty),
        'prune_unplaced': bool(prune_unplaced),
        'n_blocks': int(n_blocks),
        'model_sources_sha256': model_source_digest(sources, root),
        'pythonhashseed': require_hash_seed(),
    }


def cell_manifest(run: dict, *, pattern, cell_index, constraints) -> dict:
    """One cell's gated fields: the run's, plus which slice of the space.

    `constraints` is the cell's [(column, block), ...] -- one entry per
    pivot column. Each block is stored as its explicit sorted membership,
    not as an index. The index is what the file name already carried, and
    the index is precisely what stayed constant while the meaning changed
    underneath it when `n_blocks` moved.

    Storing every constraint, rather than a single pivot, is what keeps
    the identity honest once a cell is the product of several columns: two
    cells can agree on their first pivot and differ on the second, and a
    manifest that recorded only the first would call them the same cell.
    """
    items = []
    for col, block in constraints:
        # None is the "this column takes no cross word" part, which is not
        # a set of option indices and must not be confused with the empty
        # set -- an empty block would enumerate nothing at all.
        items.append([int(col),
                      None if block is None else sorted(int(i) for i in block)])
    items.sort(key=lambda t: t[0])
    return {
        **run,
        'kind': 'enumeration-cell',
        'pattern': [int(c) for c in sorted(pattern)],
        'cell_index': int(cell_index),
        'constraints': items,
    }


def run_dir(ckpt_dir: str, run: dict, width: int = 12) -> str:
    """Namespace a checkpoint directory by the run it belongs to.

    The gate alone is enough to be sound; this makes stale reuse impossible
    by construction as well, so a regression in the check cannot silently
    resurrect the original failure. Twelve hex characters is 48 bits, far
    past collision range for the handful of runs a directory ever holds,
    and short enough to stay readable in a path."""
    return os.path.join(ckpt_dir, f'run-{digest(run)[:width]}')


def describe_mismatch(stored: dict, expected: dict) -> str:
    """Which gated fields differ, for an error message worth reading.

    A bare hash mismatch tells the operator that something is wrong but not
    what, and the likeliest causes -- a changed threshold, a changed block
    count -- are one-word answers."""
    keys = sorted(set(stored) | set(expected))
    diffs = []
    for k in keys:
        a, b = stored.get(k, '<absent>'), expected.get(k, '<absent>')
        if a != b:
            if isinstance(a, str) and isinstance(b, str) and len(a) == 64:
                a, b = a[:12] + '...', b[:12] + '...'
            diffs.append(f'{k}: stored={a!r} current={b!r}')
    return '; '.join(diffs) if diffs else 'no field differs (digest bug?)'
