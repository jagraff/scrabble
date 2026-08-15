# Optimisation attempts, measured

Kept so nothing here is retried on a hunch. Every figure is measured on
pattern `(0,2,3,7,11,13,14)` unless stated, PYTHONHASHSEED=0.

## Taken

| change | effect |
|---|---|
| `num_search_workers=1` | median solve 14.6s vs 24.2s at 8 workers, and a tighter spread (13.7–17.4 vs 18.2–36.9). One thread is faster in wall-clock, not merely cheaper. Complete enumeration 274s vs 415s at 8 workers. |
| pattern-level parallelism | enumeration within a pattern is sequential (each solve depends on the previous blocking clause), so the only axis is running patterns concurrently: ~8× on 8 cores. |
| in-model blank penalty | 4 of 14 patterns die at tier 2 outright; the rest keep lower ceilings. Per-solve cost rises ~17%. It pays where the configuration count falls a lot — the expensive patterns (824 → 43). The 824 → 43 figure is **correct for the in-model penalty**; see "Two different blank savings" below for what was genuinely wrong. |
| lean blocking clauses | under `fix_placed` the 15 `placed` literals and the unplaced `has_cross` literals are fixed constants that can never satisfy the clause: ~30 dead literals per clause, ~24,000 over an 800-configuration run. |

## Rejected, with the measurement

| idea | why not |
|---|---|
| disable probing (`cp_model_probing_level=0`) | looked 1.68× faster per solve (8.1s vs 13.6s) but **261s vs 274s on a complete enumeration** — the gain on solves that *find* a configuration is cancelled by a slower closing infeasibility proof. The per-solve number was a trap. |
| disable presolve | 9.4s vs 13.6s per solve, same trap as above; not worth the risk to the infeasibility proof. |
| shrink the row-1 DAWG alphabet | all 26 letters can appear in row 1 — 26 as inward letters, 26 as supports. No reduction exists. |
| restrict the blank penalty to letters that can be over-subscribed | for every one of the 14 patterns, **all 26 letters** can be: seven placed columns each contributing a long cross word can exceed any letter's distribution. Only 15 letters are *ever* over-subscribed in the 1,903 archived configurations, but that is an observation, not a bound, and cannot be used soundly. |
| GPU | CP-SAT is clause learning, propagation and LP — branchy and sequentially dependent. GPUs win on dense regular arithmetic. No production GPU CP/SAT solver would approach OR-Tools here. |

## Where the time actually goes

**Superseded — the paragraph below was wrong.** It read:

> Model construction is 0.5s once; `cross_options` and the DAWG about 6.4s
> once. Everything else is CP-SAT's C++ search. There is no Python hot spot
> to optimise — the cost is intrinsic to re-solving a 10,698-constraint
> model with 45 automata once per configuration found.

Two of those sentences are true and the conclusion drawn from them is not.
"Model construction is 0.5s once" is about *Python* building the proto. It
says nothing about CP-SAT's own **presolve**, which runs inside every
`Solve()` call and was never measured. Measured with
`log_search_progress`, presolve was **12.3–19.1s of each 27.4–33.9s
solve** — over half — and the enumeration loop re-pays it on every solve,
of which the worst pattern has ~824.

The lesson worth keeping: "there is no Python hot spot" was the right
answer to the wrong question. Time went to C++, so the search was blamed;
nobody asked *which* C++ phase, and the phase that was over half the cost
was one the loop was repeating unnecessarily.

## Round 3

Every change below only *removes* things the model has already forced, so
each is sound by construction. That is an argument, and arguments of that
shape have been wrong in this project before, so they were also measured
against known-good outputs:

* **All 28 tier-2 bounds re-derived — 14 patterns x both charging modes —
  against `results/blank_penalty_tier2.json`: 0 mismatches.** Tier 2 runs
  under `fix_placed` too, so it exercises both the column pruning and the
  automaton trim on 14 independent instances. A change to the feasible set
  would move a bound.
* A complete enumeration of (0,2,3,7,11,13,14) pruned and unpruned emitted
  the **identical 14 configurations**, both terminating in INFEASIBLE.
