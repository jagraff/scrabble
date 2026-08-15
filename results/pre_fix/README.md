# Pre-fix baseline

Snapshot of every computed result as of commit `a158768`, i.e. **before**
the `tighten.cross_options` deduplication fix.

Extracted from git rather than the working tree, because stage B was
already overwriting `results/tight_bounds.json` in place when this was
taken.

These numbers are **not trusted**. The old `cross_options` deduplicated
cross-word options by the remainder's letter multiset while callers read
the remainder's order, so legal options were deleted, the feasible region
was too small, and computed maxima may sit below the true maxima. They
are kept only as the comparison baseline for the recomputation.

## What the recomputation must satisfy

The fix strictly enlarges the feasible region, so every comparison has a
known direction. A violation means the fix is wrong, not the old data.

| quantity | baseline | required after fix |
|---|---|---|
| stage-B bound per candidate | see `tight_bounds.json` | **≥** baseline |
| max over all but OXYPHENBUTAZONE row 0 | 1778 | ≥ 1778 (Thm 2 needs ≤ 1778, so **= 1778** or Thm 2 weakens) |
| six-tile bound, row 0 / row 14 | 1730 / 1706 | ≥ baseline (Thm 3 needs < 1786) |
| tier-2 bound per pattern | see `pattern_row1.json` | **≥** baseline |
| tier-2 survivors | 14 | **⊇** the baseline 14 |
| tier-3 config list per pattern | see `pattern_configs/` | **⊇** the baseline list |

Note the asymmetry: bounds may only rise, and rising bounds can only make
theorems weaker, never stronger. Theorem 2 survives only if the runner-up
stays at or below 1,778; Theorem 3 survives only if both six-tile bounds
stay below 1,786.

## Baseline figures

* stage B: 17 candidates, max 1798 (OXYPHENBUTAZONE row 0), runner-up 1778
* six-tile: row 0 = 1730, row 14 = 1706
* tier 2: 165 patterns → 14 survivors (140 infeasible, 11 proved-optimal
  eliminations, 14 proved-optimal survivors, no timeouts)
* tier 3: 8 of 14 patterns refuted over 1,903 configurations
