"""Stage B: tight upper bounds for surviving candidates via CP-SAT.

For each candidate (word, edge row) from the stage-A enumeration, solve

    max  WM * MainSum + sum of cross-word scores + 50*bingo - blank losses

jointly over the placed set S (1 <= |S| <= 7) and one concrete cross word
per placed cell, subject to constraints that every REAL play of this
geometry must satisfy:

  * cross-word geometry: on row 0 the hook tile is the FIRST letter of
    the cross word, on row 14 the LAST (nothing fits beyond the edge);
  * hook validity: the cross word minus its hook tile is a maximal
    vertical run of the pre-move position, so for cross words of length
    >= 3 the remainder must itself be a lexicon word (for length 2 the
    remainder is a single tile, which may legally be supported
    sideways by other pre-move tiles);
  * pre-existing-run validity: the non-placed cells of the edge row form
    maximal horizontal runs of the pre-move position, so every such run
    of length >= 2 must be a lexicon word;
  * pre-existing-run support: every such run (including singletons) is
    connected to the rest of the pre-move board only through tiles in
    the next row inward, so each run forces at least one extra board
    tile (counted against the 100-tile bag);
  * adjacent cross words: if columns c and c+1 both receive cross words,
    their letters in the next row inward are horizontally adjacent in
    the final position, so that ordered letter pair must occur adjacently
    inside at least one lexicon word;
  * global tile inventory: for every letter, (main word tiles) + (all
    cross word rest tiles) <= bag count + b_x, where b_x are blank
    allowances, sum b_x <= 2, and each blank subtracts only its face
    value from the score (the minimum possible loss, keeping this an
    upper bound);
  * total tiles on the final board <= 100.

Everything else (full validity of deeper rows, connectivity to the
center, reachability, exact blank placement loss) remains relaxed, hence
the optimum of this model is a rigorous upper bound on the score of any
legal play realizing (word, edge row).

The word multiplier is handled exactly by solving once per subset of the
three triple-word cells (WM in {1, 3, 9, 27}).
"""

from __future__ import annotations

import json
from collections import Counter

from ortools.sat.python import cp_model

from .rules import DISTRIBUTION, N, VALUES
from .bounds import word_playable

LETTERS = [ch for ch in DISTRIBUTION if ch != '?']


def cross_options(lexicon, letter: str, row: int):
    """Cross-word options for a hook tile `letter` at an edge row,
    honouring hook validity (remainder must be a word when len >= 3).

    Returns list of (raw_rest, rest_len, rest_counts_dict, example_word,
    inward_letter) where inward_letter is the cross word's letter in the
    next row inward (row 1 resp. row 13).

    Keyed by the *ordered* remainder, i.e. one option per valid cross
    word.  An earlier version keyed by the remainder's letter multiset,
    which was unsound: callers inspect the retained representative's
    ordered letters (`rest_letter_at_depth` for the adjacency
    constraints, `o[4]` for the row-1 inward letter), so collapsing
    anagrams silently deleted legal cross-word choices from the
    relaxation.  YARE and YEAR are both valid Y-hooks with remainder
    multiset {A,E,R} but inward letters A and E; dropping either breaks
    the "every legal play satisfies these constraints" property that
    Lemma 1 depends on.  Hook validity already prunes anagrams heavily,
    so keying on the full remainder costs only ~3% more options.

    Sorted by (-raw_rest, rest), not -raw_rest alone: `lexicon` is a
    frozenset, so ties broken by iteration order would make the emitted
    model depend on PYTHONHASHSEED."""
    assert row in (0, N - 1)
    seen = {}
    for w in lexicon:
        m = len(w)
        if m < 2 or m > N or not word_playable(w):
            continue
        hook = w[0] if row == 0 else w[-1]
        if hook != letter:
            continue
        rest = w[1:] if row == 0 else w[:-1]
        if len(rest) >= 2 and rest not in lexicon:
            continue  # remainder would be an invalid pre-move run
        inward = rest[0] if row == 0 else rest[-1]
        counts = Counter(rest)
        raw_rest = sum(VALUES[ch] for ch in rest)
        seen[rest] = (raw_rest, m - 1, dict(counts), w, inward)
    return [v for _, v in sorted(seen.items(),
                                 key=lambda kv: (-kv[1][0], kv[0]))]


