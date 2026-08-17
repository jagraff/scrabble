# Soundness remediation: work log

Tracks the response to `scrabble_adversarial_soundness_review.md`, and the
five further defects that turned up while acting on it. One section per
finding: what the code actually did, what changed, and the test that pins
it. Every claim is backed by a test that runs in seconds.

**Status: complete.** The certified run is manifest `99a5fe3feede` at
commit `4174af3`:

| | |
|---|---|
| cells | 50 of 50 complete, 0 corrupt, 0 unstamped |
| configurations | 1,327 enumerated, **1,327 refuted** |
| undecided | 0 — closed by decomposition inside the pipeline |
| above the threshold | 0 |
| environment | one solver build, one machine, one commit, clean source |

`check_independent.py`, which shares no code with the package, agrees: 31
checks, 0 failures. `python -m scrabble_max.manifest --verify` reports
everything it names unchanged.

---

## Verification of the review's findings

The review was audited before being acted on. Three findings held, one held
in a weaker form than stated, one was mostly wrong.

| # | claim | verdict |
|---|---|---|
| 1 | checkpoints not bound to their computation | **confirmed**, and the sharpest instance was not the one named |
| 2 | provenance does not identify the final run | **confirmed** |
| 3 | `verify_witness` weaker than documented | **partly** — the named exploit does not work, a different one does |
| 4 | Stage-C partial `tw_placed` unsound | **confirmed latent**, no effect on any committed number |
| 5 | reflection is not a symmetry | **mostly wrong** |

### 1 — the block count, not the threshold

The review led with `--threshold`. The likelier break is `--blocks`.
`make_cells` round-robins option indices, so cell *i* covers indices
`i mod n_blocks`; the cell index is in the file name but the block count was
not, and three entry points defaulted to 4, 8 and 24 blocks while writing to
the same `results/enum_cells`. Re-running a 4-block directory at 8 blocks
reused five files whose union no longer covered the option set and printed
`complete=True`.

### 3 — the exploit the review named does not work

The review's headline was `zip(witness_moves, moves)` with no length check,
allowing a truncated witness. That one is already blocked: the 100-tile
accounting identity sums played tiles over the full move list but racks over
only the zipped prefix, so a short witness fails `!= 100`. Every move places
at least one tile, so the identity cannot be satisfied by a short witness.

The real hole was `p = rec['player']` — the mover was read out of the record
instead of derived from the move index. Sweeping all 25 adjacent-owner swaps
found **24 tile-feasible schedules in which one player takes two turns in a
row**, every one of which the old verifier accepted. That is the "two
alternating players" claim the schedule exists to certify.

Also unchecked: `rack_after` and `bag_left` were written to the witness and
never compared against anything; refill-to-seven was not enforced; opening
hands were not required to be seven tiles.

### 5 — reflection

Top↔bottom reflection *is* a genuine Scrabble symmetry: the premium layout
is symmetric under it and left-to-right reading order is preserved. It is
left↔right reflection that reverses words. And nothing in the pipeline
quotients by either — row 0 and row 14 are enumerated separately
(`tighten.py:12,113`). The sentence in `PROOFS.md` is descriptive, not
load-bearing; it needs a precision edit, not a deletion. Deferred to P3.

---

## P0.1 — checkpoint identity (`scrabble_max/identity.py`)

A cell checkpoint makes two claims: a list of configurations, and
`complete` — the blocking-clause loop reached INFEASIBLE. The second is a
discharged proof obligation and is only meaningful about the model it was
proved for.

**Gated** (mismatch ⇒ `StaleCheckpoint`, raised not warned): lexicon digest,
threshold, word, row, `blank_penalty`, `prune_unplaced`, `n_blocks`,
pattern, pivot, cell index, **explicit block membership**, a digest of the
model-building sources, and `PYTHONHASHSEED`.

**Recorded, not gated**: OR-Tools version, Python, platform, git commit.

### Where this diverges from the review, and why

*The review wanted OR-Tools version to be a hard reject.* An infeasibility
proof is a fact about the model, not about the solver that found it, so a
proof from 9.14 and one from 9.15 establish the same proposition. Gating on
it would discard sound work on every upgrade and make every future bump
silently invalidate the whole certificate. The legitimate worry it answers —
"a solver build turns out to be buggy and I must find everything it
touched" — is served by recording the version in every header and asserting
*uniformity* over the finished manifest (P1), which is the stronger
property: checked over the whole artifact rather than pairwise at resume.

