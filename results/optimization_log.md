# Optimisation attempts, measured

Kept so nothing here is retried on a hunch. Every figure is measured on
pattern `(0,2,3,7,11,13,14)` unless stated, PYTHONHASHSEED=0.

## Taken

| change | effect |
|---|---|
| `num_search_workers=1` | median solve 14.6s vs 24.2s at 8 workers, and a tighter spread (13.7–17.4 vs 18.2–36.9). One thread is faster in wall-clock, not merely cheaper. Complete enumeration 274s vs 415s at 8 workers. |
| pattern-level parallelism | enumeration within a pattern is sequential (each solve depends on the previous blocking clause), so the only axis is running patterns concurrently: ~8× on 8 cores. |
| in-model blank penalty | 4 of 14 patterns die at tier 2 outright; the rest keep lower ceilings. Per-solve cost rises ~17%, so it pays only where the configuration count falls a lot — which is exactly the expensive patterns (824 → ~43). |
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

Model construction is 0.5s **once**; `cross_options` and the DAWG about
6.4s once. Everything else is CP-SAT's C++ search. There is no Python hot
spot to optimise — the cost is intrinsic to re-solving a
10,698-constraint model with 45 automata once per configuration found.
