"""Read the progress of a running (or dead) enumeration off disk.

Every configuration is appended to a checkpoint and flushed as it is
found, together with the seconds its solve took, so the checkpoint
directory is already a complete record of what has happened. This reads
it. It touches nothing, needs no cooperation from the running job, and
works equally on a finished run, a killed one, and one still going.

Deliberately reports **observed quantities only** -- configurations found,
seconds per solve, time since the last one. It does not project a finish
time. The per-solve cost varies by more than an order of magnitude between
patterns and the configuration count per pattern is not known until the
pattern finishes, so any ETA would be a guess wearing a number's clothing.
What it does show is enough to judge for yourself: the rate so far, the
slowest solve yet seen, and how long the current one has been running.

The last column is the one to watch. `since last` is how long the current
solve has been going. Compare it to `slowest`: a value well past that is
either an unusually hard solve or the closing infeasibility proof, which
is normally the most expensive solve of a pattern.

Usage:
    python -m scrabble_max.status
    python -m scrabble_max.status --watch 30
    python -m scrabble_max.status --dir results/enum_cells --json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
import time

# Configuration counts from the archived (pre-cross_options-fix)
# enumerations, shown only as a rough denominator. They are what the
# re-run is re-deriving, so a pattern legitimately finishing on a
# different number is not an error.
ARCHIVED = {
    '00010203071114': 396, '00010304071114': 584, '00010307081114': 9,
    '00010307111314': 21, '00020304071114': 26, '00020307081114': 27,
    '00020307091114': 824, '00020307111314': 16,
}


def _fmt(seconds):
    if seconds is None:
        return '-'
    seconds = int(seconds)
    if seconds < 90:
        return f'{seconds}s'
    if seconds < 5400:
        return f'{seconds // 60}m{seconds % 60:02d}'
    return f'{seconds // 3600}h{(seconds % 3600) // 60:02d}'


def read_one(path):
    """Parse one checkpoint. Tolerates a torn final line -- the file may
    be being appended to as we read it."""
    n, timings, complete, corrupt, scales = 0, [], False, False, set()
    started = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                corrupt = True          # almost certainly a live final line
                continue
            scales.add(e.get('blank_penalty'))
            if 'started' in e:
                # a work marker, not a solve: it carries no duration, and
                # counting its 0.0 would drag the median toward zero
                started = e['started']
                continue
            timings.append(e.get('seconds', 0.0))
            if e.get('complete'):
                complete = True
            elif 'config' in e:
                n += 1
    return {'path': path, 'configs': n, 'timings': timings, 'started': started,
            'complete': complete, 'corrupt': corrupt, 'scales': scales}


def _pattern_of(tag):
    """Cell files are `<pattern>_p03c007`; plain ones are just the pattern."""
    return tag.split('_')[0]


def collect(ckpt_dir):
    rows = []
    now = time.time()
    for path in sorted(glob.glob(os.path.join(ckpt_dir, '*.jsonl'))):
        r = read_one(path)
        tag = os.path.basename(path)[:-len('.jsonl')]
        r['tag'] = tag
        r['pattern'] = _pattern_of(tag)
        r['idle'] = now - os.path.getmtime(path)
        r['spent'] = sum(r['timings'])
        r['slowest'] = max(r['timings']) if r['timings'] else None
        r['median'] = statistics.median(r['timings']) if r['timings'] else None
        rows.append(r)
    return rows


def render(rows, by_pattern=False):
    if not rows:
        return ('no checkpoints yet -- either the run has not started or it '
                'is writing somewhere else')
    if by_pattern:
        merged = {}
        for r in rows:
            m = merged.setdefault(r['pattern'], {
                'tag': r['pattern'], 'configs': 0, 'timings': [],
                'cells': 0, 'done': 0, 'idle': r['idle']})
            m['configs'] += r['configs']
            m['timings'] += r['timings']
            m['cells'] += 1
            m['done'] += bool(r['complete'])
            m['idle'] = min(m['idle'], r['idle'])
        rows = []
        for m in merged.values():
            rows.append({**m,
                         'complete': m['done'] == m['cells'],
                         'spent': sum(m['timings']),
                         'slowest': max(m['timings']) if m['timings'] else None,
                         'median': (statistics.median(m['timings'])
                                    if m['timings'] else None),
                         'corrupt': False, 'scales': set(),
                         'pattern': m['tag']})
        rows.sort(key=lambda r: r['tag'])

    w = max(len(r['tag']) for r in rows)
    head = (f'{"checkpoint".ljust(w)}  configs  state      cpu-time  '
            f'median  slowest  since last')
    out = [head, '-' * len(head)]
    tot_cfg = tot_spent = 0
    for r in rows:
        exp = ARCHIVED.get(r['pattern'])
        cfg = f'{r["configs"]}'
        if exp is not None and not r['complete']:
            cfg = f'{r["configs"]}/~{exp}'
        if 'cells' in r:
            state = ('done' if r['complete']
                     else f'{r["done"]}/{r["cells"]} cells')
        elif r['complete']:
            state = 'done'
        elif r['configs'] == 0:
            # started, nothing found yet. Distinguished from "running"
            # because it is the state that used to be invisible: a cell
            # can spend its whole life here and end with a bare
            # infeasibility proof, having never found anything.
            state = 'searching'
        else:
            state = 'running'
        out.append(
            f'{r["tag"].ljust(w)}  {cfg:>7}  {state:<9}  '
            f'{_fmt(r["spent"]):>8}  {_fmt(r["median"]):>6}  '
            f'{_fmt(r["slowest"]):>7}  '
            f'{_fmt(r["idle"]) if not r["complete"] else "-":>10}')
        tot_cfg += r['configs']
        tot_spent += r['spent']

    done = sum(1 for r in rows if r['complete'])
    out.append('-' * len(head))
    out.append(f'{done}/{len(rows)} finished, {tot_cfg} configurations, '
               f'{_fmt(tot_spent)} of solver time')
    # A cell that has not completed a solve yet has no yardstick of its
    # own, so fall back to how long solves are taking everywhere else.
    # Without this a cell that never finds anything is never flagged --
    # precisely the case worth flagging.
    all_solves = [t for r in rows for t in r.get('timings', [])]
    fallback = 3 * statistics.median(all_solves) if all_solves else None
    stale = []
    for r in rows:
        if r['complete']:
            continue
        bar = 3 * r['slowest'] if r['slowest'] else fallback
        if bar and r['idle'] > bar:
            stale.append(r)
    if stale:
        out.append('')
        out.append('running much longer than any solve so far -- a hard '
                   'solve, the closing proof, or stuck:')
        for r in stale:
            yard = (f'slowest so far {_fmt(r["slowest"])}' if r['slowest']
                    else 'no solve finished yet')
            out.append(f'  {r["tag"]}: {_fmt(r["idle"])} since last write, '
                       f'{yard}')
    mixed = [r for r in rows if len(r.get('scales', set()) - {None}) > 1]
    if mixed:
        out.append('')
        out.append(f'MIXED CHARGING SCALES in {[r["tag"] for r in mixed]} -- '
                   f'these lists are not trustworthy')
    return '\n'.join(out)


def collect_checks(checks_dir, configs_file, cache=None):
    """Refutation progress, per pattern.

    `check_configs` rewrites its whole output file after every
    configuration, so a read can easily land mid-write and raise. That is
    normal, not an error: the previous good value is reused and the row is
    marked `(writing)`. Reporting 0 for a file that is simply being
    rewritten would look exactly like a stalled pattern.
    """
    cache = {} if cache is None else cache
    expected = {}
    if os.path.exists(configs_file):
        try:
            d = json.load(open(configs_file))
            for p in d['patterns']:
                tag = ''.join(f'{c:02d}' for c in p['placed'])
                expected[tag] = p['count']
        except (json.JSONDecodeError, KeyError):
            pass

    rows = []
    for tag, total in sorted(expected.items()):
        path = os.path.join(checks_dir, f'{tag}.json')
        writing = False
        if not os.path.exists(path):
            got, statuses, no_solve, over = 0, {}, 0, []
        else:
            try:
                data = json.load(open(path))
                cache[tag] = data
            except json.JSONDecodeError:
                data = cache.get(tag, [])
                writing = True
            got = len(data)
            statuses = {}
            no_solve = 0
            over = []
            for r in data:
                statuses[r.get('status')] = statuses.get(r.get('status'), 0) + 1
                if r.get('value') is None:
                    no_solve += 1
                elif r['value'] > 1786:
                    over.append(r)
        rows.append({'tag': tag, 'done': got, 'total': total,
                     'statuses': statuses, 'no_solve': no_solve,
                     'over': over, 'writing': writing,
                     'mtime': (os.path.getmtime(path)
                               if os.path.exists(path) else None)})
    return rows


def render_checks(rows):
    if not rows:
        return ('no enumeration results yet -- results/tier3_configs.json '
                'is missing, so there is nothing to refute')
    now = time.time()
    w = max(len(r['tag']) for r in rows)
    head = (f'{"pattern".ljust(w)}  decided       by ceiling  by solver  '
            f'not INFEASIBLE  since')
    out = [head, '-' * len(head)]
    d = t = ceil = solved = 0
    alarms, over_all = [], []
    for r in rows:
        bad = {k: v for k, v in r['statuses'].items() if k != 'INFEASIBLE'}
        if bad:
            alarms.append((r['tag'], bad))
        over_all += r['over']
        n_solved = r['done'] - r['no_solve']
        mark = ' (writing)' if r['writing'] else ''
        age = (_fmt(now - r['mtime']) if r['mtime'] and r['done'] < r['total']
               else '-')
        out.append(
            f'{r["tag"].ljust(w)}  {r["done"]:>4}/{r["total"]:<6}  '
            f'{r["no_solve"]:>10}  {n_solved:>9}  '
            f'{(sum(bad.values()) if bad else 0):>14}  {age:>5}{mark}')
        d += r['done']
        t += r['total']
        ceil += r['no_solve']
        solved += n_solved
    out.append('-' * len(head))
    pct = (100.0 * d / t) if t else 0.0
    out.append(f'{d}/{t} decided ({pct:.1f}%)  |  {ceil} by exact blank '
               f'ceiling with no solve, {solved} by tableau solve')
    if over_all:
        out.append('')
        out.append(f'*** {len(over_all)} CONFIGURATION(S) SCORE ABOVE 1786 '
                   f'-- this would beat the record ***')
        for r in over_all[:5]:
            out.append(f'    value={r["value"]} {r["config"]}')
    if alarms:
        out.append('')
        out.append('NOT INFEASIBLE -- these are undecided or realisable, and '
                   'the proof is not closed while any remain:')
        for tag, bad in alarms:
            out.append(f'    {tag}: {bad}')
    elif d == t and t:
        out.append('')
        out.append('every configuration INFEASIBLE: no legal play in these '
                   'geometries exceeds 1786')
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dir', default='results/enum_ckpt',
                    help='checkpoint directory (default: results/enum_ckpt)')
    ap.add_argument('--watch', type=float, metavar='SECONDS',
                    help='refresh every SECONDS until interrupted')
    ap.add_argument('--by-pattern', action='store_true',
                    help='merge partition cells into one row per pattern')
    ap.add_argument('--json', action='store_true',
                    help='machine-readable, for piping')
    ap.add_argument('--checks', action='store_true',
                    help='show the refutation phase instead of enumeration')
    ap.add_argument('--checks-dir', default='results/tier3_checks')
    ap.add_argument('--configs', default='results/tier3_configs.json')
    a = ap.parse_args()

    cache = {}
    while True:
        if a.checks:
            rows = collect_checks(a.checks_dir, a.configs, cache)
            if a.watch:
                print('\033[2J\033[H', end='')
                print(time.strftime('%H:%M:%S'), f'  {a.checks_dir}')
            print(json.dumps(rows, indent=1, default=str) if a.json
                  else render_checks(rows))
            if not a.watch:
                return
            try:
                time.sleep(a.watch)
                continue
            except KeyboardInterrupt:
                return
        rows = collect(a.dir)
        if a.json:
            print(json.dumps([{k: (sorted(x for x in v if x is not None)
                                   if isinstance(v, set) else v)
                               for k, v in r.items() if k != 'timings'}
                              for r in rows], indent=1))
        else:
            if a.watch:
                print('\033[2J\033[H', end='')
                print(time.strftime('%H:%M:%S'), f'  {a.dir}')
            print(render(rows, by_pattern=a.by_pattern))
        if not a.watch:
            return
        try:
            time.sleep(a.watch)
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    sys.exit(main())