*The review wanted the git commit gated.* A typo fix in a markdown file
would then invalidate hours of solver output, which trains the operator to
pass `--allow-unstamped`, and a gate that is routinely bypassed protects
nothing. The digest covers the six modules that can change the emitted
model; the commit is still recorded.

*Stricter than the review on `PYTHONHASHSEED`.* Gating on
`os.environ.get` alone is close to worthless: with the variable unset every
worker records the same `None` and so compares equal to every other, while
each actually runs under a different random seed — the check would report a
match in exactly the dangerous case. `require_hash_seed()` refuses to start
instead.

Identity applies to *persisted* artifacts only. With no checkpoint directory
nothing is stored that a later run could mistake for its own, so an
in-memory enumeration needs no stamp and is not made to demand one.

Belt and braces: checkpoint directories are namespaced
`results/enum_cells/run-<hash12>/`, so stale reuse is impossible by
construction even if the check regresses.

**Also fixed:** the three conflicting `n_blocks` defaults now all reference
`partition.DEFAULT_BLOCKS`. Identity stamping detects the mismatch, but a
trap that is merely detected is still a trap.

**Tests** — `tests/test_identity.py`, 24 tests, 0.32 s. The four isolation
cases the review asked for (threshold, blocks, lexicon, code revision), plus
block membership at equal count, header/legacy handling, hash-seed refusal,
digest collision hygiene, and two wiring tests that drive `_run_cell` end to
end with the solver stubbed out.

## P0.2 — witness verification (`scrabble_max/racks.py`)

`verify_witness` now derives everything it checks. The mover comes from the
move index; `rack_after` and `bag_left` are recomputed and compared;
refill-to-seven is enforced; opening hands must be exactly seven; witness
and move-list lengths must agree.

`schedule()` gained an `owner=` override. It exists so a deliberately
non-alternating schedule can be built and rejected — the only way to
demonstrate that alternation is enforced rather than merely recorded.

**New: `verify_board_sequence`.** `verify_witness` consumes tile *counts*,
so it cannot see where the tiles went: a schedule for an entirely different
set of moves satisfies it. The sequence is now re-parsed with its cells
intact and replayed through the rules engine, confirming legality and word
validity at every step, that the final position is the record board, and
that the last move scores exactly 1786. This closes a gap the review did not
raise: the rack witness and the board were previously joined only by a text
log.

Run output:

```
26 moves (25 build-up + the record play), 97 tiles played
board replay: True  (26 moves replayed, final move scored 1786)
rack/bag feasible with 2 alternating players: True
witness independently re-verified: True  (97 played, 3 on racks, 0 in bag)
```

**Tests** — `tests/test_racks.py`, 20 tests, 0.07 s. Every tamper case from
the review (truncate, append, corrupt `rack_after`, corrupt `bag_left`) plus
skipped refill, short opening hand, a draw the bag cannot supply, four
tile-feasible alternation breaks, and two board-replay cases.

Non-vacuity was checked rather than assumed: the pre-fix verifier was
re-run against each tamper case. It accepted the extra trailing move,
corrupted `rack_after`, corrupted `bag_left`, and all 24 alternation breaks.
It rejected truncation, skipped refill and the short opening hand — the
first via the accounting identity, the others incidentally. The tests say
which is which rather than implying all of them were exploits.

## P0.3 — `tw_placed` exactness (`scrabble_max/cstage.py`)

`solve_tableau` forced the named TW columns occupied but left the rest free,
while scoring read the word multiplier off `len(tw_placed)`. A solution
covering an unnamed TW square was therefore scored below its true value —
and since this model eliminates configurations by failing to reach a
threshold, under-scoring can discard a legal record-beating board.

Now pinned exactly through `tw_occupancy()`, matching what `tighten.py` has
always done (`tighten.py:333-334`). **No committed number changes**: every
caller passes the full `(0, 7, 14)` mask, which has no unnamed columns. The
per-mask bounds behind Theorem 3 come from `tighten.py` and were never
affected.

**Tests** — `tests/test_cstage.py`, all 8 subsets of the three TW columns,
plus a test tying `WM = 3 ** len(mask)` to the pinned occupancy so the two
cannot drift apart.

