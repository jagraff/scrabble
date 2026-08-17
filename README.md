# The Maximum Single-Turn Score in Scrabble (NWL2023)

Is **1,786** — Bob Lucassen's OXYPHENBUTAZONE construction
([woogles.io, May 2024](https://blog.woogles.io/posts/2024-05-27-new-theoretical-highest-play-discovered/))
— the highest score a single turn can earn in North American Scrabble
under NWL2023?

**Yes** — see the conditions in "What the claim is *not*" below.

## Status: the argument is complete for NWL2023

**No legal NWL2023 play scores above 1,786.** Since 1,786 is achieved by a
legal play and is reachable in a legal two-player game, it is exactly the
maximum single-turn score — subject to the four conditions below, which
are not incidental caveats and should be read before the claim is quoted.

| | Result | Status |
|---|---|---|
| **Thm 1** | Any play not filling an entire edge row scores ≤ **1,656** | complete — stage A only |
| **Thm 2** | Any play but OXYPHENBUTAZONE on row 0 scores ≤ **1,778** | complete |
| **Thm 3** | A record-beating play covers all three TWs and places 7 tiles | complete |
| **Thm 4** | Its placed set is one of **14** listed patterns; all score ≤ **1,794** | complete |
| **Thm 5** | The published 1,786 construction is legal and scores exactly 1,786 | complete — rules engine only |
| **Thm 6** | 1,786 is reachable in a legal two-player game (26 moves) | complete |
| **Tier 2** | The in-model blank penalty eliminates 4 of the 14 patterns | complete |
| **Tier 3** | The remaining 10 patterns' 1,327 configurations are all refuted | **complete** |

Tier 3 enumerated every configuration those ten patterns admit — 1,327 in
total, every partition cell terminating in INFEASIBLE, which is what makes
the lists exhaustive rather than merely long — and decided each one:
**1,063** by an exact closed-form blank ceiling, **263** by a CP-SAT
infeasibility proof, and the last by cell decomposition inside the
pipeline. Details are in
[results/tier3_results.md](results/tier3_results.md).

## Where the proof currently stands

The computational content was re-run from an empty checkpoint namespace on
2026-08-17 and is certified by **`results/MANIFEST.json`**, digest
`99a5fe3feede`, at commit `4174af3`.

| | |
|---|---|
| cells | 50 of 50 complete, 0 corrupt, 0 unstamped |
| configurations | 1,327 enumerated, **1,327 refuted** |
| undecided | 0 |
| above the threshold | 0 |
| environment | one solver build (OR-Tools 9.15.6755), one machine, one commit, clean source |
| lexicon | `data/NWL2023.txt`, sha256 `7ced912101628ad7…`, 196,601 words |

Two commands check it:

```bash
.venv/bin/python -m scrabble_max.manifest --verify  # re-hash everything it names
python3 check_independent.py                        # re-derive it, sharing no code
```

The second is a separate implementation of the rules that imports nothing
from `scrabble_max`. It re-derives the 1,786 score from the board layout
up, replays the 25-move witness to the record pre-board, and reproduces
1,063 of the 1,327 refutations without a solver — 31 checks, 0 failures.

**The run this replaced was not exhaustive.** It reused a checkpoint left
by an aborted launch and skipped five configurations of pattern
(0,1,3,7,11,13,14). All five refute, and the certified run enumerates them;
the count moved from 1,322 to 1,327. That defect, five others found with
it, and what changed in response are recorded in
[results/soundness_remediation.md](results/soundness_remediation.md).

### What is still trusted

Certification covers the *search*, not the modelling. Outside it:

* ~264 CP-SAT infeasibility claims, which would need a DRAT/LRAT layer;
* the stage-A geometry caps, which `check_independent.py` reports as not
  re-derived rather than claiming agreement;
* that the encodings model Scrabble faithfully, and that the lexicon file
  is genuinely NWL2023.

So this is an **exhaustive, machine-checkable computer-assisted search**,
not a machine-checked proof in the sense a proof assistant would mean.

## What the claim is *not*

1. **NWL2023 only — not "Scrabble".** Collins/CSW is a substantially
   larger lexicon and would very plausibly admit a higher maximum. Nothing
   here speaks to it.
2. **One play, not a game.** This is the maximum for a single turn, not a
   game total.
3. **Computer-assisted, not machine-checked.** It rests on CP-SAT being
   correct, on the lexicon file being right, and on the encodings
   modelling Scrabble faithfully. No proof assistant has verified any part
   of it.
4. **Everything hangs on one property: every stage must be a
   *relaxation*** — a filter may only ever *enlarge* the feasible set
   (PROOFS.md §1). This is the load-bearing assumption and the place this
   project has actually had bugs. `tighten.cross_options` once deduplicated
   cross-word options by the remainder's letter *multiset* while callers
   read its *order*, silently deleting options and shrinking the feasible
   region — the unsound direction. Every affected stage was recomputed and
   came back identical, and 28 of 28 tier-2 bounds reproduce exactly, but
   a reviewer should start here.

A fifth, weaker caveat: the refutation of the final configuration is
carried by two independent implementations that agree on 180 solves and on
the open-branch count at every depth. That is strong evidence, not a
formal check.

## Method

Every step relies on one principle (PROOFS.md §1): relaxing a constraint
can only *raise* the optimum, so a relaxation scoring ≤ 1,786 eliminates
its case outright. Relaxations are used only to eliminate, never to
confirm — a satisfiable relaxation proves nothing, which is why the
surviving cases have to be settled by the exact model.

- **Stage A** (`bounds.py`) — closed-form geometry caps over all 1,575
  (row, start, length) triples. Arithmetic only, no solver.
- **Stage B** (`tighten.py`) — CP-SAT with real cross-word structure: hook
  validity, run structure, global tile inventory, pairwise adjacency.
- **Stage C** (`cstage.py`) — the full 15×15 tableau: dictionary automata,
  connectivity, inventory and exact scoring, asking directly whether any
  legal position reaches 1,787.
- **Tier 3** (`partition.py`, `tier3.py`, `decompose.py`) — for each
  surviving pattern, enumerate every configuration it admits (partitioned
  into independently-enumerable cells so a pattern can use more than one
  core), then decide each exactly. A configuration the exact blank ceiling
  cannot kill goes to the tableau; one the tableau cannot decide is split
  cell by cell until it does.
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
3. **[results/tier3_results.md](results/tier3_results.md)** — how the last
   ten patterns were closed, and the one configuration that needed cell
   decomposition.
4. **[COLLINS_HANDOFF.md](COLLINS_HANDOFF.md)** — a ready-to-hand-off brief
   for running the same question against the Collins (CSW) lexicon, where
   the answer is necessarily ≥ 1,786 and almost certainly higher. Carries
   the soundness rule and the traps that cost this project time.

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