def adjacent_pairs(lexicon) -> set[tuple[str, str]]:
    """All ordered letter pairs that occur adjacently in some lexicon word."""
    pairs = set()
    for w in lexicon:
        for a, b in zip(w, w[1:]):
            pairs.add((a, b))
    return pairs


def second_letters(lexicon, letter: str, row: int) -> set[str]:
    """Letters that can sit in the next row inward under a pre-existing edge
    tile `letter`: second letters of words starting with `letter` (row 0)
    resp. penultimate letters of words ending with `letter` (row 14)."""
    out = set()
    for w in lexicon:
        if len(w) < 2 or len(w) > N:
            continue
        if row == 0 and w[0] == letter:
            out.add(w[1])
        elif row == N - 1 and w[-1] == letter:
            out.add(w[-2])
    return out


def build_line_dawg(lexicon):
    """Minimal DFA accepting exactly the 15-column line contents whose
    maximal nonempty runs are each either a single tile or a lexicon word.

    Symbols: 0 = empty, 1..26 = A..Z.  Returns (transitions, start, finals).
    """
    # trie including all 26 single letters as words (a single tile is a
    # legal maximal run when supported perpendicularly)
    trie = {}
    END = '$'
    # sorted: `lexicon` is a frozenset, and trie insertion order decides
    # the order `intern` allocates state ids.  The minimal DAWG is
    # canonical up to renaming, so an unsorted build stays *correct* but
    # emits a differently-numbered automaton — and hence a different
    # CP-SAT model — on every PYTHONHASHSEED, which makes
    # timeout-derived bounds irreproducible.
    words = sorted(w for w in lexicon if 2 <= len(w) <= N)
    words += [chr(ord('A') + i) for i in range(26)]
    for w in words:
        t = trie
        for ch in w:
            t = t.setdefault(ch, {})
        t[END] = True

    # bottom-up hash-consing -> minimal DAWG
    memo = {}
    states = []  # states[i] = (is_end, ((sym, child_id), ...))

    def intern(node):
        end = END in node
        items = tuple(sorted((ch, intern(sub)) for ch, sub in node.items()
                             if ch != END))
        key = (end, items)
        if key not in memo:
            memo[key] = len(states)
            states.append(key)
        return memo[key]

    import sys
    sys.setrecursionlimit(100)
    root = intern(trie)

    transitions = []
    finals = set()
    for sid, (end, items) in enumerate(states):
        for ch, child in items:
            transitions.append((sid, ord(ch) - ord('A') + 1, child))
        if end:
            transitions.append((sid, 0, root))
            finals.add(sid)
    transitions.append((root, 0, root))
    finals.add(root)
    return transitions, root, sorted(finals)