---

---

## P1 — provenance and the clean re-run

### What the chain could not reproduce

Preparing the re-run turned up a gap the audit did not find:
`results/blank_penalty_tier2.json` is what `tier3.py` reads to decide which
patterns to enumerate, and **it had no entry point**. It was produced once
by an ad-hoc script and committed. Everything downstream of it was
reproducible; the step that selected the work was not, so a clean re-run
would have had to inherit it.

`scrabble_max/blank_tier2.py` fills that in. It derives the same 14
survivors from `pattern_row1.json` — verified against the committed file,
same set — and asserts the two directional facts the sweep must satisfy: no
bound may rise under the penalty, and the record play's own placed set must
stay at or above 1,786 (below that the model would be refuting a play that
demonstrably exists).

### Correction to the note below

An earlier draft of this log said stage-B solve statuses were unrecorded.
That was wrong: all 17 bounds carry `detail.proved_optimal = True`, nested
inside `detail` rather than at top level, which a top-level probe missed.
Stage B is clean.

The real gap was narrower — the *per-mask* cells recorded a value and no
status, and Theorem 3 rests on those. `tighten.py` now fills a `status_out`
map with `OPTIMAL` / `BOUND` / `INFEASIBLE` per mask, so a re-run that
disagrees on a cell can be told from a bug: a `BOUND` is a valid upper
bound that moves with the solver version, and an `OPTIMAL` is not supposed
to move at all.

### The manifest

`scrabble_max/manifest.py` records the environment, the parameters, and a
SHA-256 of every artifact and every cell checkpoint, in one file whose own
digest can be quoted. Two properties it asserts that no individual
checkpoint can:

* **coverage** — every cell the partition defines has a file, and every file
  belongs to a cell that was asked for. A cell that was never launched
  writes nothing, so 49 files where 50 were expected looks exactly like 49
  where 49 were expected.
* **uniformity** — one solver build, one interpreter, one commit across
  every cell. This is where the cost of *not* gating identity on the solver
  version is collected: a mixed artifact is possible by construction, so it
  is caught over the finished whole.

It also separates `source_dirty` from `git_dirty`. The latter is true for
the whole of any run, because the results being regenerated are themselves
tracked files, so it cannot answer the question that matters — whether the
code that produced them was committed.

### The re-run

`rerun.sh`, one command, ~2.5 h on four cores. Each stage is followed by the
check that can fail it, ending with `check_rerun` (bounds may only rise,
survivor sets may only grow) and the manifest. Not resumable by design.

`results/pre_hardening/` holds the previous state for comparison — the 50
old cell checkpoints included, because they are the evidence of the original
tier-3 run and deleting them would destroy the audit trail.

One consequence of the source digest worth stating plainly: editing any of
the six model-building modules invalidates every checkpoint and forces a
fresh ~1 h enumeration. Adding the per-mask status recording to `tighten.py`
did exactly that, moving the run digest from `5de00fc1974d` to
`ddc68461eadd`. That is the intended trade — over-gating costs compute,
under-gating costs a false theorem — but it means model edits should be
batched before a certifying run, not dribbled in after one.

---

## P2 — soundness gaps found while certifying, not in the audit

The audit asked whether a stale checkpoint could be reused. Wiring the chain
so a machine could check it end to end turned up three places where the
pipeline could report success with the proof open. None appear in the
review.

### The last open case was closed in prose

Tier 3's refutation leaves configurations CP-SAT cannot decide at its time
limit. On the recorded run there was exactly one — exact ceiling 1787, so if
realisable at all it beats the record by a point, and UNKNOWN after 1300 s
even with the score constraint dropped. `tier3_results.md` describes how it
was closed: pin a board cell, recurse, refute all 180 branches,
independently reproduced by a second implementation.

But `decompose.py` had **no CLI, and `tier3.py` never called it**. The
closure was a manual invocation written up as prose. A clean re-run would
stop at `1 UNDECIDED`, print that the proof was not closed, and **exit 0** —
`rerun.sh` would have recorded the step as successful.

Run against the committed artifacts, the new checker reports the true
machine-checkable state:

```
1322 enumerated, 1322 checked, 1321 refuted,
1 UNDECIDED and not closed by decomposition
```

`tier3` now runs the decomposition itself, records each outcome in
`tier3_checks/decomposed.json`, and exits non-zero on anything undecided,
anything above the threshold, or an enumeration that did not finish.

