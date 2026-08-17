# Proofs

What is established so far about the maximum single-turn score in North
American Scrabble under NWL2023, stated as theorems with their proofs.

Results marked **(complete)** have no open cases. Results marked
**(partial)** are stated with exactly what remains. Every theorem here is
independent of the unfinished work in §7 unless it says otherwise.

Throughout, "the record" means Bob Lucassen's OXYPHENBUTAZONE
construction scoring **1,786**.

---

> ## Certified run: manifest `99a5fe3feede`
>
> The computational content of these theorems was re-run from an empty
> checkpoint namespace on 2026-08-17 at commit `4174af3`, with a clean
> source tree, one solver build (OR-Tools 9.15.6755) and one machine
> across every cell.
>
> | | |
> |---|---|
> | cells | 50 of 50 complete, 0 corrupt, 0 unstamped |
> | configurations | 1,327 enumerated, **1,327 refuted** |
> | undecided | 0 — the last case closed by decomposition *in the pipeline* |
> | above the threshold | 0 |
> | lexicon | `data/NWL2023.txt`, sha256 `7ced912101628ad7…`, 196,601 words |
>
> `results/MANIFEST.json` binds the environment, the parameters, and a
> SHA-256 of every artifact, cell checkpoint and verdict file.
> `python -m scrabble_max.manifest --verify` re-hashes them.
>
> The run that preceded it was **not** exhaustive: it reused a checkpoint
> left by an aborted launch and skipped five configurations of pattern
> (0,1,3,7,11,13,14). All five refute, and the certified run enumerates
> them. `results/soundness_remediation.md` records what was wrong and what
> changed; `results/tier3_results.md` carries the corrections inline.
>
> `check_independent.py` re-derives what can be re-derived without a
> solver, from a separate implementation of the rules that imports nothing
> from `scrabble_max`: 31 checks, 0 failures, including the 1,786 score
> from the board layout up and 1,063 of the 1,327 refutations. What it
> cannot verify — 264 CP-SAT infeasibility claims, and the stage-A
> geometry caps — it reports as out of scope rather than as agreement.

---

> ## Status: recomputed after the `cross_options` bug; all theorems stand
>
> A soundness bug was found in `tighten.cross_options` after these
> theorems were written. It deduplicated cross-word options by the
> remainder's letter *multiset*, but callers read the remainder's
> *order* — the row-1 inward letter and the adjacency constraints both
> depend on it. YARE and YEAR are both valid Y-hooks with remainder
> multiset {A,E,R} but inward letters A and E; only one survived.
>
> The direction is the unsafe one. Fewer options means a smaller
> feasible region, so `tighten_candidate`'s optimum can come out **below**
> the true maximum — and these values are used as upper bounds. Anything
> eliminated because its bound fell at or below 1,786 may have been
> eliminated wrongly, so the surviving set can only **grow**.
>
> | | status |
> |---|---|
> | Theorem 1 (geometry, ≤1656) | **unaffected** — stage A uses `best_rest_table`, not `cross_options` |
> | Theorem 2 (≤1778) | **reconfirmed** — stage B recomputed, every bound identical |
> | Theorem 3 (7 tiles) | **reconfirmed** — 1,730 / 1,706 recomputed, both identical |
> | Theorem 4 (14 patterns) | **reconfirmed** — tier 2 recomputed on the fixed `cross_options`: 165 → 14, unchanged |
> | Theorem 5 (record = 1786) | **unaffected** — rules engine only |
> | Theorem 6 (reachability) | **unaffected** — `reachability.py`, `racks.py` |
> | §8 (all 14 refuted) | **closed** — every pattern re-enumerated from scratch post-fix; see §8 |
>
> **Recomputation so far** (commit `d9420e9`, `PYTHONHASHSEED=0`,
> OR-Tools 9.15.6755). All 17 stage-B candidates returned bounds
> identical to the pre-fix run, in all 136 per-mask cells: still exactly
> one entry above 1,786 (OXYPHENBUTAZONE row 0, stage B⁺ 1,794), and the
> largest of the rest still 1,778. The `|S| ≤ 6` optima are still 1,730
> and 1,706. So Theorems 2 and 3 stand as written.
>
> The bug was not inert, though. In the `|S| ≤ 6` model eight per-mask
> cells moved **up** and none moved down — row 0 mask 3 from 714 to 717,
> mask 6 from 716 to 718, and similarly on row 14. The mask that
> Theorem 3 rests on, `{0,7,14}`, was not among them. The pattern is
> mechanical: the old dedup kept the highest-scoring representative of
> each anagram class, so an unconstrained optimum usually landed on a
> surviving option, and the deleted ones only bind once other constraints
> force a structurally compatible but lower-scoring cross word. Tier 2
> pins the placed set, a tighter constraint still, so it is where numbers
> are likeliest to move — and Theorem 4 is stated below as if they have
> not.
>
> One clarification on scope. A separate determinism defect in
> `build_line_dawg` — unsorted trie construction, giving seed-dependent
> state numbering — changes which model is emitted but not the feasible
> region it describes, so it does not alter the value of any
> infeasibility or proved optimum. The dedup bug is different in kind:
> it deletes legal options and so shrinks the region itself. A proved
> optimum over a too-small region is still a wrong upper bound, and an
> infeasibility is exactly the verdict a missing option can manufacture.
> All 165 tier-2 verdicts — the 140 infeasibilities included — are
> therefore suspect, and the 165 → 14 reduction must be recomputed in
> full.