def tighten_candidate(lexicon, word: str, row: int, *, time_limit=300.0,
                      opts_cache=None, adj_pairs=None, log=print,
                      row1_exact=False, dawg=None, mask_filter=None,
                      pairwise_all_rows=False, enumerate_above=None,
                      enumerate_cb=None, fix_placed=None, max_placed=None,
                      blank_penalty=False):
    """Return ((bound, detail), per_mask) for a full-row edge play.

    row1_exact adds the exact model of the next row inward: every tile in
    it is either a cross-word letter (fixed by the chosen option), a
    support tile under a pre-existing run (a letter that can follow /
    precede the edge letter in some word, consuming inventory), or absent;
    and the row's maximal runs must be lexicon words (via a DAWG
    automaton).  Supports feed the tile-count and inventory constraints.
    """
    assert len(word) == N and row in (0, N - 1)
    tw_cols = [0, 7, 14]
    dl_cols = [3, 11]
    vals = [VALUES[ch] for ch in word]
    raw = sum(vals)
    main_counts = Counter(word)

    if opts_cache is None:
        opts_cache = {}
    for ch in set(word):
        if (ch, row) not in opts_cache:
            opts_cache[(ch, row)] = cross_options(lexicon, ch, row)
    if adj_pairs is None:
        adj_pairs = adjacent_pairs(lexicon)

    # intervals [a, b] of pre-existing cells that would be invalid words
    bad_intervals = [(a, b)
                     for a in range(N) for b in range(a + 1, N)
                     if word[a:b + 1] not in lexicon]

    if row1_exact:
        if dawg is None:
            dawg = build_line_dawg(lexicon)
        second = {ch: second_letters(lexicon, ch, row) for ch in set(word)}

    def rest_letter_at_depth(example, depth):
        """Letter of this cross word `depth` rows inward (depth >= 1)."""
        rest = example[1:] if row == 0 else example[:-1]
        if depth > len(rest):
            return None
        return rest[depth - 1] if row == 0 else rest[-depth]

    best = (float('-inf'), None)
    per_mask = {}
    for t_mask in range(8):
        if mask_filter is not None and t_mask not in mask_filter:
            continue
        T = [c for j, c in enumerate(tw_cols) if t_mask >> j & 1]
        WM = 3 ** len(T)

        model = cp_model.CpModel()
        placed = [model.NewBoolVar(f'p{c}') for c in range(N)]
        for c in tw_cols:
            model.Add(placed[c] == (1 if c in T else 0))
        if fix_placed is not None:
            for c in range(N):
                model.Add(placed[c] == (1 if c in fix_placed else 0))
        model.Add(sum(placed) <= 7)
        if max_placed is not None:
            model.Add(sum(placed) <= max_placed)
        model.Add(sum(placed) >= 1)
        bingo = model.NewBoolVar('bingo')
        model.Add(sum(placed) >= 7 * bingo)
        model.Add(sum(placed) <= 6 + bingo)

        # forbid invalid pre-existing runs
        for a, b in bad_intervals:
            clause = [placed[i] for i in range(a, b + 1)]
            if a > 0:
                clause.append(placed[a - 1].Not())
            if b < N - 1:
                clause.append(placed[b + 1].Not())
            model.AddBoolOr(clause)

        # cross-word option choice per column
        x = {}
        opt_lists = {}
        has_cross = {}
        for c in range(N):
            opts = opts_cache[(word[c], row)]
            opt_lists[c] = opts
            cvars = []
            for oi in range(len(opts)):
                v = model.NewBoolVar(f'x{c}_{oi}')
                model.Add(v <= placed[c])
                x[(c, oi)] = v
                cvars.append(v)
            model.AddAtMostOne(cvars)
            hc = model.NewBoolVar(f'hc{c}')
            model.Add(sum(cvars) == hc)
            has_cross[c] = hc

        # adjacent cross words: at every shared depth, the horizontally
        # adjacent letter pair must occur adjacently in some lexicon word.
        # Grouped by (column, depth, letter) to keep the encoding small.
        max_depth = N - 1 if pairwise_all_rows else 1
        zvar = [dict() for _ in range(N)]  # zvar[c][(depth, letter)] -> bool
        for c in range(N):
            groups = {}
            for oi, o in enumerate(opt_lists[c]):
                for d in range(1, min(o[1], max_depth) + 1):
                    ch = rest_letter_at_depth(o[3], d)
                    groups.setdefault((d, ch), []).append(x[(c, oi)])
            for (d, ch), vs in groups.items():
                zv = model.NewBoolVar(f'z{c}_{d}_{ch}')
                model.AddMaxEquality(zv, vs)
                zvar[c][(d, ch)] = zv
        for c in range(N - 1):
            for (d, la), zl in zvar[c].items():
                for (d2, lb), zr in zvar[c + 1].items():
                    if d == d2 and (la, lb) not in adj_pairs:
                        model.AddBoolOr([zl.Not(), zr.Not()])

        # ---- optional exact model of the next row inward ----
        sup = None
        if row1_exact:
            transitions, start, finals = dawg

            def code(ch):
                return ord(ch) - ord('A') + 1

            e = [model.NewIntVar(0, 26, f'e{c}') for c in range(N)]
            nz, sup, eq = [], [], {}
            for c in range(N):
                # sorted, not raw set iteration: variable creation order
                # would otherwise depend on PYTHONHASHSEED
                inw = sorted({o[4] for o in opt_lists[c]})
                sec = sorted(second[word[c]])
                allowed = sorted({0} | {code(a) for a in set(inw) | set(sec)})
                model.AddAllowedAssignments([e[c]],
                                            [(v,) for v in allowed])
                # cross columns: e fixed to the chosen option's inward letter
                for a in inw:
                    zv = zvar[c].get((1, a))
                    if zv is not None:
                        model.Add(e[c] == code(a)).OnlyEnforceIf(zv)
                model.Add(e[c] == 0).OnlyEnforceIf(
                    [placed[c], has_cross[c].Not()])
                # support columns: only continuation letters
                for v_ in allowed:
                    if v_ != 0 and chr(v_ + 64) not in sec:
                        model.Add(e[c] != v_).OnlyEnforceIf(placed[c].Not())
                nzc = model.NewBoolVar(f'nz{c}')
                model.Add(e[c] != 0).OnlyEnforceIf(nzc)
                model.Add(e[c] == 0).OnlyEnforceIf(nzc.Not())
                nz.append(nzc)
                sc = model.NewBoolVar(f'sup{c}')
                model.AddBoolAnd([nzc, has_cross[c].Not()]).OnlyEnforceIf(sc)
                model.AddBoolOr([nzc.Not(), has_cross[c]]
                                ).OnlyEnforceIf(sc.Not())
                sup.append(sc)
                # per-letter support indicators for inventory:
                # eq[(c,a)] <-> (e_c == a) and sup_c
                for a in sec:
                    eqv = model.NewBoolVar(f'q{c}{a}')
                    model.Add(e[c] == code(a)).OnlyEnforceIf(eqv)
                    model.Add(e[c] != code(a)).OnlyEnforceIf(eqv.Not())
                    ind = model.NewBoolVar(f'i{c}{a}')
                    model.AddBoolAnd([eqv, sc]).OnlyEnforceIf(ind)
                    model.AddBoolOr([eqv.Not(), sc.Not()]
                                    ).OnlyEnforceIf(ind.Not())
                    eq[(c, a)] = ind
            # row-1 maximal runs must be lexicon words (or singles)
            model.AddAutomaton(e, start, finals, transitions)
            # every pre-existing run needs at least one support tile below
            for a in range(N):
                for bcol in range(a, N):
                    if a < bcol and word[a:bcol + 1] not in lexicon:
                        continue  # already forbidden
                    clause = [placed[i] for i in range(a, bcol + 1)]
                    clause += [nz[i] for i in range(a, bcol + 1)]
                    if a > 0:
                        clause.append(placed[a - 1].Not())
                    if bcol < N - 1:
                        clause.append(placed[bcol + 1].Not())
                    model.AddBoolOr(clause)
            # supports whose two-letter combination is not itself a word
            # must extend at least one row deeper
            deep = []
            for c in range(N):
                dc_terms = []
                for a in second[word[c]]:
                    two = word[c] + a if row == 0 else a + word[c]
                    if two not in lexicon:
                        dc_terms.append(eq[(c, a)])
                if dc_terms:
                    dc = model.NewBoolVar(f'deep{c}')
                    model.AddMaxEquality(dc, dc_terms)
                    deep.append(dc)

        # blanks: bs are forced blanks among *scored* tiles (each loses at
        # least its face value); bu cover unscored support tiles for free
        bs = {ch: model.NewIntVar(0, 2, f'bs{ch}') for ch in LETTERS}
        bu = {ch: model.NewIntVar(0, 2, f'bu{ch}') for ch in LETTERS}
        model.Add(sum(bs.values()) + sum(bu.values()) <= 2)

        for ch in LETTERS:
            scored = [main_counts.get(ch, 0)]
            for (c, oi), v in x.items():
                n = opt_lists[c][oi][2].get(ch, 0)
                if n:
                    scored.append(n * v)
            unscored = []
            if row1_exact:
                unscored = [eq[k] for k in eq if k[1] == ch]
            model.Add(sum(scored) <= DISTRIBUTION[ch] + bs[ch])
            model.Add(sum(scored) + sum(unscored)
                      <= DISTRIBUTION[ch] + bs[ch] + bu[ch])

        # board size: main word + cross rests + supports (or one support
        # tile per pre-existing run when row 1 is not modelled exactly)
        rest_tiles = sum(opt_lists[c][oi][1] * v for (c, oi), v in x.items())
        if row1_exact:
            model.Add(rest_tiles + sum(sup) + sum(deep) <= 100 - N)
        else:
            run_starts = []
            for c in range(N):
                rs = model.NewBoolVar(f'rs{c}')
                if c == 0:
                    model.AddBoolAnd([placed[0].Not()]).OnlyEnforceIf(rs)
                    model.AddBoolOr([placed[0]]).OnlyEnforceIf(rs.Not())
                else:
                    model.AddBoolAnd([placed[c].Not(), placed[c - 1]]
                                     ).OnlyEnforceIf(rs)
                    model.AddBoolOr([placed[c], placed[c - 1].Not()]
                                    ).OnlyEnforceIf(rs.Not())
                run_starts.append(rs)
            model.Add(rest_tiles + sum(run_starts) <= 100 - N)

        # objective
        terms = [50 * bingo]
        const = WM * raw
        for c in dl_cols:
            terms.append(WM * vals[c] * placed[c])
        for (c, oi), v in x.items():
            wm_c = 3 if c in T else 1
            lm_c = 2 if c in dl_cols else 1
            score = wm_c * (vals[c] * lm_c + opt_lists[c][oi][0])
            terms.append(score * v)
        for ch in LETTERS:
            terms.append(-VALUES[ch] * bs[ch])

        if blank_penalty:
            # The charge above is face value, which under-states what a
            # blank really forfeits.  A blank standing in for `ch` costs:
            #   * face value, if some copy of `ch` sits in a cross-word
            #     remainder in a NON-word-multiplier column;
            #   * three times face, if every copy sits in a TW column;
            #   * value x letter-mult x 27, if it must go in the main word.
            # So `2 * VALUES[ch]` extra per blank is a valid *lower* bound
            # on the shortfall whenever no cheap cell exists, and zero
            # otherwise.  Subtracting a lower bound on a loss keeps the
            # objective an upper bound on the true score (Lemma 1).
            #
            # Deliberately conservative in two places: it charges 2x even
            # when the blank would land in the main word and cost ~27x, and
            # it charges nothing when a single cheap cell exists even if a
            # second blank for the same letter must go somewhere dearer.
            # Both under-charge, so both stay sound.
            for ch in LETTERS:
                cheap_lits = [x[(c, oi)]
                              for c in range(N) if c not in T
                              for oi in range(len(opt_lists.get(c, [])))
                              if opt_lists[c][oi][2].get(ch, 0) > 0]
                gap = model.NewIntVar(0, 4 * VALUES[ch], f'blankgap_{ch}')
                if cheap_lits:
                    cheap = model.NewBoolVar(f'cheapcell_{ch}')
                    model.AddMaxEquality(cheap, cheap_lits)
                    # bs[ch] <= 2, so 4*V dominates 2*V*bs[ch]
                    model.Add(gap >= 2 * VALUES[ch] * bs[ch]
                              - 4 * VALUES[ch] * cheap)
                else:
                    model.Add(gap >= 2 * VALUES[ch] * bs[ch])
                terms.append(-gap)

        if enumerate_above is not None:
            # feasibility enumeration mode: hand the model to the caller
            total_var = model.NewIntVar(0, 3000, 'total')
            model.Add(total_var == sum(terms) + const)
            model.Add(total_var >= enumerate_above + 1)
            return enumerate_cb(model,
                                (placed, x, opt_lists, has_cross, total_var))

        model.Maximize(sum(terms) + const)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        if status == cp_model.INFEASIBLE:
            per_mask[t_mask] = float('-inf')
            continue
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f'solver status {status} for T={T}')
        if status != cp_model.OPTIMAL:
            log(f'  WARNING: T={T} hit time limit; using upper bound')
            val = solver.BestObjectiveBound()
            proved = False
        else:
            val = solver.ObjectiveValue()
            proved = True
        per_mask[t_mask] = val
        if val > best[0]:
            chosen = {}
            for (c, oi), v in x.items():
                if solver.Value(v):
                    chosen[c] = opt_lists[c][oi][3]
            placed_cols = [c for c in range(N) if solver.Value(placed[c])]
            blanks = {ch: (solver.Value(bs[ch]), solver.Value(bu[ch]))
                      for ch in LETTERS
                      if solver.Value(bs[ch]) or solver.Value(bu[ch])}
            detail = {'T': T, 'WM': WM, 'placed': placed_cols,
                      'crosses': chosen, 'blanks(bs,bu)': blanks,
                      'bingo': bool(solver.Value(bingo)),
                      'proved_optimal': proved}
            if row1_exact:
                detail['row1'] = ''.join(
                    '.' if solver.Value(e[c]) == 0
                    else chr(solver.Value(e[c]) + 64) for c in range(N))
            best = (val, detail)
    return best, per_mask