### The refutation half was certified by nothing

Cell checkpoints establish that the *enumeration* was exhaustive. The
verdicts refuting what it enumerated were unhashed and uncounted, so "every
configuration refuted" rested on a line of console output. A configuration
enumerated and then never checked would leave no trace at all — absence is
precisely what a listing of the verdict files cannot show. The manifest now
hashes every verdict file and counts refuted against enumerated.

Related: `verify()` had begun recording those hashes without re-checking
them. A recorded hash that nothing verifies is worse than no hash, because
it reads as coverage while providing none.

### The witness was certified by nothing

The upper bound says nothing beats 1,786. The other half of the theorem says
1,786 is *attained and reachable*, and that half is a file on disk like any
other. A run whose witness quietly stopped verifying, replayed to a
different board, or scored 1,785 would have been certified exactly as
happily as one that did not. `check_witness` requires all four: a schedule
exists, it re-verifies, it replays to the record board, and the final move
scores 1,786.

### Smaller things

* `rerun.sh` runs both test suites before any solving. Certifying results
  produced by code that fails its own tests certifies nothing.
* `reachability.py` carried `assert replay == grid or True` directly above
  the real check — a no-op that reads like a check, which is worse than
  none, because the next reader will believe it.

### Checked and cleared

* `max_configs=100000` returns `complete=False` when the cap is hit. No
  false exhaustiveness.
* The reachability node budgets fail safe: exhaustion reports no sequence
  found, so they cannot manufacture reachability.
* `known_upper` is applied only where the exact per-configuration blank
  ceiling is at or above the threshold, and `int()` floors an
  integer-valued score, so it cannot cut off a real solution.
* Every per-mask cell in the re-run came back `OPTIMAL` — 17 candidates × 8
  masks, no timeout-derived bound anywhere. Theorem 3's cells are
  solver-version-independent as a matter of measurement, not argument.

### Two tests that fail mid-run, by design

`test_survivors_match_the_recorded_sweep` and
`test_tier_two_survivors_match_the_config_enumeration` compare across result
files. During a re-run the directory is half-regenerated and they fail. That
is correct behaviour — they are consistency assertions over the artifact set
— and it is why `rerun.sh` runs the suites before touching results rather
than after.

---

## P3 — what the clean re-run found

### A stale checkpoint was reused, and it cost five configurations

The audit's central worry was not hypothetical. Four of the 50 archived cell
checkpoints contain only a `complete` marker with no `started` line, and
`started` is written unconditionally before any solving — so those four were
not produced by the code the run used. Their mtimes are 19:22:45–19:23:07 on
2026-08-15; commit `ed8a8a3`, which added the marker, landed at 19:23:45,
and the tier-3 run began at 19:24:31. They are leftovers from an aborted
launch, consumed as complete.

Three were harmless. The fourth, `00010307111314_p03c001`, claimed **0
configurations in 15.12 s**; the clean re-run enumerates the same cell in
**116 s and finds 5**.

`tier3_results.md` had already recorded the symptom. Its prediction table
has exactly one miss — pattern `(0,1,3,7,11,13,14)`, predicted 5, actual 0 —
explained away as *"the one miss goes in the safe direction: 0
configurations means that pattern is refuted with nothing left to check."*
That reasoning is backwards. Missing configurations is never the safe
direction: they were not refuted, they were not looked at. An independent
check fired correctly and was rationalised.

### The five are refuted, so 1,786 stands

All five survive the exact-blank ceiling, so only a tableau solve settles
them. Decided with `check_configs` at the current commit:

```
[1/5] relaxed=1787 -> INFEASIBLE (3s)
[2/5] relaxed=1787 -> INFEASIBLE (2s)
[3/5] relaxed=1787 -> INFEASIBLE (2s)
[4/5] relaxed=1788 -> INFEASIBLE (2s)
[5/5] relaxed=1787 -> INFEASIBLE (2s)
```

Cross words: `OPACIFICATIONS / XEROTIC|XEROSES / PREQUALIFYING /
BLADDERLIKE / ZOOGAMETE|ZOOGAMETES / NARROWING|NARROWED /
ESTABLISHMENTS`. All refute in seconds by propagation, matching the
archived observation that the configurations surviving the ceiling are
usually structurally impossible rather than merely low-scoring.

