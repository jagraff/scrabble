"""Stage C: full-tableau CP-SAT model for the one surviving geometry.

Decides exactly the static-feasibility question (question A): over ALL
legal pre-move positions, what is the maximum score of playing `word`
across an edge row hitting the given triple-word squares?

The model contains the complete 15x15 pre-move position:

  * g[r][c] in {0=empty, 1..26} for rows 1..14; row 0 is the played word,
    with placed_c choosing which of its tiles are new;
  * every row's and every column's maximal runs must be lexicon words or
    single tiles (line-DAWG automaton constraints; single tiles that are
    isolated in both directions are excluded by connectivity);
  * pre-move row 0 (placed cells empty) must satisfy the same rule, and
    each column must be valid BOTH pre-move (without the hook tile, via a
    v0 auxiliary symbol) and post-move (with it);
  * global tile inventory with at most 2 blanks; each blank subtracts
    only its face value from the score (an optimistic under-count of the
    real loss, so the model's optimum is an upper bound; any solution
    found is re-verified exactly by the rules engine);
  * pre-move connectivity to the center square via a flow model;
  * the score is computed exactly (main word with premiums on placed
    cells, cross words of placed cells over their contiguous runs, bingo
    for 7 tiles).

Maximizing the score therefore yields the true maximum for this geometry
up to the blank-loss optimism, with any incumbent solution independently
checkable.
"""

from __future__ import annotations

import json

from ortools.sat.python import cp_model

from .rules import DISTRIBUTION, N, VALUES
from .tighten import build_line_dawg

LETTERS = [chr(ord('A') + i) for i in range(26)]


