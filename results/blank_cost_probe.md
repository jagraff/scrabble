# Probe: how far is the blank charge from the true cost?

For each of the 14 surviving patterns, tier 2's *optimal* configuration was
recovered and its exact blank loss computed with
`finalize.exact_fixed_blank_loss`, then compared with what the relaxation
charged (face value only).

| pattern | ceiling | charged | exact | argmax true ≤ | slack |
|---|---:|---:|---:|---:|---:|
| (0,2,3,7,11,13,14) | 1787 | 0 | 0 | 1787 | 1 |
| (0,1,3,7,11,13,14) | 1788 | 6 | 12 | 1782 | 2 |
| (0,2,3,4,7,11,14) | 1788 | 4 | 10 | 1782 | 2 |
| (0,1,3,7,8,11,14) | 1790 | 6 | 12 | 1784 | 4 |
| (0,2,3,7,8,11,14) | 1790 | 6 | 12 | 1784 | 4 |
| (0,1,2,3,7,11,14) | 1791 | 3 | 9 | 1785 | 5 |
| (0,1,3,4,7,11,14) | 1791 | 6 | 18 | 1779 | 5 |
| (0,2,3,7,9,11,14) | 1791 | 3 | 9 | 1785 | 5 |
| (0,2,3,7,10,11,14) | 1791 | 3 | 9 | 1785 | 5 |
| (0,1,3,5,7,11,14) | 1792 | 6 | 12 | 1786 | 6 |
| (0,1,3,6,7,11,14) | 1792 | 3 | 9 | 1786 | 6 |
| (0,2,3,6,7,11,14) | 1792 | 3 | 9 | 1786 | 6 |
| (0,1,3,7,9,11,14) | 1794 | 3 | 9 | 1788 | 8 |
| (0,1,3,7,10,11,14) | 1794 | 6 | 12 | 1788 | 8 |

"slack" is ceiling − 1786, the margin a pattern has to lose before it dies.

## What this shows

The under-charge is **6 to 18 points**, against a slack of **1 to 8**. The
correction is the same size as or larger than the whole margin, in every
row. So exact blank costing is the right lever: it is not a rounding
detail, it dominates the quantity that decides these patterns.

## What this does NOT show

**It does not prove any pattern dies.** The number in "argmax true ≤" is
the true score of the configuration that maximises the *charged*
objective. Under exact costing the solver would not choose that
configuration — it would re-optimise and pick one whose blanks are cheaper,
possibly scoring higher than the figure shown. Killing the argmax does not
kill the pattern; that is the classic second-best error.

The only sound way to use this is to put the exact per-cell blank cost
**inside** the model, so the solver optimises the true objective and the
resulting optimum is a genuine upper bound (Lemma 1). Then, and only then,
does a ceiling below 1,787 refute a pattern.

## Why it is still worth doing

Two of the three patterns that survive even this optimistic reading are the
1,794 pair, which are also the two that defeated the tableau. If exact
costing drops the other eleven below the threshold, the open set shrinks
from six to a couple, and the ~30 h of tier-3 re-enumeration may be
avoidable entirely rather than merely repeated.
