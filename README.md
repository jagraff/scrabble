# The Maximum Single-Turn Score in Scrabble (NWL2023)

Is **1,786** — Bob Lucassen's OXYPHENBUTAZONE construction
([woogles.io, May 2024](https://blog.woogles.io/posts/2024-05-27-new-theoretical-highest-play-discovered/))
— the highest score a single turn can earn in North American Scrabble
under NWL2023?

## Status: open, but reduced to six cases

**The headline claim is not proved.** What is proved is that the search
space collapses to fourteen explicit configurations, of which **eight are
closed and six remain open**.

That is a stronger statement than "no better play is known." It is a
complete case analysis: every play the argument discards is discarded by a
machine-checked upper bound, never by heuristic or by search failing to
find something.

| | Result | Status |
|---|---|---|
| **Thm 1** | Any play not filling an entire edge row scores ≤ **1,656** | complete |
| **Thm 2** | Any play but OXYPHENBUTAZONE on row 0 scores ≤ **1,778** | complete |
| **Thm 3** | A record-beating play covers all three TWs and places 7 tiles | complete |
| **Thm 4** | Its placed set is one of **14** listed patterns; all score ≤ **1,794** | complete |
| **Thm 5** | The published 1,786 construction is legal and scores exactly 1,786 | complete |
| **Thm 6** | 1,786 is reachable in a legal two-player game (26 moves) | complete |
| **§8** | The 14 patterns are all refuted | **6 of 14 open** |

Since 1,778 < 1,786, Theorem 2 gives the sharpest complete statement:

> **Any play beating the record is OXYPHENBUTAZONE across an edge row —
> the record's own geometry — and scores at most 1,798.**

Of the fourteen surviving patterns, **1,903 configurations have been
enumerated exhaustively and every one refuted**. No legal position scoring
above 1,786 has been found anywhere. Six patterns remain unrefuted, at
ceilings 1,794 (×2), 1,792 (×3) and 1,791 (×1).

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
tests/            re-checks the load-bearing claims (49 tests)
data/             NWL2023 lexicon (196,601 words)
results/          machine-readable verdicts cited by the proofs
```

## Reproducing

```bash
python3.12 -m venv .venv && .venv/bin/pip install ortools pytest pillow
.venv/bin/python -m pytest tests/ -q            # fast tests
.venv/bin/python -m pytest tests/ -q -m slow    # solver validation
```

Full pipeline commands are in REPORT.md §10.

The tests re-derive the record's 1,786 from the board alone, check the
495 → 165 → 14 pattern reduction, and assert the tier-1 filter retains the
record's own placed set — a filter that dropped it would be provably
wrong.

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