def solve_tableau(lexicon, word: str, row: int = 0, *, tw_placed=(0, 7, 14),
                  time_limit=3600.0, hint_grid=None, hint_placed=None,
                  min_score=None, known_upper=None, fix_hint=False,
                  fix_placed_exact=None, fix_crosses=None,
                  fixed_blank_loss=None, fix_cells=None, build_only=False,
                  log=print, verbose=True):
    """Maximize the score of playing `word` on row 0 with the given TW
    cells placed.  Returns (status_name, best_value, bound, solution)."""
    assert row == 0, "row-14 candidates were eliminated earlier"
    assert len(word) == N

    transitions, start, finals = build_line_dawg(lexicon)
    delta = {}
    for s, sym, t in transitions:
        delta[(s, sym)] = t

    def code(ch):
        return ord(ch) - ord('A') + 1

    m = cp_model.CpModel()

    placed = [m.NewBoolVar(f'p{c}') for c in range(N)]
    for c in tw_placed:
        m.Add(placed[c] == 1)
    m.Add(sum(placed) <= 7)
    bingo = m.NewBoolVar('bingo')
    m.Add(sum(placed) >= 7 * bingo)
    m.Add(sum(placed) <= 6 + bingo)

    # grid vars rows 1..14
    g = {(r, c): m.NewIntVar(0, 26, f'g{r}_{c}')
         for r in range(1, N) for c in range(N)}
    occ = {}
    for (r, c), var in g.items():
        o = m.NewBoolVar(f'o{r}_{c}')
        m.Add(var != 0).OnlyEnforceIf(o)
        m.Add(var == 0).OnlyEnforceIf(o.Not())
        occ[(r, c)] = o

    # letter indicator bools
    lit = {}
    for (r, c), var in g.items():
        for i, ch in enumerate(LETTERS, start=1):
            b = m.NewBoolVar(f'l{r}_{c}{ch}')
            m.Add(var == i).OnlyEnforceIf(b)
            m.Add(var != i).OnlyEnforceIf(b.Not())
            lit[(r, c, ch)] = b

    # pre-move row 0 symbols
    v0 = []
    for c in range(N):
        var = m.NewIntVar(0, 26, f'v0_{c}')
        m.AddAllowedAssignments([var], [(0,), (code(word[c]),)])
        m.Add(var == 0).OnlyEnforceIf(placed[c])
        m.Add(var == code(word[c])).OnlyEnforceIf(placed[c].Not())
        v0.append(var)

    # line validity: rows 1..14
    for r in range(1, N):
        m.AddAutomaton([g[(r, c)] for c in range(N)], start, finals,
                       transitions)
    # pre-move row 0
    m.AddAutomaton(v0, start, finals, transitions)
    # columns: pre-move (v0 + rows 1..14) and post-move (hook letter fixed:
    # start from delta(root, letter) over rows 1..14)
    for c in range(N):
        col = [g[(r, c)] for r in range(1, N)]
        m.AddAutomaton([v0[c]] + col, start, finals, transitions)
        m.AddAutomaton(col, delta[(start, code(word[c]))], finals,
                       transitions)

    # center occupied pre-move
    m.Add(g[(7, 7)] != 0)

    # ---- optional: pin a specific configuration (per-config checking) ----
    if fix_placed_exact is not None:
        for c in range(N):
            m.Add(placed[c] == (1 if c in fix_placed_exact else 0))
    if fix_crosses is not None:
        for c in fix_placed_exact:
            w = fix_crosses.get(c)
            if w is None:
                m.Add(g[(1, c)] == 0)  # no cross word at this placed cell
                continue
            assert w[0] == word[c]
            for r in range(1, len(w)):
                m.Add(g[(r, c)] == code(w[r]))
            if len(w) < N:
                m.Add(g[(len(w), c)] == 0)  # the cross word ends here

    # inventory with blank allowances.  A blank on a *scored* tile (row 0
    # or a cross-word cell) loses at least its face value; blanks on
    # unscored tiles lose nothing.  Real tiles are assigned to scored
    # cells first, so at least (scored_count - bag) blanks are scored.
    over = {}
    for ch in LETTERS:
        cnt = sum(lit[(r, c, ch)] for r in range(1, N) for c in range(N))
        o = m.NewIntVar(0, 2, f'ov{ch}')
        m.Add(cnt + word.count(ch) - DISTRIBUTION[ch] <= o)
        over[ch] = o
    m.Add(sum(over.values()) <= 2)

    # board size <= 100
    m.Add(sum(occ.values()) + N <= 100)

    # ---- connectivity of the pre-move position (flow to center) ----
    # occupancy incl. row 0 pre-move
    occ_pre = dict(occ)
    for c in range(N):
        occ_pre[(0, c)] = placed[c].Not()
    cells = list(occ_pre)
    arcs = []
    for (r, c) in cells:
        for (rr, cc) in ((r + 1, c), (r, c + 1)):
            if (rr, cc) in occ_pre:
                arcs.append(((r, c), (rr, cc)))
    flow = {}
    CAP = 224
    for a, b in arcs:
        for (u, v) in ((a, b), (b, a)):
            f = m.NewIntVar(0, CAP, f'f{u}{v}')
            m.Add(f <= CAP * occ_pre[u])
            m.Add(f <= CAP * occ_pre[v])
            flow[(u, v)] = f
    total_occ = m.NewIntVar(0, 225, 'tocc')
    m.Add(total_occ == sum(occ_pre.values()))
    for cell in cells:
        inflow = sum(f for (u, v), f in flow.items() if v == cell)
        outflow = sum(f for (u, v), f in flow.items() if u == cell)
        if cell == (7, 7):
            m.Add(inflow - outflow == total_occ - 1)
        else:
            m.Add(inflow - outflow == -1 * occ_pre[cell])

    # ---- score ----
    dl_cols = (3, 11)
    # contiguous-run indicators below row 0
    inrun = {}
    for c in range(N):
        prev = None
        for r in range(1, N):
            ir = m.NewBoolVar(f'ir{r}_{c}')
            if prev is None:
                m.Add(ir == occ[(r, c)])
            else:
                m.AddBoolAnd([prev, occ[(r, c)]]).OnlyEnforceIf(ir)
                m.AddBoolOr([prev.Not(), occ[(r, c)].Not()]
                            ).OnlyEnforceIf(ir.Not())
            inrun[(r, c)] = ir
            prev = ir
    # per-cell scored value inside the cross run
    sval = {}
    for c in range(N):
        for r in range(1, N):
            v = m.NewIntVar(0, 10, f'sv{r}_{c}')
            val_expr = sum(VALUES[ch] * lit[(r, c, ch)] for ch in LETTERS)
            m.Add(v <= val_expr)
            m.Add(v <= 10 * inrun[(r, c)])
            m.Add(v >= val_expr - 10 * (1 - inrun[(r, c)]))
            sval[(r, c)] = v

    # scored-cell indicators: cross-word cells of placed columns
    scell = {}
    for c in range(N):
        for r in range(1, N):
            s = m.NewBoolVar(f'sc{r}_{c}')
            # s >= inrun & placed (one-sided is enough: the penalty only
            # needs a lower bound on scored blanks)
            m.Add(s >= inrun[(r, c)] + placed[c] - 1)
            scell[(r, c)] = s
    pen = {}
    for ch in LETTERS:
        u_terms = []
        for c in range(N):
            for r in range(1, N):
                u = m.NewBoolVar(f'u{r}_{c}{ch}')
                m.Add(u >= lit[(r, c, ch)] + scell[(r, c)] - 1)
                u_terms.append(u)
        p = m.NewIntVar(0, 2, f'pen{ch}')
        m.Add(p >= sum(u_terms) + word.count(ch) - DISTRIBUTION[ch])
        pen[ch] = p

    cross_scores = []
    for c in range(N):
        wm_c = 3 if c in tw_placed else 1
        lm_c = 2 if c in dl_cols else 1
        hook = VALUES[word[c]] * lm_c
        expr = wm_c * (hook + sum(sval[(r, c)] for r in range(1, N)))
        cs = m.NewIntVar(0, 3 * (20 + 14 * 10), f'cs{c}')
        m.Add(cs == expr).OnlyEnforceIf([placed[c], occ[(1, c)]])
        m.Add(cs == 0).OnlyEnforceIf(placed[c].Not())
        m.Add(cs == 0).OnlyEnforceIf(occ[(1, c)].Not())
        cross_scores.append(cs)

    main_terms = []
    for c in range(N):
        v = VALUES[word[c]]
        lm_c = 2 if c in dl_cols else 1
        main_terms.append(v)
        if lm_c > 1:
            main_terms.append(v * (lm_c - 1) * placed[c])
    WM = 3 ** len(tw_placed)

    total = m.NewIntVar(0, 3000, 'total')
    if fixed_blank_loss is not None:
        # pinned configuration: the forced-blank loss among fixed scored
        # tiles is a known constant (exact, not optimistic)
        n_forced, loss = fixed_blank_loss
        m.Add(total == WM * sum(main_terms) + sum(cross_scores)
              + 50 * bingo - loss)
    else:
        m.Add(total == WM * sum(main_terms) + sum(cross_scores)
              + 50 * bingo
              - sum(VALUES[ch] * pen[ch] for ch in LETTERS))
    if min_score is not None:
        m.Add(total >= min_score)
    if known_upper is not None:
        # a previously proven upper bound for this geometry (stage B);
        # adding it only prunes the search
        m.Add(total <= known_upper)
    m.Maximize(total)

    # ---- hints (or hard fixing, for model validation) ----
    if hint_grid is not None:
        for r in range(1, N):
            for c in range(N):
                t = hint_grid.get((r, c))
                v = code(t.letter) if t else 0
                if fix_hint:
                    m.Add(g[(r, c)] == v)
                else:
                    m.AddHint(g[(r, c)], v)
        if hint_placed is not None:
            for c in range(N):
                v = 1 if c in hint_placed else 0
                if fix_hint:
                    m.Add(placed[c] == v)
                else:
                    m.AddHint(placed[c], v)

    if fix_cells:
        # Pin individual cells: {(row, col): 'A' or None}, None meaning
        # empty. Used to split one hard instance into a partition of
        # easier ones -- every legal board assigns *something* to these
        # cells, so pinning each possibility in turn is exhaustive.
        for (r, c), ch in fix_cells.items():
            m.Add(g[(r, c)] == (0 if ch is None else code(ch)))

    if build_only:
        # Hand the finished model back instead of solving it. Building it
        # is 0.92s of a 1.70s solve, and a decomposition re-solves the
        # *same* model once per branch with only a pinned cell differing,
        # so the build is pure repeated waste. TableauSession keeps one
        # model and varies the pinned cells through CP-SAT assumptions.
        return m, g

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 12
    solver.parameters.log_search_progress = verbose
    if verbose:
        solver.log_callback = lambda s: log('  ' + s)
    status = solver.Solve(m)
    name = solver.StatusName(status)
    sol = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        rows = [word]
        for r in range(1, N):
            rows.append(''.join(
                '.' if solver.Value(g[(r, c)]) == 0
                else chr(solver.Value(g[(r, c)]) + 64) for c in range(N)))
        sol = {'value': solver.Value(total),
               'placed': [c for c in range(N) if solver.Value(placed[c])],
               'board_rows': rows,
               'over': {ch: solver.Value(over[ch]) for ch in LETTERS
                        if solver.Value(over[ch])}}
    return name, (solver.ObjectiveValue()
                  if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
                  else None), solver.BestObjectiveBound(), sol


def main():
    import argparse
    import time
    from . import known
    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--time-limit', type=float, default=3600.0)
    ap.add_argument('--min-score', type=int, default=None)
    ap.add_argument('--no-hint', action='store_true')
    ap.add_argument('--out', default='results/tableau.json')
    args = ap.parse_args()
    lex = load()
    hint = None if args.no_hint else known.pre_board()
    t0 = time.time()
    name, val, bound, sol = solve_tableau(
        lex, 'OXYPHENBUTAZONE', 0, time_limit=args.time_limit,
        hint_grid=hint, hint_placed={0, 1, 3, 6, 7, 11, 14},
        min_score=args.min_score, known_upper=1794)
    out = {'status': name, 'best_value': val, 'upper_bound': bound,
           'seconds': time.time() - t0, 'solution': sol}
    print(json.dumps(out, indent=1))
    import os
    os.makedirs('results', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
