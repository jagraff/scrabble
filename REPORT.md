# The Maximum Single-Turn Score in NWL2023 Scrabble

**Question.** Is 1,786 — Bob Lucassen's OXYPHENBUTAZONE construction
([woogles.io blog, May 2024](https://blog.woogles.io/posts/2024-05-27-new-theoretical-highest-play-discovered/))
— truly the maximum score a single turn can earn in standard North
American Scrabble under the NWL2023 lexicon, without assuming in advance
that the best play is a 15-letter word on an outside row?

**Answer (summary).** We built an independent solver chain that searches
*every* legal move geometry with machine-checked upper bounds:

1. All geometries except a full-width 15-letter word on an edge line are
   **rigorously eliminated**: no such play can reach 1,786 under any board.
2. Among all 3,839 fifteen-letter words × both edge orientations, only
   **17 (word, orientation) candidates** have a relaxed upper bound ≥ 1,786,
   and after CP-SAT tightening only **one case anywhere on the board**
   remains above 1,786: OXYPHENBUTAZONE across the top row with all three
   triple-word squares newly covered, bounded above by **1,794**.
3. That final case splits into **14 explicit placed patterns**, attacked
   with the *complete static-position feasibility problem* (a full 15×15
   tableau CP-SAT model with dictionary automata, connectivity, tile
   inventory and exact scoring). Tier 2's in-model blank penalty kills 4
   of the 14 outright; the remaining 10 admit **1,322 configurations**,
   all enumerated exhaustively and **all refuted** — see §7.3 and §9.
4. Separately, we answered the reachability question constructively: an
   explicit **26-move legal game** (25 build-up moves plus the record
   play) reaches and then plays the 1,786 board from an empty board, with
   two **strictly alternating** players each drawing from the standard
   bag into a rack of at most 7. So the 1,786 play is not merely
   statically legal but realizable in an ordinary two-player game.

We could not locate source code for Lucassen's own BSAT solver (the blog
post links none), so nothing here relies on it; the 1,786 construction
itself was transcribed from the blog's board screenshot and
independently re-verified (§3).

---

## 1. Rules model

`scrabble_max/rules.py`, `scrabble_max/board.py` implement:

- the standard premium layout (8 TW, 17 DW incl. center, 12 TL, 24 DL),
  generated from a quadrant definition and mirrored; unit tests pin down
  canonical squares and counts, and verify the layout is invariant under
  transposition (needed for the symmetry argument below);
- official tile distribution (100 tiles, face values summing to 187) and
  blank handling (blanks are typed but score 0 and count against the two
  in the bag);
- full move application: placement in one line, contiguity through
  existing tiles, gap-filling, connection to the board, first-move center
  rule, cross-word formation, premium behavior (premiums count only under
  newly placed tiles; a word multiplier under a placed tile multiplies
  both the main word and that tile's cross word), the 50-point bingo;
- static-position validity: every maximal run of ≥2 tiles is a lexicon
  word, all tiles connected through the center, tile usage within the bag.

30 unit tests cover scoring (including the canonical MUZJIKS = 128
opening), premium reuse, blanks, cross-words, illegal moves, and
inventory (`tests/test_rules.py`).

Lexicon: NWL2023 (196,601 words) from the public
`scrabblewords/scrabblewords` repository (`data/NWL2023.txt`).

## 2. What a legal move is (completeness of the enumeration)

Every legal move places 1–7 tiles in one line. There is always a
direction in which the maximal run through the placed tiles has length
≥ 2 and contains *all* placed tiles (for a one-tile move, at least one of
its two runs, else no word is formed and the move is illegal). Call that
run the **main word** `w` (necessarily a lexicon word), its cells the
span, and the placed subset `S`. The score is exactly

```
WM(S)·MainSum(w,S) + Σ_{c∈S} CrossScore(c) + 50·[|S|=7]
```

Since the board is transpose-symmetric and the lexicon and bag are
shared, vertical moves map score-preservingly onto horizontal ones; we
enumerate horizontal moves on all 15 rows. The enumeration over
`(row, start, w, S)` therefore covers **every** legal move on **any**
board. Single-tile plays, gap-fills, extensions of existing words, and
plays incorporating any number of existing letters are all instances.

## 3. The known 1,786 construction, independently verified

We transcribed the final board from the woogles.io screenshot
(`scrabble_max/known.py`). The verifier confirms: the pre-move position
is statically valid (every one of its 21 distinct words is in NWL2023,
connected, center covered, 82 tiles + 2 blanks within inventory); the
move (rack **BENOPXZ**, placing O,X,P,N,B,Z,E on A1,B1,D1,G1,H1,L1,O1)
is legal; and the score decomposes exactly as:

| word | score |
|---|---|
| OXYPHENBUTAZONE (27× main, P and Z on DLS) | 1,458 |
| OPACIFICATIONS (×3) | 69 |
| XED | 11 |
| PREQUALIFYING (P doubled) | 34 |
| NARROWING | 13 |
| BLADDERLIKE (×3) | 57 |
| ZOOGAMETE (Z doubled) | 31 |
| ESTABLISHMENTS (×3) | 63 |
| bingo | 50 |
| **total** | **1,786** |

This is a permanent regression test (`test_known_1786_construction`).
The final board uses 97 of the 100 tiles and exhausts the full supply of
every letter it uses except I (and unused J, V) — inventory really is a
binding resource in this regime.

## 4. Stage A — geometry caps and the relaxed enumeration

`scrabble_max/bounds.py` computes, for each `(row, start, length)`, a
**word-independent cap**: max word multiplier attainable in the span ×
(best inventory-adjusted letter sum of any word of that length + maximal
letter-premium boosts) + the top-7 per-cell cross-word bounds + 50. Each
ingredient is a proven overestimate (see module docstring; every
relaxation only enlarges the feasible set). Cross-word bounds come from a
table `best_rest[letter][row]`: the best value-sum over all lexicon words
containing that letter at a position that geometrically fits through that
row, inventory-adjusted per word (words that would need more than the
bag + 2 blanks are excluded — provably unplayable on any board).

**Result: only full-row 15-letter spans on row 1 and row 15 (and their
column transposes) have caps ≥ 1,786.** Every shorter word, every inner
line, every partial span is eliminated at once (`results/candidates.json`,
`live_geometries_by_length`). The margins are wide: the best cap of any
eliminated geometry is **1,656** (a full 15-letter word through the
center row's two TWs and the center DW), and the best 14-letter edge
span caps at 1,031. A ×27 word multiplier is achievable only by newly
covering three TWs in one line, which forces exactly the surviving
geometry; without it, even best-case letters plus seven tripled
cross-words fall short.

For the surviving geometry the per-word relaxed maximum (exact
maximization over placed subsets under the relaxations) leaves **17
candidates** ≥ 1,786 across 9 distinct words:

```
2000 OXYPHENBUTAZONE(top)   1935 OXYPHENBUTAZONE(bottom)
1911/1897 PSYCHOANALYZING   1860/1845 DEMYTHOLOGIZING
1839/1836 DEMYTHOLOGIZERS   1836/1824 NEPHRECTOMIZING
1834 VENTRILOQUIZING        1830/1815 REMYTHOLOGIZING
1825/1807 HYPERIMMUNIZING   1790 DICHLOROBENZENE
1789 OVEREMPHASIZING
```

Soundness tests: the bound dominates the actual score of every scored
test play including the known 1,786 (`tests/test_bounds.py`).

## 5. Stage B — CP-SAT tightening with real cross-word structure

`scrabble_max/tighten.py` solves, per candidate, a joint optimization
over the placed set and one **concrete** cross word per placed cell:

- edge geometry: a top-row cross word must *start* with the hook letter
  (bottom row: end with it);
- **hook validity**: the cross word minus the hook is a maximal run of
  the pre-move board, so for length ≥ 3 it must itself be a word (this
  is why the real construction uses B+LADDERLIKE, N+ARROWING, …); this
  alone cuts the option lists from thousands to hundreds (X has only 10
  valid front-hooks in NWL2023);
- **pre-existing-run structure**: the non-placed edge cells form maximal
  runs of the pre-move board — every such run of length ≥ 2 must be a
  word, and every run needs at least one supporting tile in the next row
  inward (counted against the 100-tile board);
- pairwise adjacency: horizontally adjacent cross-word letters at every
  shared depth must occur adjacently in some lexicon word;
- **global tile inventory** across the main word and all cross words,
  with ≤ 2 blanks; a blank forced onto a scored tile costs at least its
  face value (a provable lower bound on the loss, keeping the optimum an
  upper bound);
- total board ≤ 100 tiles;
- word multiplier handled exactly by solving all 8 subsets of the three
  TW squares.

**A soundness bug in the option lists (fixed 2026-08-15).** For the
relaxation to bound anything, every legal play must satisfy its
constraints — the option list for a hook letter has to contain *every*
valid cross word. `cross_options` originally deduplicated options by the
letter *multiset* of the cross word's remainder, keeping one
representative per anagram class. But callers read the representative's
**ordered** letters: `o[4]` supplies the row-1 inward letter, and
`rest_letter_at_depth` supplies the letters the pairwise-adjacency
constraints compare. Anagrams are not interchangeable there. NWL2023
contains both YARE and YEAR — both valid Y-hooks, both with remainder
multiset {A, E, R}, but with inward letters A and E respectively; only
one survived. EARS/ERAS is the same story.

The direction of the error is the dangerous one. Deleting options
*shrinks* the feasible region, so the model's optimum can fall *below*
the true maximum — and those optima are used as upper bounds, so any
case eliminated on "bound ≤ 1786" may have been eliminated wrongly. The
bug was also nondeterministic: the lexicon is a frozenset, so which of
YARE/YEAR survived depended on `PYTHONHASHSEED`.

The fix keys options on the full ordered remainder, i.e. one option per
valid cross word. Hook validity already prunes anagrams heavily, so this
costs only ~3% more options (11,670 → 11,965 across both edge rows for
the letters of OXYPHENBUTAZONE). Regression tests in
`tests/test_tighten.py` pin YARE/YEAR and EARS/ERAS, assert that every
valid cross word appears as its own option, and check that the option
list is byte-identical across hash seeds.

The real 1,786 play satisfies every one of these constraints, giving the
soundness regression `test_tight_bound_dominates_known_1786` (bound must
be ≥ 1,786 — it is).

**Results** (`results/tight_bounds.json`), relaxed → stage-B bound, for
(top row / bottom row):

```
OXYPHENBUTAZONE  2000→1798 / 1935→1778   PSYCHOANALYZING  1911→1430 / 1897→1424
DEMYTHOLOGIZING  1845→1650 / 1860→1703   DEMYTHOLOGIZERS  1836→1629 / 1839→1716
NEPHRECTOMIZING  1824→1642 / 1836→1639   REMYTHOLOGIZING  1815→1621 / 1830→1666
HYPERIMMUNIZING  1825→1645 / 1807→1624   VENTRILOQUIZING  1834→1629 (top)
DICHLOROBENZENE  1790→1585 (top)         OVEREMPHASIZING  1789→1560 (top)
```

Every candidate except OXYPHENBUTAZONE-top collapses below 1,786 (the
runner-up is OXYPHENBUTAZONE played on the *bottom* row at 1,778, where
cross words must *end* at the edge). Crucially, the per-TW-mask breakdown
for OXYPHENBUTAZONE-top is `{no TWs: 264, …, two TWs: ≤784, all three
TWs: 1798}`: **the only configuration anywhere above 1,786 is the known
one — OXYPHENBUTAZONE across the top row placing tiles on all three
triple-word squares.**

### Stage B⁺ — exact model of the second row

For that one survivor we additionally model row 2 exactly: a variable per
column that is either the fixed second letter of the chosen cross word, a
support tile whose letter can legally follow the edge letter (feeding
inventory and the tile count), or empty — with the row's maximal runs
required to be lexicon words via an automaton over a minimized DAWG of
the lexicon (59,710 states; semantics unit-tested on a toy lexicon).
This lowers the bound **1798 → 1794** (solver-proved optimal).

## 6. Interlude — every relaxation is one-directional

Every pruning rule used above is of the form "delete constraints /
overestimate terms", each documented in the module docstrings and
exercised by tests that check domination over real scored plays. Hence
the chain proves, unconditionally:

> **No legal Scrabble move on any NWL2023 board scores more than 1,794,
> and the only move type that can possibly exceed 1,786 is
> OXYPHENBUTAZONE played across a triple-word edge line covering all
> three TWs.**

## 7. Stage C — exact static feasibility for the final case

`scrabble_max/cstage.py` models the *entire* 15×15 pre-move position:
letter variables for all 210 inner cells; DAWG automata enforcing that
every row and every column — pre-move **and** post-move, including the
empty-pre-move hook cells via an auxiliary symbol — consists of valid
maximal runs; center-connectivity by a flow model; global inventory with
blanks (scored-blank losses lower-bounded as in stage B); and the exact
score expression (contiguous cross-run depth per column, premiums,
bingo). Maximizing the score *would* answer question A exactly for this
geometry — the model is faithful, not a relaxation. Whether it can be
solved is a separate matter, and in practice it cannot be solved directly;
§7.3 records where that leaves things.

Model validation: hard-fixing the grid to the transcribed 1,786 board
makes the model feasible with objective **exactly 1,786** in 10 s
(`tests/test_cstage.py`), validating automata, flow, inventory and
scoring in one shot.

Solving the tableau with everything free proved too slow (CP-SAT presolve
of 45 automaton constraints over a free grid), so the final case is
decided by decomposition. Two decompositions were tried.

### 7.1 First attempt — per-configuration refutation (abandoned)

`scrabble_max/finalize.py` enumerates *configurations*: a placed set
together with a concrete cross word in each placed column. A blocking-clause
loop emits every configuration whose stage-B⁺ relaxed score reaches 1,787,
and each is then refuted by the tableau with those columns pinned — which
makes presolve collapse, so a check takes seconds.

This works per item but does not terminate. Cross words are freely
substitutable (ZOOGAMETE/ZOOGAMETES, XYLEM/XYLEMS, …), so one board
structure spawns hundreds of configurations that all fail for the same
reason. After 21 hours the loop had emitted **1,300 configurations — all
refuted, none surviving — spanning just 14 distinct placed sets**, at a
steady ~57/hour with no sign of exhaustion. The enumeration was over the
wrong equivalence class, and was stopped.

Two findings from it are kept. First, it exercised the pinned tableau
1,300 times without ever producing a legal position above 1,786. Second,
it caught a modelling bug: one configuration solved to OPTIMAL 1,787 whose
true score was 1,775, because blanks forced onto scored tiles were
under-charged; `exact_fixed_blank_loss` fixed it and the configuration is
INFEASIBLE under the corrected model.

### 7.2 Second attempt — per-pattern refutation

`scrabble_max/patterns.py` quantifies over the placed set alone, in three
tiers of increasing cost.

**Tier 1 (arithmetic).** A rack holds 7 tiles and stage B caps |S| ≤ 6 at
1,730, so |S| = 7; stage B caps every non-full TW mask at 784, so
{0, 7, 14} ⊆ S. That leaves exactly **C(12,4) = 495** placed patterns.
Scoring each with the stage-A relaxation (ceiling 2,000) leaves **165**;
the other 330 cannot reach 1,787 even optimistically.

**Tier 2 (row-1-exact).** `tighten_candidate` gains `fix_placed=`, pinning
the placed set inside the stage-B⁺ model (ceiling 1,794). This is both
much tighter than tier 1 and far cheaper than a tableau solve: it decided
all 165 patterns in **10 minutes**, leaving **14 survivors**. It
disposes of cases the tableau cannot — `(0,1,3,7,11,12,14)` bounds at
1,785 in 25 s where the tableau returned UNKNOWN twice at 300 s and 600 s.

The 14 survivors and their proven upper bounds:

| row-1-exact bound | placed columns |
|---:|---|
| 1794 | `(0, 1, 3, 7, 10, 11, 14)` |
| 1794 | `(0, 1, 3, 7, 9, 11, 14)` |
| 1792 | `(0, 2, 3, 6, 7, 11, 14)` |
| 1792 | `(0, 1, 3, 6, 7, 11, 14)` |
| 1792 | `(0, 1, 3, 5, 7, 11, 14)` |
| 1791 | `(0, 2, 3, 7, 10, 11, 14)` |
| 1791 | `(0, 2, 3, 7, 9, 11, 14)` |
| 1791 | `(0, 1, 3, 4, 7, 11, 14)` |
| 1791 | `(0, 1, 2, 3, 7, 11, 14)` |
| 1790 | `(0, 2, 3, 7, 8, 11, 14)` |
| 1790 | `(0, 1, 3, 7, 8, 11, 14)` |
| 1788 | `(0, 2, 3, 4, 7, 11, 14)` |
| 1788 | `(0, 1, 3, 7, 11, 13, 14)` |
| 1787 | `(0, 2, 3, 7, 11, 13, 14)` |

Two checks on the list, neither an independent proof of the count. First,
every one of the 1,300 configurations found by the abandoned
per-configuration enumeration (§7.1) lies in these 14 placed sets. That is
evidence the 14 are not *too few* in the region that run explored, but it
is **not** an independent verification that there are only 14: the run
never terminated, so it sampled rather than exhausted. Had it finished it
would have been a second derivation; it did not. Second, the list contains
`(0, 1, 3, 6, 7, 11, 14)` — the placed set of the record play itself,
which must survive any sound filter (`tests/test_patterns.py`).

Exhaustiveness of the 14 rests on tiers 1 and 2 alone: 495 patterns
enumerated combinatorially, each eliminated only on a proven upper bound.

**Tier 3 (tableau).** Each survivor goes to the full tableau with the
placed set pinned and cross words free, asking for a legal position
scoring ≥ 1,787. `known_upper` is deliberately not passed, so this step
does not inherit tier 2's ceiling as an assumption.

Attacking a pattern directly with the tableau stalls: the `≥ 1,787` query
returned UNKNOWN at 600 s for `(0,1,3,7,10,11,14)` with and without the
1,794 ceiling, and a case-split on the exact total also returned UNKNOWN.

### 7.3 Tier 3 by per-pattern configuration enumeration

`prove_pattern_by_configs` reinstates the §7.1 idea *inside* a fixed
placed set, which is what makes it terminate. For one pattern: enumerate
by blocking-clause loop every configuration (a concrete cross word per
placed column) whose stage-B⁺ relaxed score exceeds 1,786, until the model
goes infeasible — at which point the list is provably exhaustive — then
refute each with the pinned tableau. Any legal position beating the record
realises some configuration and its relaxed score dominates its true
score, so it must appear in the list; refuting every entry refutes the
pattern.

**Parallelism.** The blocking loop is sequential within a fixed solution
space, but the space itself can be split: every configuration either gives
a chosen pivot column no cross word or gives it exactly one option, so
partitioning the option indices into blocks partitions the configurations
into cells with independent loops (`partition.py`). Cells are covering
(asserted) and disjoint (checked at runtime). This matters because the
per-pattern counts are severely skewed — 623 against a median of ~100 — so
whole-pattern parallelism alone leaves the finish time set by one pattern.

**Result: all ten surviving patterns closed. 1,322 configurations, every
partition cell terminating INFEASIBLE, every configuration refuted**
(`results/tier3_configs.json`, `results/tier3_checks/`,
`results/tier3_results.md`). Enumeration 29.7 min; refutation 28 min.

| how each configuration was decided | count |
|---|---:|
| exact blank ceiling, closed form, no solve | 1,063 |
| CP-SAT infeasibility proof on the tableau | 258 |
| cell decomposition (`decompose.py`) | 1 |

**The 258 tableau refutations are not about score.** Re-run with the score
constraint removed entirely — asking only whether *any* legal board
realises the configuration — a sample of twelve returned INFEASIBLE 12 of
12 in ~2.8 s each. Those configurations describe boards that cannot exist,
and propagation refutes them without 1,786 entering the proof. This is why
the phase took 28 minutes rather than days, and it was not predicted.

**The one that resisted.** `(0,1,3,7,10,11,14)` with cross words
OPACIFICATIONS / XEROSES / PREADJUSTING / BRAINWASHING / AMELIORATIVE /
ZOOGAMETE / EQUALITY, exact ceiling 1,787, still UNKNOWN after 1,300 s and
UNKNOWN even without the score constraint — it has no shallow structural
contradiction, so the solver must search rather than propagate. Its static
features are unremarkable, so the diagnosis had to be behavioural.

It is refuted by splitting on individual board cells (`decompose.py`).
Every legal board puts something in a given cell, so refuting every
possible value refutes the configuration — provided the option set is
exhaustive. For a row-1 cell under a pre-existing column that is `{empty} ∪
{letters that can follow the row-0 letter}`; the set may **not** be
narrowed to letters with tiles still spare, because a blank can supply a
letter whose copies are exhausted. Recursion to depth 6 closes it in **180
solves**, reproduced by two implementations differing in traversal order,
parallelism, and whether the model is rebuilt per branch — agreeing on the
solve count and the open-branch count at every depth (506 s and 140 s).

Checked against a case with a known answer: the same refuter run on the
record's own configuration at threshold 1,785, where a 1,786 board exists,
refutes 9 of 10 branches and leaves standing exactly the branch containing
the record.

## 8. Question A vs. question B (reachability)

Static feasibility (a legal position exists on which the move is legal)
does not imply a legal game reaches that position. We answered
reachability for the 1,786 construction **constructively**, in two parts.

**Board legality.** `scrabble_max/reachability.py` runs a backwards
"unplay" search — guess the last move, check that removing it leaves a
valid connected position and that the move was legal on that smaller
board, recurse — and found a complete **25-move** build-up from the empty
board to the exact pre-board (first move UNLED through the center; both
blanks entering as the h of HA and the s of RAS). The sequence is replayed
forward through the rules engine and reproduces the pre-board
tile-for-tile (`results/reachability.log`). Move 26 is OXYPHENBUTAZONE for
1,786.

**Rack and bag feasibility.** Board legality alone still allows draws no
real bag could supply, so `scrabble_max/racks.py` deals the 26 moves to
two **strictly alternating** players and constructs the draws. Since any
permutation of the bag is a legal shuffle, the draws are ours to choose
and this is an existence question: each player draws 7 to start and
refills to 7 after each of their moves, taking the tiles their soonest
upcoming move needs. The schedule closes exactly — **97 tiles played, 3
left on racks, 0 in bag** — with no letter over its distribution, both
blanks used, and no rack ever above 7; the bag empties after move 25.

`verify_witness` replays the recorded draws against a fresh bag with
independent logic and asserts every rule at each step, so
`results/rack_schedule.json` is a self-contained certificate rather than a
claim about the generator (`tests/test_racks.py`).

Together these upgrade the result from "buildable by legal board moves" to
**reachable in an ordinary two-player game**. Neither follows
automatically from the other, and the second is the one a player cares
about.

## 9. What is proven, and how strongly

| claim | status |
|---|---|
| 1,786 is achievable as a static position | **proven constructively**, machine-verified (§3) |
| 1,786 is reachable in a legal two-player game | **proven constructively** (§8, board legality + rack/bag witness) |
| no play outside a full edge row reaches 1,786 | **proven** (stage A only — §4, unaffected by the §5 bug) |
| no play ≥ 1,787 exists in any geometry other than OXYPHENBUTAZONE/edge-row/3×TW | **proven** — stage B recomputed post-fix, identical |
| every other play scores ≤ 1,778 | **proven** — recomputed post-fix, identical |
| global upper bound 1,794 | **proven** — stage B⁺ recomputed post-fix, identical |
| the 14-pattern reduction | **proven** — tier 2 recomputed post-fix: 165 → 14, unchanged |
| **1,786 is the maximum single-turn score in NWL2023** | **proven**, subject to the four conditions in §9 — all 14 patterns refuted (§7.3) |

After the `cross_options` fix of §5, stage B and B⁺ were rerun over all 17
candidates (commit `d9420e9`, `PYTHONHASHSEED=0`, OR-Tools 9.15.6755) and
every bound returned identical, in all 136 per-mask cells. The `|S| ≤ 6`
bounds behind Theorem 3 are likewise unchanged at 1,730 and 1,706.

That is not evidence the bug was harmless. In the `|S| ≤ 6` model eight
per-mask cells moved **up** and none moved down (row 0 mask 3: 714 → 717;
mask 6: 716 → 718; row 14 mask 6: 705 → 706, and others). The mask
Theorem 3 depends on was not among them. The old dedup kept the
highest-scoring representative of each anagram class, so an unconstrained
optimum usually landed on a surviving option; the deleted ones bind only
once other constraints force a structurally compatible but lower-scoring
cross word. Tier 2, which pins the placed set, is a tighter constraint
still and is where numbers are likeliest to move — which is why tier 2 was
rerun rather than assumed. It was, and the 165 → 14 reduction came back
unchanged; all 28 tier-2 bounds (14 patterns × both charging modes)
reproduce exactly.

### The four conditions on the headline claim

The claim is **1,786 is the maximum single-turn score in NWL2023**. It is
not "the maximum Scrabble score", and the difference is not pedantic:

1. **NWL2023 only.** Collins/CSW is a substantially larger lexicon and
   would plausibly admit a higher maximum. Nothing in this work bears on
   it.
2. **A single play, not a game total.**
3. **Computer-assisted, not machine-checked.** No proof assistant has
   verified any part of this; it rests on the trust base below.
4. **Lemma 1 is load-bearing everywhere.** Every stage must only ever
   *enlarge* the feasible set — a filter that shrinks it can eliminate a
   case wrongly. This is where the project has actually had bugs (§5), and
   it is where a reviewer should start rather than with the arithmetic.

Caveats and trust base: correctness rests on (a) the rules engine
(unit-tested, including the independently hand-computed 1,786 breakdown),
(b) the documented one-directional relaxations, (c) OR-Tools CP-SAT
returning correct OPTIMAL/INFEASIBLE verdicts, and (d) the NWL2023 word
list from `scrabblewords/scrabblewords` matching the official lexicon.
Blank-designation subtleties are handled conservatively throughout
(bounds assume real tiles; found solutions are re-verified exactly).

## 10. Reproduction

The whole chain, from an empty checkpoint directory, is one command:

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
./rerun.sh                                           # ~2.5 h on 4 cores
```

It runs each stage in the order that matters — every stage's output selects
the next stage's work — and follows each with the check that can fail it,
ending with the directional comparison against the previous run and the run
manifest. It is deliberately not resumable: a re-run whose point is that no
stale artifact was reused must not itself reuse one.

The stages individually:

```
export PYTHONHASHSEED=0                              # not decoration; see below
.venv/bin/python -m pytest tests/ -q -m "not slow"   # fast tests (~50 s)
.venv/bin/python -m pytest tests/ -q -m slow         # solver validation (~8 min)
.venv/bin/python -m scrabble_max.bounds --threshold 1786   # stage A  (~1 min)
.venv/bin/python -m scrabble_max.tighten --time-limit 240  # stages B/B⁺ (~1 h)
.venv/bin/python -m scrabble_max.tighten --six-tiles   # Theorem 3's |S| <= 6 bound
.venv/bin/python -m scrabble_max.patterns --stop-after-row1  # tiers 1-2 (~8 min)
.venv/bin/python -m scrabble_max.blank_tier2         # blank-penalty sweep (~6 min)
.venv/bin/python -m scrabble_max.tier3 --workers 4 --blocks 4   # tier 3 (~1 h)
.venv/bin/python -m scrabble_max.reachability        # 25-move build-up (~1 min)
.venv/bin/python -m scrabble_max.racks               # rack/bag + board witness
.venv/bin/python -m scrabble_max.check_rerun         # directional checks
.venv/bin/python -m scrabble_max.manifest            # certify the run
.venv/bin/python -m scrabble_max.manifest --verify   # re-hash what it names
```

Note that `pytest tests/ -q` alone runs the solver tests too and takes ~9
minutes; `-m "not slow"` is the fast subset.

Stage C's free tableau solve (`cstage --time-limit 21600`) is **not** in
this list. It does not terminate and is not part of the argument — §7 above
records why. What stage C contributes is the model, used per-configuration
with columns pinned, plus the validation test that fixes the grid to the
known board and recovers exactly 1,786.

### What certifies a run

`results/MANIFEST.json` binds the environment, the parameters, and a
SHA-256 of every artifact and every cell checkpoint. Each checkpoint also
carries its own identity header naming the computation it certifies —
lexicon, threshold, pattern, pivot, block membership, block count, and a
digest of the modules that build the model — and a checkpoint that does not
match the run being executed is refused rather than reused. See
`results/soundness_remediation.md` for what that fixes and where the design
deliberately differs from the audit that prompted it.

`patterns` takes `--only` to run a subset of placed sets, so open patterns
can be worked in parallel, and `--configs-out` to record the enumerated
configurations.

### Reproducibility

Dependencies are pinned in `requirements.txt`. This matters more than
usual here: every elimination rests on a *proven* upper bound, so the
argument stays sound under any solver version, but the recorded numbers
are only reproducible under the pinned one — CP-SAT's presolve and search
heuristics move between releases, and a timeout-derived
`BestObjectiveBound` moves with them.

`PYTHONHASHSEED=0` is not decoration. `lexicon.load()` returns a
frozenset, and two places once let its iteration order reach the emitted
model: `cross_options` (fixed — see §5) and `build_line_dawg`, whose trie
insertion order decided how `intern` allocated automaton state ids. The
minimal DAWG is canonical up to renaming, so the automaton was always
*correct*, but each hash seed produced a different numbering and hence a
different CP-SAT model. Both now sort their input, and the automaton
hashes identically across seeds; the environment variable is belt and
braces, so that any residual order-dependence shows up as a diff rather
than hiding.

Every pipeline entry point writes `results/PROVENANCE.json` — git commit,
OR-Tools version, interpreter, platform, hash seed, and the lexicon's
SHA-256 and word count — so a result file can be traced to the run that
produced it. It is a sidecar rather than a field inside each result file,
to avoid changing structures that `tests/` already parse.

Logs and machine-readable results live in `results/`.