The pipeline decides these same five again in its own refutation phase;
that second verdict is an independent confirmation, not a formality.

### So the conclusion held and the certificate did not

The 1,786 result is unchanged. What was false is the claim that it had been
*exhaustively verified*: the committed artifact skipped five configurations,
and nothing in it recorded that. Reading the repository could not have
revealed this. Only re-running from an empty directory did.

### The 29.7-minute enumeration was a replay

`tier3_results.md` records the tier-3 enumeration as taking 29.7 minutes.
The archived cells' start times span **15.2 hours**, 2026-08-15 19:24 to
2026-08-16 10:38. Both are true: the 29.7 minutes measured a final pass over
mostly-cached cells, not a computation. That is exactly the condition in
which a leftover file gets consumed unnoticed. The clean re-run's tier-3
enumeration takes hours, which is the honest figure.

---

## P5 — the independent verification, complete

Run on the idle cores while the certified pipeline works through its
straggler cell. None of it writes to `results/`; it is corroboration, not a
shortcut, and the certified run still has to reach these conclusions
through its own identity-bound artifacts.

| pattern | archived | independent re-run | verdict |
|---|---:|---:|---|
| 8 patterns | — | — | identical counts |
| (0,1,3,7,11,13,14) | 0 | **5** | the stale-checkpoint gap; all 5 INFEASIBLE |
| (0,1,3,7,10,11,14) | 623 | **623** | identical set, different partition |

For the largest pattern, enumerated from scratch under a **different pivot
column and block count** (10/48 against 3/4) and reaching the identical
623-configuration set — zero found that the archive lacked, zero missing.
Then decided: 550 by exact ceiling with no solve, 72 by CP-SAT proof, 1
UNDECIDED, **0 above 1786**.

The one undecided is the configuration `tier3_results.md` describes as "the
one that resisted":

```
OPACIFICATIONS / XEROSES / PREADJUSTING / BRAINWASHING
AMELIORATIVE / ZOOGAMETE / EQUALITY
   -> refuted=True, 0 open branches, 404s
```

Closed by `tier3.decompose_undecided` -- the production function, not a
reimplementation -- so the path that crashed on its first real invocation
now has an end-to-end confirmation rather than only a stubbed test.

Every configuration of every surviving pattern is therefore accounted for
by an independent route, and nothing reaches 1787.

## Bugs found by using the tools rather than reading them

Worth recording as a pattern, because all three were invisible to review:

* **the decomposition crash** -- found by running the production path on
  the pattern that actually contains an undecided configuration;
* **the status watcher merging two runs** -- found by watching a live run
  next to an archived one;
* **the manifest matching verdicts by count** -- found by running the
  manifest against a half-finished run.

And two of my own tests were decoration until mutation-tested: the first
decomposition regression test passed with the bug reintroduced, and a
second raised AttributeError before reaching the code it claimed to
exercise while its own except-clause swallowed it. Every non-trivial guard
in this remediation has since been checked by breaking the thing it
guards.

## Deliberately not done, and why

* **A runtime assertion in `cstage.solve_tableau`.** Combining a
  configuration whose placed set omits a triple-word column with the
  default full mask makes the model infeasible by contradiction rather
  than by refutation — a silent false refutation. It predates the
  exactness change and cannot arise today, because Theorem 3 puts all
  three triple-word columns in every pattern that reaches tier 3; verified
  over all 1,327 configurations and pinned by
  `tests/test_tw_mask_invariant.py`.

  The assertion is still the more direct guard, and it is not applied
  because `cstage.py` is one of the six modules whose text determines
  checkpoint identity. Editing it invalidates 50 identity-bound cells and
  18.7 hours of solver time, and leaves the certified manifest pointing at
  a commit whose model sources differ from HEAD — reintroducing exactly
  the provenance drift this work exists to remove. **Batch it into the
  next model-touching run**, together with anything else that needs those
  six files.

* **Partition pivot selection.** `choose_pivot` maximises the number of
  cross options in the lexicon, not the spread of configurations that
  actually exist. On (0,1,3,7,10,11,14) it picks column 3, whose 1,619
  options carry only 15 realised words with 334 sharing one; round-robin
  splits option *indices*, so those 334 are atomic and no block count
  divides them. One cell ran for over eleven hours on one core while three
  sat idle. Column 10 realises 118 distinct values with a largest bucket of
  57: re-enumerating there with 48 blocks took 90 minutes on 3 cores and
  reached the identical 623 configurations.

  Pure scheduling — it changes which cell computes what, not what is
  computed or how it is bounded — but it touches `partition.py`, so it
  belongs in the same batch.

