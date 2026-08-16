# Handoff: the same question under Collins (CSW)

This file is a **prompt**, meant to be handed whole to an agent (or a
person) starting the Collins version of this work. It is kept in the repo
because most of its value is the list of traps and the soundness rule —
the parts that are expensive to rediscover.

Everything below the line is the prompt.

---

# Task: establish the maximum single-turn Scrabble score under Collins (CSW)

## Goal

Determine the maximum score a single turn can earn under the Collins
Scrabble Words lexicon, and prove it — without assuming in advance that the
best play is a 15-letter word on an edge row.

An existing project did exactly this for NWL2023 and proved the answer is
**1,786**: `git@github.com:jagraff/scrabble.git`. Read `README.md`, then
`PROOFS.md`, then `REPORT.md` before writing code. The pipeline is
lexicon-agnostic — `scrabble_max/lexicon.py` just loads a word list — so
you are re-running an existing argument on a larger input, not starting over.

## Expect a different answer

Collins is a superset of NWL (~280,000 words vs 196,601), so every
NWL-legal board is Collins-legal and **the Collins maximum is ≥ 1,786**.
It is almost certainly higher. Specifically:

- Collins has ~125 two-letter words against NWL's 107. Two-letter words are
  *hooks* — they are what lets a newly placed tile form a legal cross-word
  downward — so `cross_options` lists grow at every column, and with them
  every CP-SAT model in the chain.
- Do not assume the answer is OXYPHENBUTAZONE, or an edge row, or 15
  letters. The NWL proof derived those; you must re-derive them.
- **The whole chain must be recomputed**, not just the last stage. Stage A's
  caps depend on the lexicon (best cross-word remainders), so Theorems 1–4
  are all back open.

## The structural difference from the NWL project

That project had a known 1,786 construction to verify against and to use as
a threshold. You may not have a known-best Collins construction. The
pipeline proves *upper* bounds; proving a maximum needs a matching
construction from below. So plan for two halves:

1. **Upper bound** — run the chain with a threshold, tightening as cases fall.
2. **Lower bound** — a construction achieving it. Start from 1,786 (legal in
   Collins) and search upward.

You are done when they meet. If they don't, report the interval honestly —
"between X and Y" is a real result; a bound quoted as a maximum is not.

## The one rule everything rests on

**Every filter may only ever *enlarge* the feasible set.** A relaxation that
permits more than the rules do is safe: if it can't reach the threshold,
neither can any legal play. A filter that quietly *shrinks* the space can
eliminate a case wrongly and produce a confident wrong answer. `PROOFS.md`
§1 states this as Lemma 1.

Relaxations eliminate; they never confirm. A satisfiable relaxation proves
nothing — surviving cases must go to the exact model.

## Traps that cost the NWL project real time — check for these

1. **`cross_options` deduplication.** It once deduped by the remainder's
   letter *multiset* while callers read its *order*. YARE and YEAR are both
   valid Y-hooks with remainder {A,E,R} but different inward letters; one was
   silently deleted. This shrinks the feasible region — the unsound
   direction. Fixed there; make sure your changes don't reintroduce it.
2. **Never narrow a cell's candidate letters to those with tiles still
   spare.** A blank can supply a letter whose copies are exhausted, so a
   spare-filtered option set is not exhaustive, and refuting every branch of
   a non-exhaustive partition proves nothing.
3. **`UNKNOWN` is not `INFEASIBLE`.** A timed-out solve is undecided. Never
   count it as refuted, and never let a summary fold it into a "decided"
   column. Report undecided cases explicitly and by name.
4. **Killing a run by pid orphans `ProcessPoolExecutor` workers** — they
   don't carry the parent's command line, so `pkill -f <module>` misses them.
   Orphans there ran three hours, corrupted checkpoints, and halved
   throughput. Use the SIGTERM handler in `partition.py`, or kill the process
   group. `SIGSTOP`/`SIGCONT` suspends without losing work.
5. **Checkpoints must record which scoring scale produced them**, or a
   resume can blend two scales undetectably. Already implemented — keep it.

## Optimizations that will matter more at Collins scale

All are in the repo and measured in `results/optimization_log.md`:

- prune unplaced columns from the model under `fix_placed` (46% of option
  variables were dead weight)
- trim the row-1 automaton to what 15 cells can reach (149,039 → 59,602
  transitions; **note this only worked because per-column alphabets are
  restricted — it does nothing for the tableau's automata**)
- partition a pattern's solution space into independently-enumerable cells
  so one pattern can use several cores
- cache the DAWG; build one tableau model per configuration and vary
  branches through CP-SAT assumptions
- `decompose.py` for configurations the tableau can't decide: split on a
  single board cell and recurse

Read the log before optimizing — it records what was tried and *rejected*
with measurements, so you don't re-litigate dead ends.

## Calibration from the NWL run

495 patterns → 165 → 14 → 10 survivors; 1,322 configurations enumerated in
30 min; refutation 28 min (1,063 killed by a closed-form blank ceiling, 258
by CP-SAT, 1 needing cell decomposition). Expect Collins to be materially
larger at every one of those numbers.

**Do not produce a time estimate.** The NWL project's estimates were wrong
twice, in both directions. The rigorous bound on a single solve is ~10^162
assignments — vacuous — and CP-SAT admits no useful per-solve bound. Report
observed rates, not projections. Use `scrabble_max/status.py` to watch runs
live rather than guessing.

## Deliverables

- The bound, and whether it is proved or is a "best found / no better found"
  interval — keep those strictly distinct
- Source, automated tests for the load-bearing claims, reproduction commands
- Provenance for every figure (commit, solver version, lexicon SHA-256)
- A technical report stating what is proved, and the conditions on it:
  which lexicon edition, single play vs game, computer-assisted vs
  machine-checked, and Lemma 1 as the load-bearing assumption

## First step

Obtain the Collins word list and confirm its edition (CSW21, CSW24, …) —
state which one, since the answer is edition-specific. Record its SHA-256.
Then re-run stage A and report how far the geometry space collapses before
touching anything else.
