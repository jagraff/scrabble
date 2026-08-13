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
3. For that final case we solve the *complete static-position feasibility
   problem* (a full 15×15 tableau CP-SAT model with dictionary automata,
   connectivity, tile inventory and exact scoring) to determine the exact
   maximum. **[RESULT — see §7.]**
4. Separately, we answered the reachability question constructively: an
   explicit **25-move legal game** reaches the 1,786 pre-board from an
   empty board (found by automated "unplay" search, replay-verified move
   by move), so the 1,786 play is not merely statically legal but
   realizable in a real (cooperative) game.

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
bingo). Maximizing the score answers question A exactly for this
geometry.

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

Independent confirmation: these 14 are **exactly** the 14 placed sets the
abandoned per-configuration enumeration found in 21 hours across 1,300
configurations. Two unrelated routes agree on the set, and it contains
`(0, 1, 3, 6, 7, 11, 14)` — the placed set of the record play itself,
which must survive any sound filter (`tests/test_patterns.py`).

**Tier 3 (tableau).** Each survivor goes to the full tableau with the
placed set pinned and cross words free, asking for a legal position
scoring ≥ 1,787. `known_upper` is deliberately not passed, so this step
does not inherit tier 2's ceiling as an assumption.

Tier 3 is the open step. The `≥ 1,787` query is hard for CP-SAT on these
patterns: `(0,1,3,7,10,11,14)` returned UNKNOWN at 600 s with and without
the 1,794 ceiling. A sound case-split on the exact total
(`total == v` for each v in [1,787, upper], exhaustive because `upper` is
proven) was also tried and also returned UNKNOWN at `total == 1794` after
419 s. Status is recorded in `results/pattern_proof.json`.

## 8. Question A vs. question B (reachability)

Static feasibility (a legal position exists on which the move is legal)
does not imply a legal game reaches that position. We answered
reachability for the 1,786 construction **constructively**:
`scrabble_max/reachability.py` runs a backwards "unplay" search — guess
the last move, check that removing it leaves a valid connected position
and that the move was legal on that smaller board, recurse — and found a
complete **25-move legal game** from the empty board to the exact
pre-board (first move UNLED through the center; both blanks entering as
the h of HA and the s of RAS). The sequence is replayed forward through
the rules engine and reproduces the pre-board tile-for-tile
(`results/reachability.log`). Move 26 is OXYPHENBUTAZONE for 1,786.

## 9. What is proven, and how strongly

| claim | status |
|---|---|
| 1,786 is achievable (static position + full legal game) | **proven constructively**, machine-verified |
| no play ≥ 1,787 exists in any geometry other than OXYPHENBUTAZONE/top-row/3×TW | **proven** (stages A+B, sound relaxation chain) |
| global upper bound 1,794 | **proven** (stage B⁺, solver-optimal) |
| exact maximum for the last geometry | stage C tableau solve — see §7 / `results/tableau.json` |

Caveats and trust base: correctness rests on (a) the rules engine
(unit-tested, including the independently hand-computed 1,786 breakdown),
(b) the documented one-directional relaxations, (c) OR-Tools CP-SAT
returning correct OPTIMAL/INFEASIBLE verdicts, and (d) the NWL2023 word
list from `scrabblewords/scrabblewords` matching the official lexicon.
Blank-designation subtleties are handled conservatively throughout
(bounds assume real tiles; found solutions are re-verified exactly).

## 10. Reproduction

```
python3.12 -m venv .venv && .venv/bin/pip install ortools pytest pillow
.venv/bin/python -m pytest tests/ -q                 # fast tests
.venv/bin/python -m pytest tests/ -q -m slow         # solver validation tests
.venv/bin/python -m scrabble_max.bounds --threshold 1786   # stage A  (~1 min)
.venv/bin/python -m scrabble_max.tighten --time-limit 240  # stages B/B⁺ (~1 h)
.venv/bin/python -m scrabble_max.cstage --time-limit 21600 --min-score 1786  # stage C
.venv/bin/python -m scrabble_max.reachability        # 25-move game (~1 min)
```

Logs and machine-readable results live in `results/`.
