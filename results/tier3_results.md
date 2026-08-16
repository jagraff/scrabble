# Tier 3: the last open case, closed

Tier 2 left ten placed patterns that no bound could eliminate. Tier 3
enumerates every configuration each of them admits, then decides each one
exactly. This records what that produced.

## Enumeration

All ten patterns enumerated to completion — every partition cell ended in
INFEASIBLE, which is what makes the lists exhaustive rather than merely
long.

| pattern | configurations |
|---|---:|
| (0,1,3,7,10,11,14) | 623 |
| (0,1,3,4,7,11,14) | 165 |
| (0,1,3,7,9,11,14) | 154 |
| (0,2,3,7,10,11,14) | 101 |
| (0,1,3,6,7,11,14) | 97 |
| (0,1,2,3,7,11,14) | 95 |
| (0,2,3,7,9,11,14) | 43 |
| (0,2,3,6,7,11,14) | 30 |
| (0,2,3,7,11,13,14) | 14 |
| (0,1,3,7,11,13,14) | 0 |
| **total** | **1322** |

29.7 minutes, `results/tier3_configs.json`.

Five of these patterns had counts predicted in advance from the archived
pre-fix lists, by evaluating the in-model blank penalty arithmetically.
Four came in exactly:

| pattern | predicted | actual |
|---|---:|---:|
| (0,1,2,3,7,11,14) | 95 | **95** |
| (0,1,3,4,7,11,14) | 165 | **165** |
| (0,2,3,7,9,11,14) | 43 | **43** |
| (0,2,3,7,11,13,14) | 14 | **14** |
| (0,1,3,7,11,13,14) | 5 | 0 |

The prediction and the measurement were made independently, in different
sessions. The one miss goes in the safe direction: 0 configurations means
that pattern is refuted with nothing left to check.

## Refutation

| how decided | count |
|---|---:|
| exact blank ceiling, no solve | 1063 |
| CP-SAT infeasibility proof | 258 |
| undecided at the 600s limit | 1 |

28 minutes for the 1321. **No configuration was shown to exceed 1786.**

### What the 258 "hard" cases actually were

Not hard, and not about score. Re-running a sample of twelve with the score
constraint removed entirely — asking only whether *any* legal board
realises the configuration — returned **INFEASIBLE 12 of 12, in ~2.8s
each**. These configurations describe boards that cannot exist at all; the
solver refutes them by propagation and the number 1786 never enters the
proof.

That is why the phase took 28 minutes rather than days, and it is worth
recording because it was not what anyone predicted: the expensive-looking
half of tier 3 was the cheap half.

## The one that resisted

`(0,1,3,7,10,11,14)` with cross words

    OPACIFICATIONS / XEROSES / PREADJUSTING / BRAINWASHING
    AMELIORATIVE / ZOOGAMETE / EQUALITY

Exact ceiling 1787, so if realisable at all it beats the record by exactly
one point. It was still UNKNOWN after 1300s, having neither produced a
board nor excluded one — and, unlike its 258 siblings, UNKNOWN even with
the score constraint dropped. It has no shallow structural contradiction,
so the solver must search rather than propagate.

Its static features are unremarkable: 67 cross tiles against a median of
68, 143 free cells against 142, one forced blank like most. Nothing marks
it out, which is why the diagnosis had to be behavioural rather than
structural.

**It decomposes.** Pinning a single board cell and recursing on whatever
survives refuted it completely:

```
split (1,4) into 10 branches (depth 0)
  split (1,6) into 10 branches (depth 1)
    split (1,13) into 10 branches (depth 2)
      split (1,2) into 11 branches (depth 3)
        split (1,9) into 14 branches (depth 4)
          split (1,8) into 18 branches (depth 5)
          all 18 branches refuted at (1,8)
        all 14 branches refuted at (1,9)
      all 11 branches refuted at (1,2)
    all 10 branches refuted at (1,13)
  all 10 branches refuted at (1,6)
all 10 branches refuted at (1,4)

REFUTED: True   open branches: 0
180 solves, 506s
```

**Reproduced independently.** A second implementation — breadth-first over
a parallel work queue, one model per configuration with branches varied
through CP-SAT assumptions rather than rebuilt — reaches the same result
by a different route:

```
depth 0:  1 solved,  0 refuted, 1 open
depth 1: 10 solved,  9 refuted, 1 open
depth 2: 10 solved,  7 refuted, 3 open
depth 3: 30 solved, 27 refuted, 3 open
depth 4: 33 solved, 30 refuted, 3 open
depth 5: 42 solved, 39 refuted, 3 open
depth 6: 54 solved, 54 refuted, 0 open
REFUTED: True, 180 solves, 140s
```

Same 180 solves, same open count at every depth, 3.6x faster. The two
differ in traversal order, in parallelism, and in whether the model is
rebuilt per branch, so agreeing on the tree shape is evidence about the
result rather than about one implementation.

Soundness rests on the option sets being exhaustive — every legal board
puts *something* in the pinned cell, so refuting every possibility refutes
the configuration. Two ways that can go wrong, both hit while building it:

* narrowing a cell's letters to those with tiles still spare. A blank can
  supply a letter whose copies are used up, so that partition is not
  exhaustive and refuting all of its branches proves nothing.
* counting a timeout as a refutation. UNKNOWN is undecided and is reported
  as such.

The sharpest check available: run the same refuter against the **record's
own configuration** at threshold 1785, where a 1786 board demonstrably
exists. It refuted 9 of 10 branches and left standing exactly the branch
containing the record. A non-exhaustive partition would have refuted all
ten.

## Status of the claim

Subject to the conditions below, no legal NWL2023 play exceeds 1786, and
since 1786 is achieved and reachable in a legal two-player game, it is the
maximum.

Conditions, none of which this run removes:

1. **NWL2023 only.** Collins/CSW is a larger lexicon and would very
   plausibly admit more. Nothing here speaks to it.
2. **One play, not a game total.**
3. **Computer-assisted, not machine-checked.** It rests on CP-SAT's
   correctness, on the lexicon file, and on the encodings modelling
   Scrabble faithfully.
4. **Every stage must be a relaxation** — only ever enlarging the feasible
   set. This is the property the whole chain hangs on and the one where
   this project has had real bugs (the `cross_options` dedup shrank the
   region, the unsound direction, and invalidated results that had to be
   recomputed).

## Incident: orphaned workers

The first tier-3 launch was stopped with `pkill -f scrabble_max.tier3`,
which matches only the parent — `ProcessPoolExecutor` workers do not carry
it in their command line. Five workers survived for three hours,
competing for the same four cores as the replacement run and appending to
the same checkpoint directory. 5 of 50 cells finished with two
completion markers and duplicate configurations, and every solve in that
run took roughly twice as long as it should have.

Nothing was lost — no line was torn, and both writers were enumerating the
same cell with identical settings. But files written by two uncoordinated
processes cannot be certified, so the five cells were quarantined and
re-enumerated from clean checkpoints. **All five reproduced exactly**:
95→95, 120→120, 23→23, 19→19, 14→14, one completion marker each.

Fixed in `partition.py`: both pools now install a SIGINT/SIGTERM handler
that terminates workers before exiting.

## Reproduce

```bash
python -m scrabble_max.tier3 --workers 4 --blocks 4
python -m scrabble_max.status --dir results/enum_cells --by-pattern
python -m scrabble_max.status --checks --watch 20
```