def main():
    import argparse
    import time

    from .lexicon import load
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidates', default='results/candidates.json')
    ap.add_argument('--out', default='results/tight_bounds.json')
    ap.add_argument('--time-limit', type=float, default=300.0)
    ap.add_argument('--threshold', type=int, default=1786)
    ap.add_argument('--max-placed', type=int, default=None,
                    help='cap |S|.  --max-placed 6 forces the bingo '
                         'variable to 0 and produces the bound behind '
                         'Theorem 3 (results/bound_six_tiles.json).')
    ap.add_argument('--word', default=None,
                    help='comma-separated words to restrict to, e.g. '
                         'OXYPHENBUTAZONE')
    ap.add_argument('--six-tiles', action='store_true',
                    help="regenerate results/bound_six_tiles.json: the "
                         "|S| <= 6 optimum for OXYPHENBUTAZONE on both "
                         "edge rows, which is what forces Theorem 3's "
                         "'exactly 7 tiles'.  Writes that file's own "
                         "schema rather than the --out list format.")
    args = ap.parse_args()
    from .provenance import write as write_provenance
    prov = write_provenance()
    print(f"provenance: commit {prov['git_commit']} "
          f"ortools {prov['ortools']} seed {prov['pythonhashseed']} "
          f"lexicon {prov['lexicon']['sha256'][:12]}", flush=True)
    lex = load()

    if args.six_tiles:
        # Theorem 3: with |S| <= 6 the bingo variable is forced to 0.  Both
        # optima must come out below 1786 for "places exactly 7 tiles".
        word, out = 'OXYPHENBUTAZONE', 'results/bound_six_tiles.json'
        opts_cache, adj = {}, adjacent_pairs(lex)
        payload = {}
        for r in (0, N - 1):
            t1 = time.time()
            (b, _), pm = tighten_candidate(
                lex, word, r, opts_cache=opts_cache, adj_pairs=adj,
                time_limit=args.time_limit, max_placed=6)
            payload[f'row{r}_max6'] = b
            payload[f'row{r}_max6_per_mask'] = pm
            print(f'{word} row={r} |S|<=6: {b:.0f}  '
                  f'({time.time() - t1:.1f}s)', flush=True)
        with open(out, 'w') as f:
            json.dump(payload, f, indent=1, default=str)
        print(f'-> {out}')
        return

    cands = json.load(open(args.candidates))['candidates']
    if args.word:
        want = {w.upper() for w in args.word.split(',')}
        cands = [c for c in cands if c['word'] in want]
        assert cands, f'no candidate matches {sorted(want)}'
    opts_cache = {}
    adj = adjacent_pairs(lex)
    dawg = None
    results = []
    t0 = time.time()
    for cand in cands:
        w, r = cand['word'], cand['row']
        t1 = time.time()
        (bound, detail), per_mask = tighten_candidate(
            lex, w, r, opts_cache=opts_cache, adj_pairs=adj,
            time_limit=args.time_limit, max_placed=args.max_placed)
        entry = {'word': w, 'row': r, 'relaxed_max': cand['relaxed_max'],
                 'tight_bound': bound, 'per_mask': per_mask,
                 'detail': detail}
        print(f"{w} row={r}: relaxed {cand['relaxed_max']} -> tight "
              f"{bound:.0f}  ({time.time()-t1:.1f}s)", flush=True)
        if bound > args.threshold:
            live_masks = [m for m, v in per_mask.items()
                          if v > args.threshold]
            if dawg is None:
                print("  building line DAWG...", flush=True)
                dawg = build_line_dawg(lex)
            t2 = time.time()
            (b2, d2), pm2 = tighten_candidate(
                lex, w, r, opts_cache=opts_cache, adj_pairs=adj,
                time_limit=args.time_limit * 4, row1_exact=True,
                dawg=dawg, mask_filter=live_masks, pairwise_all_rows=True,
                max_placed=args.max_placed)
            print(f"  row1-exact: {bound:.0f} -> {b2:.0f} "
                  f"({time.time()-t2:.1f}s)", flush=True)
            entry['row1_exact_bound'] = b2
            entry['row1_exact_detail'] = d2
            entry['row1_exact_per_mask'] = pm2
        results.append(entry)
        with open(args.out, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    print(f"done in {time.time()-t0:.0f}s -> {args.out}")


if __name__ == '__main__':
    main()