---

## 0. Setup

**Board.** 15×15. Premium squares: 8 triple-word (TW), 17 double-word
(DW, including the centre), 12 triple-letter (TL), 24 double-letter (DL),
in the standard arrangement. Verified against the official layout in
`rules.py` by assertions on the counts and on pairwise disjointness.

**Tiles.** The standard 100-tile English distribution; face values sum to
187 over the 98 lettered tiles; 2 blanks score 0. Asserted in `rules.py`.

**Lexicon.** `L` = NWL2023, 196,601 words, from
`scrabblewords/scrabblewords`.

**Position.** An assignment of tiles to a subset of cells such that every
maximal horizontal or vertical run of length ≥ 2 is a word of `L`, and
the occupied cells are connected through the centre.

**Move.** A set `P` of newly placed tiles, `1 ≤ |P| ≤ 7`, all in one row
or one column, contiguous with the pre-existing tiles of that line,
touching at least one pre-existing tile (or the centre if the board is
empty), such that the resulting position is legal.

**Score.** For each word formed (the main word plus one cross word per
placed tile that has a perpendicular neighbour): sum of letter values,
with letter premiums applied only under newly placed tiles, multiplied by
the product of word premiums under newly placed tiles. A cross word
shares the word multiplier of its hook cell. Plus 50 if `|P| = 7`.

`board.py::apply_move` implements exactly this and is validated in §6.

---

## 1. The soundness principle

Everything below rests on one observation, used repeatedly.

> **Lemma 1 (one-directional relaxation).** Let `Legal` be the set of
> legal plays and `R ⊇ Legal` any superset. Then
> `max_{Legal} score ≤ max_{R} score`, and if `R` contains no play scoring
> `≥ t` then neither does `Legal`.

*Proof.* Immediate from `Legal ⊆ R`. ∎

Consequently: to **eliminate** a case it suffices to exhibit a relaxation
of it with optimum `≤ 1786`; and any relaxation's optimum is a valid
upper bound on the truth. The converse does **not** hold — a relaxation
being satisfiable proves nothing — which is why §7 needs the exact model.

Each relaxation used below is justified where introduced by showing every
legal play satisfies it.

---

## 2. Theorem 1 — geometry reduction **(complete)**

> **Theorem 1.** Every legal play whose main word does not occupy an
> entire edge row (row 0 or row 14, all 15 cells) scores at most
> **1,656**.

*Proof.* The board is symmetric under transposition, and scoring is
transposition-equivariant, so it suffices to treat horizontal plays; the
vertical case follows by transposing the position.

