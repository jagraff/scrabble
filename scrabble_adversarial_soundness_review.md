# Adversarial Soundness Review: `jagraff/scrabble`

## Scope

Repository reviewed: `https://github.com/jagraff/scrabble`

Audit target: the current proof/computational pipeline supporting the claim that **1,786 is the maximum possible single-turn Scrabble score under the repository's stated ruleset**.

The main goal of this review was not code quality. It was to find **soundness bugs**: places where the implementation or certificate machinery could incorrectly eliminate a legal position, incorrectly claim exhaustive coverage, or otherwise make a false theorem appear proved.

## Executive Summary

I did **not** find a concrete counterexample showing that the 1,786 headline result is false.

I did find one **high-severity soundness hole** in the tier-3 checkpoint/resume system that can cause the program to falsely report exhaustive coverage, plus several secondary correctness/provenance issues.

The most important issue is:

> **Completed tier-3 checkpoints are trusted without validating that they were generated for the same threshold, partition definition, lexicon, code revision, solver version, or other relevant model settings.**

This means stale checkpoints from a different computation can silently contaminate a later run and cause cases to be skipped while still being reported as complete.

Because the final proof depends on exhaustively closing all tier-3 cells, this is a real certificate-soundness problem even if the committed result itself happens to be correct.

---

# Findings

## 1. HIGH: Tier-3 checkpoints are not bound to the computation they certify

### Problem

The checkpoint/resume layer accepts a cell marked `complete` and immediately trusts it.

However, checkpoint identity/metadata does not appear to include all parameters that determine the meaning of the cell, including at least:

- score threshold
- number of partition blocks / partition definition
- exact option membership in a cell
- lexicon hash
- git commit / source tree hash
- OR-Tools / solver version
- model flags and other relevant configuration

The stored metadata appears far too weak to establish that a checkpoint corresponds to the run currently being executed.

### Why this is a soundness bug

A completed checkpoint is being used as a proof obligation discharge:

> “This portion of the search space has already been exhaustively checked.”

That statement is only valid if the checkpoint was generated from **exactly the same search space and model**.

If checkpoint identity does not encode the computation, “complete” is not a meaningful certificate.

### Concrete failure mode

For example:

1. Run tier 3 with:

   ```text
   --threshold 1786 --blocks 4 --checkpoint-dir X
   ```

2. Allow some or all cells to become marked complete.

3. Re-run with the same checkpoint directory but:

   ```text
   --threshold 1785
   ```

   or with a different:

   ```text
   --blocks N
   ```

4. Existing completed cells can be accepted without recomputation.

For a lower threshold, configurations scoring exactly 1,786 or otherwise newly entering the search may need to be enumerated, but the old checkpoint did not search for them.

For a different partition definition, `cell_N` can correspond to a different subset of option combinations.

Yet the resume layer can still interpret the checkpoint as proof that the new cell has been exhausted.

### Impact

This is capable of manufacturing a **false completeness result**.

It directly affects any theorem whose proof depends on statements such as:

- all tier-3 cells were exhausted;
- all remaining cases were closed;
- no legal board exceeds the threshold.

### Recommended fix

Every checkpoint should contain and validate a canonical computation identity before reuse.

At minimum hash or record:

```text
git tree / commit
lexicon contents hash
threshold
pattern / geometry
pivot
partition block count
exact partition membership for this cell
all solver/model flags
OR-Tools version
Python version if relevant
blank-handling mode
objective / feasibility mode
```

Prefer a canonical serialized manifest and store:

```text
computation_hash = SHA256(canonical_manifest)
```

Each checkpoint should include that hash.

On resume:

```text
if checkpoint.computation_hash != current.computation_hash:
    reject checkpoint
```

Do not merely warn.

### Stronger fix

Make checkpoint directories namespaced by the computation hash so stale reuse is impossible by construction:

```text
checkpoints/<computation_hash>/cell_0001.json
```

---

## 2. HIGH/MEDIUM: Provenance does not establish the final tier-3 computation

### Problem

The proof documentation claims that pipeline outputs have sufficient provenance to trace results to the run that generated them.

However, the committed provenance data does not appear to fully identify the final tier-3 closure.