## Still open, beyond this remediation

* ~264 CP-SAT infeasibility claims are trusted. Removing them from the
  trust base needs a DRAT/LRAT layer over a CNF re-encoding, checked by a
  verified checker. Note the trap: without a proof that the encoding is
  faithful, that moves trust from a heavily-tested solver to a bespoke
  encoder, which may be a downgrade. All defects found in this project
  have been in encoding, bookkeeping and orchestration; none in CP-SAT.
* The stage-A geometry caps are not independently re-derived —
  `check_independent.py` reports this rather than claiming agreement. It
  needs an independent cross-bound table, and is the last significant
  piece reachable without a solver.
* The lexicon being genuine NWL2023 is an empirical claim no formalisation
  can discharge.

---

## Appendix: what was actually done, in order

For someone picking this up cold. Commits `73aa8d6`..`c026bda`.

**Audited the review before acting on it.** Three findings held, one held in
a weaker form than claimed, one was mostly wrong. Recorded above with the
evidence, because acting on a finding that does not hold is how correct code
gets broken.

**P0 — checkpoint identity.** `identity.py`; headers on every cell; the gate
raises rather than warns; directories namespaced by run digest; the three
conflicting `n_blocks` defaults reconciled. Diverged from the review twice,
deliberately: the solver version is recorded but not gated (an infeasibility
proof is a fact about the model, not the prover), and `PYTHONHASHSEED` is
refused outright when unset rather than recorded as `None`.

**P0 — witness verification.** The verifier now derives everything it
checks, including the mover. `verify_board_sequence` ties the rack schedule
to the board it claims to build — a gap the review did not raise.

**P0 — `tw_occupancy`.** The tableau model pins all three triple-word
columns exactly. No committed number changes.

**P1 — provenance.** `manifest.py` (coverage and uniformity, matched by
identity rather than count); `blank_tier2.py`, which fills a hole where the
step that *selected* tier 3's work had no entry point at all; per-mask solve
statuses in `tighten.py`; `rerun.sh`; `check_rerun.check_identical`.

**P2 — three gaps the review missed**, all of which let the pipeline report
success with the proof open: the last case closed in prose rather than in
code, a refutation phase certified by nothing, and a witness certified by
nothing.

**The re-run.** ~19 hours of solver time across two attempts. The first died
after 11.7 hours on a `TypeError` in the decomposition — fixed three hours
earlier, but the process had loaded the module at start and an edit on disk
cannot reach a running interpreter. `--resume` was added so identity-bound,
complete cells are not discarded when the interruption is downstream.

**Independent verification**, on cores the straggler cell left idle: the
largest pattern re-enumerated under a different pivot and block count
reaching the identical 623 configurations; all 623 refuted; the stubborn one
closed by the production decomposition function; the five hidden
configurations refuted separately.

**`check_independent.py`.** A checker that imports nothing from the package.

**Corrections to the record.** `tier3_results.md`'s wrong figures struck and
its "safe direction" sentence quoted back rather than deleted;
`REPORT.md`'s reproduction section, which named a command that did not
produce its own artifact; `PROOFS.md`'s reflection claim.

### The six defects, and how each was found

| # | defect | found by |
|---|---|---|
| 1 | stale checkpoint: 5 configurations never enumerated or refuted | re-running from empty |
| 2 | decomposition crashed on a flushed log call | running the production path on the real case |
| 3 | status watcher merged two runs' counts | watching a live run beside an archived one |
| 4 | manifest matched verdicts by count, not identity | running the manifest mid-run |
| 5 | documented command did not produce its own artifact | the checker crashing on the wrong shape |
| 6 | `tier3.py` returned 0 with the proof open | reading exit paths while wiring `rerun.sh` |

Five of six were invisible to review. Two of the regression tests written
during this work were themselves decoration until mutation-tested — one
passed with its bug reintroduced, the other threw before reaching the code
it claimed to exercise while its own `except` swallowed it. Every
non-trivial guard here has since been checked by breaking the thing it
guards.