A horizontal play is determined by a row `r`, a start column `c0`, a
length `L`, a word `w ∈ L` of length `L`, and a placed subset
`S ⊆ {c0..c0+L−1}` with `1 ≤ |S| ≤ 7`. There are 1,575 triples
`(r, c0, L)` with `L ≥ 2` and `c0 + L ≤ 15`.

For each triple define the word-independent cap

```
cap(r,c0,L) = WM · (VMAX[L] + Σ_{letter-premium cells} (lm−1)·10)
            + (top 7 over the span of max_ch cb[ch][r][c]) + 50
```

where `WM` is the product of all word multipliers in the span, `VMAX[L]`
the largest blank-adjusted letter sum of any `L`-letter word of `L`, and
`cb[ch][r][c]` an upper bound on the cross-word contribution of letter
`ch` newly placed at `(r,c)`.

This is a relaxation in the sense of Lemma 1: the main word's letter sum
is at most `VMAX[L]` plus the premium boosts (letter values are at most
10); the word multiplier is at most the product over *all* word-multiplier
cells in the span; each placed cell contributes at most the best cross
score available to any letter there; at most 7 cells are placed; and the
bingo bonus is at most 50. Every legal play therefore scores at most the
cap for its geometry.

Evaluating all 1,575 caps (`bounds.py::geometry_cap_table`): exactly
**two** exceed 1,786, namely `(r,c0,L) = (0,0,15)` and `(14,0,15)`. The
largest cap among all others is **1,656**, attained at `(7,0,15)` — the
centre row, which carries the centre DW. ∎

> **Corollary 1.1.** A play beating the record occupies all 15 cells of
> row 0 or of row 14 (or, by transposition, of column 0 or column 14).

---

## 3. Theorem 2 — one word, one row **(complete)**

> **Theorem 2.** Every legal play other than OXYPHENBUTAZONE occupying
> row 0 scores at most **1,778**.

*Proof.* By Theorem 1 only the two full-edge-row geometries survive. For
these, enumerate every 15-letter `w ∈ L` playable with at most two blanks
and compute the exact optimum of the relaxed objective over placed
subsets (`bounds.py::relaxed_max_for_span`, exact by enumerating
word-multiplier masks and taking the best remaining cells greedily).
Seventeen `(word, row)` pairs exceed 1,786.

Each of the 17 is then bounded by the stage-B model
(`tighten.py::tighten_candidate`), which adds to the relaxation:

* **hook validity** — a cross word must be a real word having the main
  word's letter as its first (row 0) or last (row 14) letter, and its
  remainder must itself be a word of `L` when of length ≥ 2, since that
  remainder is a maximal run in the *pre-move* position;
* **run structure** — maximal runs of pre-existing tiles in the played
  row must be words;
* **global inventory** — letters used by the main word and all cross
  words respect the 100-tile distribution, with at most 2 blanks, and
  blanks placed on scoring cells forfeit at least their face value;
* **pairwise adjacency** — letters adjacent at a shared depth must
  co-occur adjacently in some word.

Every legal play satisfies all four, so Lemma 1 applies. The resulting
bounds (`results/tight_bounds.json`):

| word | row | bound |
|---|---:|---:|
| OXYPHENBUTAZONE | 0 | **1798** |
| OXYPHENBUTAZONE | 14 | 1778 |
| DEMYTHOLOGIZERS | 14 | 1716 |
| DEMYTHOLOGIZING | 14 | 1703 |
| REMYTHOLOGIZING | 14 | 1666 |
| DEMYTHOLOGIZING | 0 | 1650 |
| HYPERIMMUNIZING | 0 | 1645 |
| NEPHRECTOMIZING | 0 | 1642 |
| *(9 more, all ≤ 1639)* | | |

Exactly one entry exceeds 1,786. The largest of the rest is 1,778.