In particular, the provenance information references an earlier commit than the code/doc changes associated with the final tier-3 proof, and tier-3 does not appear to emit a complete run manifest that binds:

- the exact code revision;
- exact lexicon;
- threshold;
- partition parameters;
- all 1,322 cells;
- solver/runtime versions;
- checkpoint identities.

### Why this matters

This issue is especially important because of Finding 1.

If checkpoints were intrinsically self-authenticating, weak top-level provenance would mostly be a reproducibility problem.

But because stale checkpoints are accepted, the final artifact needs to demonstrate that every “complete” cell was generated under the intended computation.

Currently that appears to rely partly on human process/documentation rather than machine-verifiable evidence.

### Impact

This does not prove the result is wrong.

It means the committed artifacts do not fully prove that the reported exhaustive run was generated entirely under the exact intended configuration.

### Recommended fix

Generate a final immutable run manifest containing:

```text
repository commit/tree hash
dirty working tree status
lexicon SHA256
CLI arguments
all model configuration
solver versions
partition definition
list of every expected cell
for each cell:
    cell identity hash
    checkpoint result hash
    status
    solver result
    elapsed time
aggregate result
```

Then have the final proof output reference the manifest hash.

A clean reproduction should start from an empty checkpoint directory.

---

## 3. MEDIUM: `verify_witness` does not verify every rule claimed by the proof text

### Problem

The proof documentation describes the witness verifier as independently checking the legality of the full game / every rule.

The implementation appears weaker than that description.

Potential omissions include:

- using `zip(witness_moves, moves)` without asserting equal lengths;
- not explicitly enforcing alternating players;
- not verifying correct initial rack sizes;
- not fully enforcing refill-to-seven mechanics;
- not checking stored `rack_after`;
- not checking stored `bag_left`.

### Failure example

If the verifier performs:

```python
for a, b in zip(expected, actual):
    ...
```

without:

```python
assert len(expected) == len(actual)
```

then a truncated sequence can pass all pairwise comparisons.

More generally, a witness verifier should derive state rather than trust redundant state recorded in the witness.

### Impact

This weakens the claim that the committed game schedule is a fully independently verified legality certificate.

I did not find a specific illegality in the committed witness itself.

So this is currently a **verifier soundness/documentation mismatch**, not evidence that the reachability claim is false.

### Recommended fix

The verifier should reconstruct the entire game state from first principles.

For each turn, verify:

```text
correct player
rack before move
tiles actually available
board legality
dictionary legality
tile consumption
score
bag contents
draw count
rack after move
player alternation
```

At the end verify:

```text
number of moves exactly matches
bag state exactly matches
both racks exactly match
target board exactly matches
```

Any serialized `rack_after`, `bag_left`, etc. should be checked against recomputed values rather than treated as authoritative.

---

## 4. MEDIUM: Stage-C API is unsound for partial `tw_placed` masks

### Problem

The Stage-C model appears to support a parameter describing which triple-word squares are occupied.

For a strict subset of the three TW squares, the model forces the specified TW squares occupied but does not necessarily force unspecified TW squares empty.

At the same time, scoring appears to use only the number of listed TW squares.

### Why this can under-score a legal solution

Suppose:

```text
tw_placed = {TW1, TW2}
```

but a model solution also occupies `TW3`.

If the board constraints permit that while the score formula still assumes only two TW multipliers, the model can assign a score lower than the actual Scrabble score of the represented position.

If this model is used as an upper-bound/elimination model, under-scoring is dangerous:

> a genuinely winning legal board could be represented but scored below the cutoff, allowing a false infeasibility/elimination conclusion.

### Impact

The final 1,786 proof apparently uses all three TW squares in the relevant computation, so this may not affect the headline result.

But the API/model is unsound for its more general advertised input domain.

### Recommended fix

Either:

1. enforce exact occupancy:

```text
specified TW squares must be occupied
unspecified TW squares must be empty
```

or:

2. compute score from actual modeled TW occupancy.

The latter is generally safer.

Add regression tests for all subsets of the three TW squares.

---

## 5. LOW: Reflection is described as a symmetry when it is not generally one

### Problem

The proof text says certain cases are equivalent “up to transposition and reflection symmetries.”

