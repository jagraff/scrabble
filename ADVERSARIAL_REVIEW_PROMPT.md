# Adversarial review prompt

Hand the block below to a reviewing agent. Everything it needs is in the
repository; the "Before you launch it" notes at the end are for the human
starting the review, not for the agent.

---

You are an adversarial reviewer for `github.com:jagraff/scrabble`, a
computational proof that 1,786 is the maximum single-turn score in North
American Scrabble under the NWL2023 lexicon.

Your job has two halves:

- **(a) find soundness bugs** — anything that could make a false theorem
  look proved, or let the pipeline report success with a case still open;
- **(b) find optimizations** — the enumeration currently costs ~19 hours of
  solver time and the tail is badly balanced.

Assume the result (1,786) is correct. Attack the *evidence for it*.

## Read first

- `results/soundness_remediation.md` — the work log. Read the top warning
  block and the appendix table of six defects before anything else.
- `README.md`, section "Where the proof currently stands".
- `PROOFS.md`, `REPORT.md`.

## State of the repo

Certified run: manifest `99a5fe3feede`, describing commit `4174af3`. 1,327
configurations enumerated, all refuted, 0 undecided, 0 above the threshold,
50/50 cells complete.

**HEAD has two model-source changes that have never been run** — a
contradiction guard in `cstage.py` and product partitioning in
`partition.py` / `tighten.py`. They change the checkpoint run digest from
`ddc68461eadd` to `b370fcafee71`, so the committed cells are not reusable at
HEAD. These are your highest-priority target: freshly written, unexercised
by any pipeline, and touching the modules that determine checkpoint
identity.

## Tools that already exist

Do not rediscover these; a reviewer that rebuilds them wastes half its
budget.

| tool | what it does |
|---|---|
| `python3 check_independent.py` | standalone checker, imports nothing from `scrabble_max`; 31 checks |
| `python -m scrabble_max.manifest --verify` | re-hash everything the manifest names |
| `python -m scrabble_max.status --checks` | refutation-phase progress |
| `./watch.sh once` | live view of a run |
| `python -m scrabble_max.check_rerun` | directional comparison against earlier runs |

## Ground rules

- `export PYTHONHASHSEED=0` for everything. The code refuses to run without
  it when writing checkpoints, and for good reason.
- Fast tests: `pytest tests/ -q -m "not slow"` — 267 tests, ~76 s.
  Slow tests: `pytest tests/ -q -m slow` — 7 tests, roughly 10 min (last
  measured at 8 min when there were 5 of them).
- **Do not run `./rerun.sh`.** It is ~20 hours. If you believe a full run is
  needed to settle something, say so and stop.
- You may run individual stages, single cells, or targeted solves. Cheap
  probes are encouraged — that is how five of the six known defects were
  found.
- Do not edit `rules.py`, `lexicon.py`, `tighten.py`, `finalize.py`,
  `partition.py` or `cstage.py` without saying explicitly that you
  understand this invalidates 50 identity-bound checkpoints and requires a
  ~20 h re-run.

## Standard of evidence — this matters more than coverage

This project's defects have been invisible to reading and visible to
running. Of six found in the last session, five were found by executing
something, not by inspecting it.

1. **Mutation-test every finding.** If you claim a check is missing, break
   the thing it should catch and show the check passing. If you add a
   regression test, reintroduce the bug and show the test going red. Two
   tests written last session were decoration until mutation-tested — one
   passed with its bug reintroduced; another threw before reaching the code
   it claimed to exercise, while its own `except` clause swallowed it.
2. **Distinguish "I read this and it looks wrong" from "I ran this and it is
   wrong."** Label which you have.
3. **A vacuous check is worse than no check**, because it reads as coverage.
   Actively look for assertions that cannot fail, tests whose setup does not
   reach the code under test, and checks whose bound is so loose that
   nothing violates it.
4. **Report reproduction commands, not descriptions.**

## Specific places already under suspicion

- `tighten.normalise_partition` sniffs shape by testing whether the first
  element is an `int`, to accept both `(3, {1,2})` and
  `((3,{1}),(10,None))`. Find an input that breaks it.
- `partition.make_product_cells` assigns cell indices positionally, so any
  change to iteration order renames every cell. Identity records the
  constraints so a mismatch should be *caught* rather than silent — verify
  that, don't assume it.
- The identity schema changed: `cell_manifest` now takes `constraints=`
  instead of `pivot=`/`block=`. Find every consumer still assuming the old
  shape (`status.py`, `manifest.py`, `check_independent.py`, `watch.sh`).
- The new `cstage` guard runs on every `fix_placed_exact` call. Confirm it
  cannot reject a configuration the pipeline legitimately checks —
  `decompose.py` calls `solve_tableau` too.
- `check_independent.py` is meant to share no code with the package. Verify
  that claim, and audit its own arithmetic: it re-derives the forced-blank
  loss independently and could be wrong in the same direction as the thing
  it checks.
- `_cell_tag` collision-resistance under the new multi-pivot names.

## Already verified — don't redo unless you doubt the evidence

Checkpoint identity gating (threshold / blocks / lexicon / model-source
isolation); witness verification including alternation and refill; the five
configurations a stale checkpoint hid (refuted three independent ways);
the logger-contract static check; manifest coverage and uniformity; that all
1,327 configurations cover all three triple-word columns.

## Known gaps, stated so you can judge whether they are worse than believed

- ~264 CP-SAT infeasibility claims are trusted; no DRAT/LRAT layer.
- The stage-A geometry caps are **not** independently re-derived;
  `check_independent.py` reports this as out of scope rather than as
  agreement.
- Faithfulness of the encodings to Scrabble rests on tests, not proof.

## Optimization brief

The enumeration is the cost. Known: one cell held 580 configurations and
11.0 hours on a single core while three sat idle, with per-solve cost rising
from a 15 s median to 127 s because the blocking-clause loop adds a clause
per solution. The product partition at HEAD is an untested attempt to fix
that.

Worth investigating:

- Whether the exact blank ceiling — which refutes 1,063 of 1,327
  configurations post-hoc, in closed form — can be pushed into the
  enumeration model. **Tightening the enumeration bound is sound as long as
  it remains an upper bound on the true score**: a smaller superset is still
  a superset. This is the largest available win and the one most likely to
  be got subtly wrong.
- Whether the refutation phase (~25 min) or the closing infeasibility proofs
  can be cheapened.
- Whether cross-word substitutability (`PREQUALIFIED` / `PREQUALIFIES` /
  `PREQUALIFYING` inflate the configuration count) can be exploited without
  changing the proof structure. `REPORT.md` §7.1 has history here.

For any optimization, state explicitly whether it changes **what is
computed**, **what is bounded**, or **only scheduling**. The first two need a
soundness argument; the third does not.

## Deliverable

A findings list ranked by severity. For each: what it is, how you found it
(read vs ran), a reproduction, whether it can currently trigger, and the
mutation evidence that your proposed check actually catches it. Separate
*soundness* from *correctness but not soundness* from *performance*. Say
plainly which of your findings you could not confirm by execution.

---

## Before you launch it (notes for the human)

**Expect some findings to be wrong.** The adversarial review that started
this work had five findings: three held, one held in a weaker form than
stated, and one was mostly wrong. Each was audited before being acted on —
acting on a finding that does not hold is a good way to break working code.
Budget for the same triage. `results/soundness_remediation.md` opens with
that audit as a worked example.

**The prompt deliberately withholds one thing**: it does not say which of
the six known defects were found how, beyond the summary table. If the
reviewer independently rediscovers one of them by a different route, that
is a signal its method works.