**The candidates that were never tightened.** The 17 are exactly those
whose *stage-A* bound exceeds 1,786; the others were dropped at stage A
and never passed to stage B, so for them we hold only the stage-A bound.
For the theorem as stated we need those bounds to be at most 1,778 too —
otherwise a candidate bounded at, say, 1,780 would be unaccounted for.
Ranking every candidate by stage-A bound (`results/stage_a_ranking.json`):

| rank | word | row | stage-A bound |
|---:|---|---:|---:|
| 17 | OVEREMPHASIZING | 0 | 1789 |
| **18** | **PROVINCIALIZING** | **0** | **1777** |
| 19 | COMMERCIALIZING | 0 | 1772 |

The 18th-largest is **1,777 ≤ 1,778**, and stage-A bounds are valid upper
bounds by Lemma 1, so every untightened candidate is also at most 1,778.
Combining: `max(1778, 1777) = 1778`. ∎

*Recomputed after the `cross_options` fix (commit `d9420e9`): all 17
stage-B bounds returned identical, so the table above is post-fix data.
The stage-A ranking is untouched by the bug — `bounds.py` never calls
`cross_options`.*

> **Corollary 2.1 (the main result so far).** *The record play's own
> geometry is the only one in the game that can beat it.* Any play
> scoring more than 1,786 is OXYPHENBUTAZONE placed across row 0 — up to
> transposition and the top↔bottom reflection of the board — and scores at
> most 1,798.

Note this is strictly stronger than "no better play is known": it is a
complete case analysis with 1,778 < 1,786 as the margin.

*On the symmetries named.* Transposition is a symmetry because horizontal
and vertical play are structurally interchangeable and the premium layout
is symmetric about the main diagonal. The **top↔bottom** reflection is a
symmetry for the same reason with one extra observation: it maps row 0 to
row 14 column-for-column, so words continue to read left-to-right and
legality is preserved. The **left↔right** reflection is *not* generally
one — it reverses every horizontal word, and `EMIT` reversed is not a word
— so it is deliberately not claimed here.

The distinction costs nothing, because the enumeration does not quotient by
either symmetry: rows 0 and 14 are modelled separately throughout
(`tighten.py` builds the cross-word options with the hook letter first on
row 0 and last on row 14), and the transposed cases are covered by
Corollary 1.1's case analysis rather than assumed away. The symmetries
appear in this statement to describe the equivalence class of geometries,
not to reduce the work.

---

## 4. Theorem 3 — structure of a record-beating play **(complete)**

> **Theorem 3.** A play beating the record covers all three triple-word
> squares of row 0 (columns 0, 7, 14) and places exactly 7 tiles, hence
> scores the 50-point bingo bonus.

*Proof.* Run the stage-B model of §3 separately for each of the 8 subsets
`T` of covered TW columns. With `WM = 3^{|T|}`, the per-mask optima are

| TW mask | bound |
|---|---:|
| {0,7,14} | 1798 |
| any other | ≤ **784** |

(`results/tight_bounds.json`, field `per_mask`). So all three TWs are
covered.

For the tile count, run the same model with `Σ placed ≤ 6`, which forces
the bingo variable to 0 (`tighten.py`, `max_placed=`). The optima
(`results/bound_six_tiles.json`) are

| row | `|S| ≤ 6` bound |
|---|---:|
| 0 | **1730** |
| 14 | 1706 |

Both are below 1,786, so a record-beating play places all 7 tiles and
takes the bingo bonus.

*(The arithmetic-only version does not suffice here: the stage-A bound for
`|S| ≤ 6` is 1,912, i.e. it eliminates nothing. The interlocking
structure enforced by stage B — hook validity, run structure, inventory —
is what closes the gap from 1,912 to 1,730.)* ∎

*Recomputed after the `cross_options` fix (commit `d9420e9`,
`tighten --six-tiles`): 1,730 and 1,706 both returned identical, as did
the ≤784 per-mask figure above. Eight of the other `|S| ≤ 6` per-mask
cells did move — all upward, none down, e.g. row 0 mask `{0,7}` from 714
to 717 — which is the fix behaving as it must, since enlarging the
feasible region can only raise an optimum. None of the moved cells is one
the theorem rests on.*

