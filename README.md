# The Maximum Single-Turn Score in Scrabble (NWL2023)

Is **1,786** — Bob Lucassen's OXYPHENBUTAZONE construction
([woogles.io, May 2024](https://blog.woogles.io/posts/2024-05-27-new-theoretical-highest-play-discovered/))
— the highest score a single turn can earn in North American Scrabble
under NWL2023?

## Status: open — and Theorem 4 is provisional

**The headline claim is not proved.** What the argument shows is that the
search space collapses to fourteen explicit configurations, of which eight
were closed and six remain open.

> ### ⚠ Recomputation after a soundness bug (2026-08-15)
>
> A **soundness bug** was found in `tighten.cross_options`: it
> deduplicated cross-word options by the remainder's letter *multiset*,
> while callers read the remainder's *order*. YARE and YEAR are both valid
> Y-hooks with remainder multiset {A,E,R} but inward letters A and E; only
> one survived. Deleting options shrinks the model's feasible region, so
> its optimum can fall **below** the true maximum — and those optima are
> used as upper bounds. Anything eliminated on "bound ≤ 1,786" may have
> been eliminated wrongly.
>
> The bug is fixed. **Stage B has been recomputed and every bound came
> back identical**, so Theorems 2 and 3 stand. **Theorem 4 is still
> provisional** — the tier-2 reduction has not yet been rerun, and the
> count of fourteen patterns can only grow. REPORT.md §5 has the
> analysis; PROOFS.md carries the full status table.

| | Result | Status |
|---|---|---|
| **Thm 1** | Any play not filling an entire edge row scores ≤ **1,656** | complete — stage A only |
| **Thm 2** | Any play but OXYPHENBUTAZONE on row 0 scores ≤ **1,778** | reconfirmed |
| **Thm 3** | A record-beating play covers all three TWs and places 7 tiles | reconfirmed |
| **Thm 4** | Its placed set is one of **14** listed patterns; all score ≤ **1,794** | **provisional** |
| **Thm 5** | The published 1,786 construction is legal and scores exactly 1,786 | complete — rules engine only |
| **Thm 6** | 1,786 is reachable in a legal two-player game (26 moves) | complete |
| **§8** | The 14 patterns are all refuted | **6 of 14 open**, and see above |

Theorems 1, 5 and 6 are untouched by the bug: stage A never calls
`cross_options`, and the record's verification and reachability go through
the rules engine rather than the solver stack.

Where this lands if the numbers hold — Theorem 2 would again give the
sharpest complete statement, since 1,778 < 1,786:

> **Any play beating the record is OXYPHENBUTAZONE across an edge row —
> the record's own geometry — and scores at most 1,798.**

Of the fourteen surviving patterns, 1,903 configurations were enumerated
and every one refuted. Those individual refutations still stand — each was
decided by the full tableau. What the bug invalidates is the claim that
the enumeration was *exhaustive*: the loop stops when the model goes
infeasible, and a missing cross-word option makes it stop **earlier**, so
`complete=True` is precisely the flag that cannot survive. Re-enumeration
can only lengthen each list.

No legal position scoring above 1,786 has been found anywhere. Six
patterns remain unrefuted, at ceilings 1,794 (×2), 1,792 (×3) and
1,791 (×1).

The per-pattern method that closed the other eight **does not scale to
these six and has been stopped** — cost grows steeply with the ceiling,
and two workers ran ~32 h and ~25 h without finishing. Closing them needs
a different approach; PROOFS.md §8 records the measured cost curve and two
untried directions.

## Method

Every step relies on one principle (PROOFS.md §1): relaxing a constraint
can only *raise* the optimum, so a relaxation scoring ≤ 1,786 eliminates
its case outright. Relaxations are used only to eliminate, never to
confirm — a satisfiable relaxation proves nothing, which is why the last
six cases need the exact model.

- **Stage A** (`bounds.py`) — closed-form geometry caps over all 1,575
  (row, start, length) triples. Arithmetic only, no solver.
- **Stage B** (`tighten.py`) — CP-SAT with real cross-word structure: hook
  validity, run structure, global tile inventory, pairwise adjacency.
- **Stage C** (`cstage.py`) — the full 15×15 tableau: dictionary automata,
  connectivity, inventory and exact scoring, asking directly whether any
  legal position reaches 1,787.
- **Reachability** (`reachability.py`, `racks.py`) — backwards "unplay"
  search for a legal build-up, then an explicit rack-and-bag schedule for
  two alternating players, re-checked by independent verifier logic.

On solver timeouts, elimination uses `BestObjectiveBound()` — still a
valid upper bound for a maximisation. A pattern with no bound at all is
kept, never dropped.

## Reading order

1. **[PROOFS.md](PROOFS.md)** — the theorems and their proofs, with what
   is *not* proved stated explicitly in §8. Start here.
2. **[REPORT.md](REPORT.md)** — the engineering narrative: model design,
   why each relaxation is sound, and reproduction commands in §10.

## Layout

```
scrabble_max/     rules engine, bounds, CP-SAT stages, reachability
tests/            re-checks the load-bearing claims (53 tests)
data/             NWL2023 lexicon (196,601 words)
results/          machine-readable verdicts cited by the proofs
```

## Reproducing

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
export PYTHONHASHSEED=0
.venv/bin/python -m pytest tests/ -q            # fast tests
.venv/bin/python -m pytest tests/ -q -m slow    # solver validation
```

Full pipeline commands are in REPORT.md §10.

Dependencies are pinned because the argument's *soundness* holds under any
solver version — every elimination rests on a proven bound — but the
recorded *numbers* only reproduce under the pinned one. `PYTHONHASHSEED`
is set because `lexicon.load()` returns a frozenset whose iteration order
once reached the emitted model; both places that happened are fixed, and
the variable keeps any residual order-dependence visible. Each pipeline
entry point writes `results/PROVENANCE.json` (commit, OR-Tools version,
interpreter, platform, seed, lexicon SHA-256).

The tests re-derive the record's 1,786 from the board alone, check the
495 → 165 → 14 pattern reduction, and assert the tier-1 filter retains the
record's own placed set — a filter that dropped it would be provably
wrong. They also pin the YARE/YEAR and EARS/ERAS cases behind the
`cross_options` bug, and assert the option list is identical across hash
seeds.

## A note on `results/`

`results/` holds the machine-readable verdicts the proofs cite. The raw
CP-SAT search logs behind them run to about 9 GB of solver internals and
are deliberately **not** committed; their content is distilled into
`results/config_checks_summary.txt` (1,218 per-configuration verdicts) and
the `results/*.json` files. Regenerate the logs with the commands in
REPORT.md §10.

## Provenance

No source for Lucassen's own BSAT solver was locatable, so nothing here
depends on it. The 1,786 construction was transcribed from the blog's
board image and re-verified independently by this repo's rules engine
(PROOFS.md §6).