* `tests/test_dawg_trim.py` drives the full and trimmed automata over
  thousands of alphabet-respecting rows, including row 1 of the 1,786
  board, and requires the same verdict. It also guards against its own
  vacuity: the first version of that sample contained only *accepted*
  rows, so the agreement test compared nothing but `True`s.

| change | effect |
|---|---|
| prune unplaced columns from the model (`prune_unplaced`) | Under `fix_placed`, a column pinned unplaced can hold no cross word — `x <= placed` forces all its option variables to 0 — yet the model still built them, their z-variables, and the quadratic adjacency clauses to their neighbours. For a 7-column pattern that is **46% of the 6,576 option variables**. Model **9,271 vars / 10,750 constraints → 5,180 / 6,035**; presolve **12–19s → 6.4–6.8s**; wall per solve **~30s → ~21s**. Search time is unchanged, so the win here really is presolve that was being re-derived. Verified not to change the answer: a complete enumeration of (0,2,3,7,11,13,14) pruned and unpruned returns the **identical 14 configurations**, both complete. |
| trim the row-1 automaton (`trim_line_dawg`) | `build_line_dawg` accepts runs of any length, so it carries 59,710 states and 149,039 transitions; the row is exactly 15 cells with a restricted alphabet per cell. Forward/backward reachability over exactly 15 steps keeps only what can lie on an accepted path: **149,039 → 59,602 transitions, 59,710 → 25,465 states**. Wall per solve **20.7s → 12.1s**. Costs ~0.1s, once, cached. |
| partition the solution space (`scrabble_max/partition.py`) | Restores parallelism *within* a pattern — see below. |

### The automaton trim does not work the way I predicted

The trim was written expecting to cut presolve, on the reasoning that
layer-by-layer reachability is presolve's job and the loop was re-paying
it. Measured, interleaved A/B in one process so a drifting background load
hits both:

| | model | presolved | presolve | wall |
|---|---|---|---|---|
| trimmed | 5,180v / 6,035c | 46,778v | 6.34s | **12.1s** |
| full | 5,180v / 6,035c | 46,777v | 6.39s | 20.6s |

Presolve is unchanged, and so is the presolved model — CP-SAT reduces both
automata to the same thing. The entire gain is in **search**.

Caveat worth keeping: because the presolved models are the same size, the
mechanism is not "a smaller problem". A satisfiability solve's time to
first solution is sensitive to the search trajectory, and a 1.7× from two
paired samples on one pattern could be partly luck. The change is sound
(`tests/test_dawg_trim.py`) and costs ~0.1s once, so it is worth keeping
either way — but **1.7× should not be quoted as established** until a
complete enumeration has been run both ways.

### Why within-pattern parallelism was worth revisiting

The "pattern-level parallelism" row above justifies itself with "enumeration
within a pattern is sequential, so the only axis is running patterns
concurrently." The premise is true; the conclusion does not follow, and the
row understates the problem: the configuration counts are
**824, 584, 396, 27, 26, 21, 16, 9**. Whole-pattern parallelism finishes the
seven cheap ones quickly and then waits hours on the 824 with seven cores
idle. Makespan is one pattern, so "~8× on 8 cores" was never available.

The loop is sequential only within a *fixed* solution space. Every
configuration either gives the pivot column no cross word or gives it
exactly one option, so partitioning the pivot's option indices into blocks
partitions the configurations into cells, each with its own independent
blocking loop. Cells are disjoint (checked at runtime, not assumed) and
covering (asserted in `make_cells` — this is the half completeness rests
on). A cell is also strictly more constrained than the whole, so it
propagates better; the gain is not only from the cores.

Cost: one extra closing infeasibility proof per cell, bounded and small
against a loop measured in hours.

Also worth recording: this machine has **4 performance + 4 efficiency
cores**, not 8 equal ones, so any "×8" claim was optimistic regardless.

## Not tried, and why — so the next pass does not assume these were ruled out

These are open, not rejected. Nothing below has been measured.