---

## 5. Theorem 4 — reduction to 14 placed patterns **(complete)**

> **Theorem 4.** A play beating the record has its placed set among 14
> explicitly listed 7-subsets of `{0..14}`, and scores at most **1,794**.

*Proof.* By Theorem 3 the placed set `S` satisfies `|S| = 7` and
`{0,7,14} ⊆ S`, leaving 4 free columns from the remaining 12:
`C(12,4) = 495` candidate patterns.

**Tier 1.** Score each pattern with the stage-A relaxation of §2, now
evaluated at a *fixed* `S` rather than maximised over `S`
(`patterns.py::pattern_bound`). By Lemma 1 this is an upper bound for
that pattern. 330 of the 495 fall at or below 1,786; **165** survive.

**Tier 2.** For each survivor, run the stage-B model of §3 with the
placed set pinned (`tighten.py`, `fix_placed=`). This is again a
relaxation of the plays with that placed set. Eliminate any pattern whose
optimum is ≤ 1,786. Elimination uses only *proven* upper bounds: on a
solver timeout the returned value is `BestObjectiveBound()`, still a valid
upper bound for a maximisation; if the solver yields no bound at all the
pattern is kept. **14** survive, with these ceilings
(`results/pattern_row1.json`):

| ceiling | placed columns |
|---:|---|
| 1794 | (0, 1, 3, 7, 9, 11, 14) |
| 1794 | (0, 1, 3, 7, 10, 11, 14) |
| 1792 | (0, 1, 3, 5, 7, 11, 14) |
| 1792 | (0, 1, 3, 6, 7, 11, 14) |
| 1792 | (0, 2, 3, 6, 7, 11, 14) |
| 1791 | (0, 1, 2, 3, 7, 11, 14) |
| 1791 | (0, 1, 3, 4, 7, 11, 14) |
| 1791 | (0, 2, 3, 7, 9, 11, 14) |
| 1791 | (0, 2, 3, 7, 10, 11, 14) |
| 1790 | (0, 1, 3, 7, 8, 11, 14) |
| 1790 | (0, 2, 3, 7, 8, 11, 14) |
| 1788 | (0, 1, 3, 7, 11, 13, 14) |
| 1788 | (0, 2, 3, 4, 7, 11, 14) |
| 1787 | (0, 2, 3, 7, 11, 13, 14) |

The maximum ceiling is 1,794. ∎

**Two checks on the list** (neither is an independent proof of the
count).

1. *Consistency check.* An earlier, abandoned approach enumerated
   *(placed set, cross-word assignment)* configurations globally, without
   quantifying over placed sets. In 21 hours it produced 1,300
   configurations, and every one lies in these 14 placed sets
   (`tests/test_patterns.py`). This is evidence the 14 are not *too few*
   in the region that run explored — but it is **not** an independent
   verification that there are only 14, because that run never
   terminated. It sampled; it did not exhaust. Had it run to completion
   it would have been an independent derivation; it did not, so it is a
   sanity check and nothing stronger.
2. *Soundness check.* The list contains `(0, 1, 3, 6, 7, 11, 14)`, the
   placed set of the record play itself. It must, since that play scores
   1,786 and any sound filter must retain it; a filter that dropped it
   would be provably wrong. Asserted as a test.

The exhaustiveness of the 14 rests on tiers 1 and 2 alone: 495 patterns
enumerated combinatorially, each eliminated only on a proven upper bound.

---

## 6. Theorem 5 — the record is verified **(complete)**

> **Theorem 5.** The transcribed construction is a legal play scoring
> exactly 1,786, forming the eight words below.

*Proof.* By direct evaluation in the rules engine, independent of the
solver stack (`known.py`, `tests/test_rules.py`). The engine re-derives
every word and the total from the board and the move alone:

OXYPHENBUTAZONE 1458, ESTABLISHMENTS 63, OPACIFICATIONS 69,
BLADDERLIKE 57, PREQUALIFYING 34, NARROWING 13, ZOOGAMETE 31, XED 11 —
total **1,786**. ∎

