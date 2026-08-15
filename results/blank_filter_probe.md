# Probe: a pre-tableau blank filter

Applied to the 8 refuted patterns' archived configuration lists
(`results/pre_fix/pattern_configs/`, 1,903 configurations).

For a fixed configuration the forced blanks are determined: every copy of
an over-subscribed letter sits in a known word at a known multiplier. The
relaxation charges each blank only its **face value**; the true cost is the
value it would have scored in place. Subtracting the *difference* gives a
valid upper bound on the configuration's true score, so a configuration
whose corrected bound falls at or below 1,786 is refuted with no tableau
solve at all.

| pattern | configs | killed by blanks | still need tableau |
|---|---:|---:|---:|
| (0,1,2,3,7,11,14) | 396 | 385 | 11 |
| (0,1,3,4,7,11,14) | 584 | 528 | 56 |
| (0,1,3,7,8,11,14) | 9 | 9 | 0 |
| (0,1,3,7,11,13,14) | 21 | 16 | 5 |
| (0,2,3,4,7,11,14) | 26 | 26 | 0 |
| (0,2,3,7,8,11,14) | 27 | 27 | 0 |
| (0,2,3,7,9,11,14) | 824 | 818 | 6 |
| (0,2,3,7,11,13,14) | 16 | 2 | 14 |
| **total** | **1903** | **1811 (95%)** | **92** |

## Correctness note

A first version of this subtracted the *whole* exact loss from the relaxed
score and reported 99%. That was wrong and unsound in the dangerous
direction: the relaxed score already subtracts face value for each blank,
so subtracting the full exact loss again double-counts and would refute
configurations that are not refutable. Only the excess over face value may
be subtracted. The corrected figure is 95%.

## What it is worth

The refutation phase shrinks about twentyfold — for the 824-configuration
pattern, 6 tableau solves instead of 824, i.e. seconds instead of the 57
minutes it actually took.

It does **not** solve the expensive half. Across the 8 patterns,
enumeration was roughly 85% of the wall time (2 h 05 m against 19 m,
4 h 24 m against 29 m, 7 h 34 m against 57 m). Cutting refutation to
near-zero saves on the order of 15% of a re-run, not the bulk of it. The
enumeration loop is still the thing that needs replacing.
