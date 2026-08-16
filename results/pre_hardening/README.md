# Pre-hardening results, archived

The state of `results/` immediately before the clean re-run described in
`../soundness_remediation.md`. Archived rather than deleted for two
reasons: the 50 cell checkpoints are the evidence of the original tier-3
run and deleting them would destroy the audit trail, and `check_rerun.py`'s
directional checks need something to compare the re-run against.

These files are **not** a certificate. The cell checkpoints carry no
identity header, so nothing on disk says which computation produced them.
That is precisely what the re-run fixes.

Provenance of this archive: everything here was produced at or before
commit `e18096e`, under the environment recorded in `../PROVENANCE.json`
(which itself names commit `5ba050a`, thirty commits earlier than the
results beside it — the drift that motivated the manifest).

Expected values, for comparison against the re-run:

| quantity | value |
|---|---:|
| tier-2 patterns evaluated | 165 |
| tier-2 survivors | 14 |
| survivors after the blank penalty | 10 |
| tier-3 cells | 50 |
| tier-3 configurations | 1322 |
| configurations above 1786 | 0 |

Stage-B bounds and the |S| ≤ 6 per-mask cells are in `tight_bounds.json`
and `bound_six_tiles.json`. Every stage-B bound was a proved optimum
(`detail.proved_optimal`); the per-mask cells recorded no status at all,
which is the gap the re-run closes.