The same engine is validated independently against the canonical
128-point MUZJIKS opening, and the stage-C tableau model is validated by
fixing its grid to this board and recovering objective exactly 1,786.

---

## 7. Theorem 6 — reachability in a legal game **(complete)**

> **Theorem 6.** The record is achievable in a legal two-player game.
> There is a 26-move game from the empty board — 25 build-up moves plus
> the record play — in which every move is board-legal, the players
> alternate strictly, and every tile played is drawn from the standard
> 100-tile bag into a rack of at most 7.

*Proof.* In two parts.

**Board legality.** A backwards "unplay" search (`reachability.py`)
removes one move at a time from the record's pre-move position while
maintaining the invariant that what remains is valid and connected,
terminating at the empty board. The forward sequence is replayed through
`apply_move`, which accepts every move and reproduces the pre-move
position exactly (`results/reachability.log`). The opening move covers
the centre, as the rules require.

**Rack and bag feasibility.** Deal the 26 moves to two players in strict
alternation. Since any permutation of the bag is a legal shuffle, the
draws are ours to choose, so this is an existence question, answered
constructively (`racks.py`): each player draws 7 to start and refills to
7 after each of their moves, taking the tiles their soonest upcoming move
needs. Every move's tiles are then in the mover's hand when played. The
schedule closes exactly:

```
97 tiles played, 3 left on racks, 0 left in bag   (= 100)
```

with no letter exceeding its distribution, both blanks used, and no rack
ever above 7. The bag empties after move 25.

The witness is re-checked by `verify_witness`, which replays the recorded
draws against a fresh bag using independent logic and asserts every rule
at each step, so the schedule is a self-contained certificate rather than
a claim about the generator (`results/rack_schedule.json`,
`tests/test_racks.py`). ∎

This matters because the published construction is a *static* board.
Neither "buildable by legal moves" nor "arises in a real game" follows
automatically from the other, and the second is the one a player would
care about. Both now hold.

---

## 8. Closing the fourteen patterns **(complete)**

Theorem 4 reduces the claim to fourteen explicit placed patterns. All
fourteen are now refuted.

**Tier 2 — four die outright.** Charging each blank a lower bound on what
it really forfeits, rather than only its face value, drops four patterns'
ceilings to 1,786 or below. The charge is `2 × value` per blank when the
configuration has no cheap non-multiplier cell for that letter and zero
otherwise; both are under-charges, so the objective stays an upper bound
and Lemma 1 still applies. Ten patterns survive.

**Tier 3 — the remaining ten.** For each, enumerate every configuration it
admits and decide each one exactly.

*Enumeration.* A blocking-clause loop per pattern, run to infeasibility;
`complete=True` therefore means the list is the whole of it. To use more
than one core per pattern the space is partitioned: every configuration
either gives a chosen pivot column no cross word or gives it exactly one
of its options, so partitioning the option indices into blocks partitions
the configurations into cells with independent loops. Cells are covering
(asserted) and disjoint (checked at runtime). Result: **1,322
configurations**, every cell terminating INFEASIBLE.

*Refutation.* Each configuration is decided by, in order of cost:

1. **the exact blank ceiling** — for a *pinned* configuration the forced
   blanks are determined, so the score has a closed-form upper bound. 1,063
   of 1,322 fall here with no solve at all;
2. **the full tableau** (`cstage.solve_tableau`) with the cross words
   pinned and `total ≥ 1,787` asserted. INFEASIBLE is a genuine
   unsatisfiability proof. 258 fall here;
3. **cell decomposition** (`decompose.py`) for anything the tableau cannot
   decide within its limit. Exactly one configuration needed this.

A finding worth recording, because it is the opposite of what was
expected: the 258 tableau refutations are not about score. Re-run with the
score constraint removed entirely — asking only whether *any* legal board
realises the configuration — a sample of twelve returned INFEASIBLE 12 of
12 in ~2.8 s each. They describe boards that cannot exist at all, and
propagation refutes them without 1,786 ever entering the proof. The
expensive-looking half of tier 3 was the cheap half.

