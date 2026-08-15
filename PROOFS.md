# Proofs

What is established so far about the maximum single-turn score in North
American Scrabble under NWL2023, stated as theorems with their proofs.

Results marked **(complete)** have no open cases. Results marked
**(partial)** are stated with exactly what remains. Every theorem here is
independent of the unfinished work in §7 unless it says otherwise.

Throughout, "the record" means Bob Lucassen's OXYPHENBUTAZONE
construction scoring **1,786**.

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

> **Corollary 2.1 (the main result so far).** *The record play's own
> geometry is the only one in the game that can beat it.* Any play
> scoring more than 1,786 is OXYPHENBUTAZONE placed across row 0 — up to
> the transposition and reflection symmetries of the board — and scores at
> most 1,798.

Note this is strictly stronger than "no better play is known": it is a
complete case analysis with 1,778 < 1,786 as the margin.

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

## 7. Theorem 6 — constructibility by legal board moves **(complete, and weaker than "reachable in a game")**

> **Theorem 6.** The pre-move position of the record is reachable by a
> sequence of 25 **legal board moves** from the empty board: each move
> places between 1 and 7 tiles in a single line, contiguous and connected
> as the rules require, and every intermediate position is valid. The
> cumulative tile usage is consistent with the official tile set.

*Proof.* By exhibition. A backwards "unplay" search (`reachability.py`)
removes one move at a time while maintaining the invariant that the
remaining position is valid and connected, terminating at the empty
board; the forward sequence is then replayed through `apply_move`, which
accepts every move (`results/reachability.log`).

Tile accounting over the 25 moves plus the final 1,786 play: 95 lettered
tiles and both blanks, **97 of 100**, with **no letter exceeding its
distribution** and at most 7 tiles per move. ∎

**What this does not establish.** It is *not* proved that the sequence
arises in a game with legal rack and bag mechanics. `reachability.py`
treats draws as unconstrained — its docstring says so explicitly — and
models no bag, no per-player racks, and no alternation. A full result
would have to exhibit an assignment of the 25 moves to two alternating
players together with a bag ordering such that each player holds the
tiles they play in a rack of at most 7 at the moment they play them.
The tile accounting above is a *necessary* condition for that and it
passes, but it is not sufficient.

So the honest statement is **constructibility by legal board moves**, not
reachability in a legal game. The distinction is worth keeping: the
published construction is a static board, and neither "buildable by legal
moves" nor "arises in a real game" follows from the other automatically.
Closing the gap is tractable — it is a scheduling problem over a known
move sequence — and is listed as open in §8.

---

## 8. What is not proved

The headline claim — that 1,786 is the global maximum — is **open**. By
Theorem 4 it reduces to fourteen explicit cases, of which **8 are closed**
and 6 remain.

The method for closing one (`patterns.py::prove_pattern_by_configs`) is:

1. enumerate every *configuration* (placed set with a concrete cross word
   per placed column) whose stage-B relaxed score exceeds 1,786, by a
   blocking-clause loop, until the model is infeasible — at which point
   the list is provably exhaustive;
2. refute each configuration with the full 15×15 tableau model, which
   pins those columns and leaves supports, glue, blanks and connectivity
   free, asking for any legal position scoring ≥ 1,787.

Soundness: any legal position beating the record realises some
configuration, and its relaxed score is at least its true score, so it
appears in the list; refuting every entry refutes the pattern. The
enumeration terminates per pattern (it did not globally) because
restricting to one placed set bounds the search space.

Result so far: **1,903 configurations across 8 patterns, every one
infeasible**, each enumeration proven exhaustive. Adding the 1,300 from
the abandoned global run, no legal position above 1,786 has been found
anywhere.

Six patterns are open: the two at ceiling 1,794, the three at 1,792, and
one at 1,791. Two are being worked now.

Also open, and independent of the above: **rack and bag feasibility** for
the 25-move sequence of §7 (assign the moves to two alternating players
and exhibit a bag ordering supplying each rack), which would upgrade
Theorem 6 from constructibility to reachability in a legal game.

**No useful bound on the remaining time can be given.** The number of
configurations per pattern is boundable exactly — it is a count over
cross-word tuples reaching the threshold — but that bound is 10⁹–10¹⁰ per
pattern against actual counts of 9–824, seven orders of magnitude loose,
because tile-bag scarcity and row-1 word validity do the real pruning and
neither is expressible in the count. Tightening it requires running the
search. CP-SAT likewise admits no useful per-solve time bound. So the
completion time is genuinely unknown, not merely uncertain.

---

## Reproduction

Commands and result files for every computation above are listed in
`REPORT.md` §10. The tests in `tests/` re-check the load-bearing claims:
the record's score, the pattern counts (495 / 165), the soundness of the
tier-1 filter against the record's own placed set, the agreement between
the two independent derivations of the 14, and that the per-pattern
enumeration covers the global one.