| idea | assessment |
|---|---|
| `AddDecisionStrategy` on the option variables | The `x[(c,oi)]` are the projection the enumeration is really searching over; branching on them first is the obvious hint. Cheap to test. Plausibly the best remaining single-solve idea. |
| `linearization_level=0` | 160,952 LP iterations on one solve is a lot for what is a feasibility question. But the LP relaxation is probably what proves `total >= 1787` infeasible, and the closing proof is the part that must not regress — the same trap that caught probing-off and presolve-off. Test on a *complete* enumeration or not at all. |
| cache `cross_options` + DAWG to disk for worker processes | `enumerate_configs` rebuilds them per call (~6s); under `partition.py` that is once per cell rather than once per process, so ~24 cells x 6s. Small against cells that run for minutes, and it needs a cache-invalidation story tied to the lexicon. |
| reduce `pairwise_all_rows` depth | Would shrink the model, but weakens the relaxation and so emits more configurations. A trade, not a win; would need both sides measured. |
| projected enumeration in one solve (`enumerate_all_solutions`) | Would presolve once instead of ~800 times and keep learned clauses across solutions — by far the biggest theoretical win. Blocked: CP-SAT enumerates over *all* variables, and supports, blanks and gap variables are free given a configuration, so one configuration would be emitted many times. No projection/model-counting support exists to fix this. |

## Two different blank savings, which had been conflated

`blank_filter_probe.md` measures the **post-hoc** filter: for a *pinned*
configuration the forced blanks are determined exactly, and subtracting the
excess over face value refutes 1,811 of 1,903 configurations (95%) with no
tableau solve. For the 824-configuration pattern that is **6 tableau solves
instead of 824**. This saving is real and large — and it is entirely in the
*refutation* phase.

The **in-model** penalty is a different, weaker thing. It must hold for
every configuration the model might build, so it charges a conservative
`2 x value` per blank and nothing at all when one cheap cell exists. It
shrinks what the enumeration *emits*.

The two were merged into one claim, and the same "95%" was quoted for
both. They are not the same number.

The counts are settled, not estimated. `charge_penalty <= exact_loss`
always — with a cheap non-TW cell the in-model charge is face value and so
is the exact loss; with none it is `3 x value` against an exact loss of
`3 x value` or `27 x value` — so the in-model survivors strictly contain
the post-hoc survivors, and both are subsets of the archived lists.
Counting over those lists is therefore exact arithmetic, no solving
(computed in the other session, via `config_ceiling`):

| pattern | archived | in-model (enumerated) | post-hoc (need tableau) |
|---|---:|---:|---:|
| (0,1,2,3,7,11,14) | 396 | 95 | 11 |
| (0,1,3,4,7,11,14) | 584 | 165 | 56 |
| (0,1,3,7,8,11,14) | 9 | 0 | 0 |
| (0,1,3,7,11,13,14) | 21 | 5 | 5 |
| (0,2,3,4,7,11,14) | 26 | 0 | 0 |
| (0,2,3,7,8,11,14) | 27 | 0 | 0 |
| (0,2,3,7,9,11,14) | **824** | **43** | 6 |
| (0,2,3,7,11,13,14) | 16 | 14 | 14 |
| **total** | **1903** | **322** | **92** |

So `824 -> 43` was right for the enumeration all along, and the error was
only in equating it with the refutation phase's 95%, which gives 6 on that
pattern. The two agree on the five small patterns and diverge on the three
large ones — precisely where the cost is.

Independent cross-check: the in-model column predicts 14 for
(0,2,3,7,11,13,14), and a complete enumeration of that pattern run here
emitted exactly 14. The prediction and the measurement were made
separately.

**I had this backwards for a while.** Told that the 95% belonged to the
post-hoc filter, I concluded the enumeration therefore still emits all 824
and that the cost "swings two orders of magnitude". Both wrong: the
in-model count is determined, and it is 43. The conflation was real; the
consequence I drew from it was not.

Standing caveat: the counts are exact *given* the archived lists are the
true enumerations, and those lists predate the `cross_options` dedup fix.
Re-deriving them is exactly what the tier-3 re-run is for, so 43 is a
well-founded expectation rather than a proved figure.