Transposition is a valid Scrabble-board symmetry because horizontal and vertical play are structurally interchangeable.

Ordinary reflection is more subtle because Scrabble words are directional: reflecting a position reverses word order unless letters/words are transformed accordingly.

The implementation itself appears to distinguish top and bottom placements rather than quotienting them by reflection.

### Impact

Likely documentation error rather than a computational soundness failure.

### Recommended fix

Remove “reflection” unless there is a precise proof of the particular reflection equivalence being used.

State only the symmetries that are actually applied by the enumeration.

---

# Areas Audited Without Finding a Break

I specifically looked for places where an alleged upper bound might accidentally become a lower/tighter bound and therefore eliminate legal positions.

I did **not** find an obvious remaining soundness bug in:

- Stage-A coarse score bounds;
- current Stage-B CP-SAT encoding;
- corrected treatment of anagrammatic cross-word options;
- corrected blank accounting;
- closed-form blank-loss ceiling;
- full-board tier-3 model;
- final exhaustive cell decomposition.

The current code appears to have already fixed at least two historically dangerous classes of bugs:

1. collapsing distinct anagrammatic cross-word placements;
2. overcharging / mishandling blank usage.

Those fixes should still receive explicit regression tests.

---

# Required Remediation Before Treating the Repository as a Strong Computational Proof

## Must fix

### A. Make checkpoint reuse cryptographically/configurationally safe

A checkpoint must be rejected unless it exactly matches the computation being run.

### B. Produce a fresh end-to-end run from an empty checkpoint directory

Do not reuse any prior cell artifacts.

### C. Emit a machine-verifiable final run manifest

The manifest should bind:

- source revision;
- lexicon;
- all parameters;
- solver version;
- exact partition;
- every cell result.

### D. Strengthen witness verification

The game witness verifier should derive and validate the complete state transition sequence.

---

# Suggested Regression Tests

## Checkpoint threshold isolation

```text
Run threshold=1786 into checkpoint dir X.
Re-run threshold=1785 using X.
Expected: old checkpoints are rejected.
```

## Checkpoint partition isolation

```text
Run blocks=4 into X.
Re-run blocks=5 using X.
Expected: old checkpoints are rejected.
```

## Lexicon isolation

```text
Run with lexicon A into X.
Modify one lexicon entry.
Re-run using X.
Expected: old checkpoints are rejected.
```

## Code revision isolation

```text
Run at commit A.
Change a model constraint.
Re-run with same checkpoint directory.
Expected: old checkpoints are rejected.
```

## Truncated witness

Remove the last move from the serialized witness.

Expected:

```text
verify_witness == failure
```

## Extra witness move

Append a spurious move.

Expected:

```text
verify_witness == failure
```

## Corrupted rack metadata

Modify `rack_after` without modifying the actual move sequence.

Expected:

```text
verify_witness == failure
```

## Corrupted bag metadata

Modify `bag_left`.

Expected:

```text
verify_witness == failure
```

## Partial TW masks

For every strict subset of the three triple-word squares, construct a model case in which an unspecified TW square is otherwise occupiable.

Expected:

```text
model either forbids that occupancy or scores it correctly
```

---

# Recommended Final Certification Procedure

After fixes:

1. Checkout the exact release commit.
2. Assert the working tree is clean.
3. Hash the lexicon.
4. Delete all old checkpoints.
5. Run the entire proof pipeline from scratch.
6. Save a canonical run manifest.
7. Hash every resulting certificate/checkpoint.
8. Independently run certificate verification.
9. Commit:
   - manifest;
   - hashes;
   - summarized results;
   - exact commands used.
10. Make `PROOFS.md` cite the manifest hash.

The intended theorem should not depend on trusting an operator's statement that stale checkpoints were not reused.

---

# Bottom Line

I found **no concrete counterexample to the 1,786 maximum**.

However, the current repository does **not yet constitute a fully sound computational certificate** because its checkpoint/resume mechanism can accept completed work from a different computation and falsely treat it as exhaustive for the current one.

That is the issue to fix first.

Once checkpoint identity/provenance is hardened and the full tier-3 computation is rerun cleanly, the remaining mathematical/modeling pipeline looks substantially stronger based on this audit.