### The one configuration that resisted

`(0,1,3,7,10,11,14)` with cross words OPACIFICATIONS / XEROSES /
PREADJUSTING / BRAINWASHING / AMELIORATIVE / ZOOGAMETE / EQUALITY, exact
ceiling 1,787. Still UNKNOWN after 1,300 s, and — unlike its siblings —
UNKNOWN even with the score constraint dropped: it has no shallow
structural contradiction, so the solver must search rather than propagate.
Its static features are unremarkable (67 cross tiles against a median 68,
143 free cells against 142, one forced blank like most).

It is refuted by splitting on individual board cells. Every legal board
puts *something* in a given cell, so if every possible value is refuted so
is the configuration — provided the option set is **exhaustive**. For a
row-1 cell under a pre-existing column that set is `{empty} ∪ {letters
that can follow the row-0 letter in some word}`; deeper cells take any
letter. Critically the set may **not** be narrowed to letters with tiles
still spare, because a blank can supply a letter whose copies are used up.

Recursing to depth 6 refutes it in **180 solves**. The result is carried by
two independent implementations — depth-first with the model rebuilt per
branch, and breadth-first in parallel with branches varied through CP-SAT
assumptions — which agree on the solve count and on the open-branch count
at every depth (506 s and 140 s respectively).

The sharpest available check on the method: run the same refuter against
the **record's own configuration** at threshold 1,785, where a 1,786 board
demonstrably exists. It refutes 9 of 10 branches and leaves standing
exactly the branch containing the record. A non-exhaustive option set
would have refuted all ten.

### What follows, and what does not

Combining §2–§7 with the above: **no legal NWL2023 play scores above
1,786**, and since the record achieves it (Theorem 5) and is reachable in
a legal game (Theorem 6), 1,786 is the maximum.

What that statement does *not* cover:

* **NWL2023 only.** Collins/CSW is a larger lexicon and would plausibly
  admit more. Nothing here speaks to it.
* **A single play, not a game total.**
* **Computer-assisted, not machine-checked.** It rests on CP-SAT's
  correctness, on the lexicon file, and on the encodings modelling the
  rules faithfully. No proof assistant has checked any of it.
* **Lemma 1 is load-bearing throughout.** Every stage must only ever
  *enlarge* the feasible set. This is where the project has actually had
  bugs — `cross_options` deduplicating by multiset shrank the region, the
  unsound direction — and it is where a reviewer should start. Every
  affected stage was recomputed; 28 of 28 tier-2 bounds reproduce exactly.

## Reproduction

Commands and result files for every computation above are listed in
`REPORT.md` §10. The tests in `tests/` re-check the load-bearing claims:
the record's score, the pattern counts (495 / 165), the soundness of the
tier-1 filter against the record's own placed set, that the 14 are
consistent with the abandoned global enumeration, that the per-pattern
enumeration covers the global one, and — since the `cross_options` bug —
that no two order-distinct cross words are ever merged into one option.

Dependencies are pinned in `requirements.txt` and runs set
`PYTHONHASHSEED=0`. Soundness does not depend on either: every
elimination rests on a proven upper bound, which stays an upper bound
under any solver version or iteration order. What they buy is
*reproducibility* of the particular numbers quoted above. Each pipeline
entry point records `results/PROVENANCE.json` — commit, OR-Tools
version, interpreter, platform, hash seed, and the lexicon's SHA-256 and
word count — so any figure here can be traced to the run behind it.

The pre-fix result files are kept under `results/pre_fix/` so the
recomputation can be checked against them rather than merely replacing
them. The fix only enlarges the models' feasible region, so every
recomputed bound must come back **greater than or equal to** its pre-fix
value, and every surviving set must be a **superset** of its pre-fix
counterpart. A bound that moved down, or a case that disappeared, would
indict the fix rather than the old data.
