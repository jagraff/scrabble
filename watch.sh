#!/usr/bin/env bash
# Live view of a rerun.sh run: which stage, how far into it, and -- once
# tier 3 starts -- the enumeration and refutation as they fill in.
#
# Reads everything off disk, so it is safe to start, stop and restart at any
# time, and works just as well on a finished or abandoned run as on a live
# one. Nothing here writes to results/.
#
#   ./watch.sh          refresh every 20s until interrupted
#   ./watch.sh 5        refresh every 5s
#   ./watch.sh once     print one snapshot and exit (for piping)
set -u

cd "$(dirname "$0")"
PY=.venv/bin/python
LOG=results/rerun/rerun.log
CELLS=results/enum_cells
CHECKS=results/tier3_checks

INTERVAL="${1:-20}"
ONCE=0
[ "$INTERVAL" = "once" ] && { ONCE=1; INTERVAL=0; }

# The stages rerun.sh runs, in order, so a stage that has not started yet is
# distinguishable from one that has finished. Without the list, "absent from
# the log" and "done" look the same.
STAGES="tests-fast tests-slow stage-a stage-b six-tiles tier-2 sweep tier-3 reach racks directional manifest"

hr() { printf '%s\n' "----------------------------------------------------------------------"; }

snapshot() {
  if [ ! -f "$LOG" ]; then
    echo "no run found: $LOG does not exist."
    echo "start one with ./rerun.sh"
    return
  fi

  printf '%s   (refreshed %s)\n' "SCRABBLE PROOF RE-RUN" "$(date '+%H:%M:%S')"
  hr

  # --- stage timeline -------------------------------------------------
  local current="" done_n=0 total_n=0
  for s in $STAGES; do
    total_n=$((total_n + 1))
    if grep -q "^    $s ok in" "$LOG" 2>/dev/null; then
      printf '  [x] %-13s %s\n' "$s" \
        "$(grep "^    $s ok in" "$LOG" | tail -1 | sed 's/.*ok in //')"
      done_n=$((done_n + 1))
    elif grep -q "  $s\$" "$LOG" 2>/dev/null; then
      current="$s"
      local started
      started=$(grep "  $s\$" "$LOG" | tail -1 | awk '{print $2}')
      printf '  [>] %-13s running since %s\n' "$s" "$started"
    else
      printf '  [ ] %-13s\n' "$s"
    fi
  done
  if grep -q "^!!!" "$LOG" 2>/dev/null; then
    hr
    grep "^!!!" "$LOG" | tail -3
    return
  fi
  if grep -q "done in" "$LOG" 2>/dev/null; then
    hr
    grep "done in" "$LOG" | tail -1
  fi

  # --- tier 3: enumeration --------------------------------------------
  if [ -d "$CELLS" ] && [ -n "$(find "$CELLS" -name '*.jsonl' 2>/dev/null | head -1)" ]; then
    hr
    echo "ENUMERATION"
    $PY -m scrabble_max.status --dir "$CELLS" --by-pattern 2>/dev/null \
      | sed 's/^/  /'
  fi

  # --- tier 3: refutation ---------------------------------------------
  #
  # Only this run's verdicts. The previous run's files are still on disk
  # until the refutation phase overwrites them, and showing them next to a
  # live enumeration reads as "1322/1322 decided" for work that has not
  # started -- the same cross-run arithmetic the enumeration watcher had to
  # be fixed for. Freshness is decided against stage-a.out, which rerun.sh
  # writes as its first act.
  if [ -d "$CHECKS" ] && [ -n "$(ls "$CHECKS"/*.json 2>/dev/null)" ]; then
    hr
    local marker=results/rerun/stage-a.out fresh=""
    if [ -f "$marker" ]; then
      fresh=$(find "$CHECKS" -name '*.json' -newer "$marker" 2>/dev/null \
              | head -1)
    else
      fresh="unknown"
    fi
    if [ -n "$fresh" ]; then
      echo "REFUTATION"
      $PY -m scrabble_max.status --checks --checks-dir "$CHECKS" 2>/dev/null \
        | sed 's/^/  /'
    else
      echo "REFUTATION  not started by this run"
      echo "  ($(ls "$CHECKS"/*.json 2>/dev/null | wc -l | tr -d ' ') verdict"\
           "file(s) on disk belong to the run being replaced, so they are"
      echo "   not shown -- they would report work this run has not done)"
    fi
  fi

  # --- the five that the stale checkpoint hid --------------------------
  # The whole point of this re-run. Pattern (0,1,3,7,11,13,14) was recorded
  # as 0 configurations because a checkpoint left over from an aborted
  # launch was reused as complete; it actually has 5, and until they are
  # decided the theorem is open.
  hr
  $PY - <<'EOF' 2>/dev/null || echo "  (five-config check unavailable yet)"
import glob, json, os

PAT = (0, 1, 3, 7, 11, 13, 14)
tag = ''.join(f'{c:02d}' for c in PAT)

found = 0
for p in glob.glob(f'results/enum_cells/run-*/{tag}_*.jsonl'):
    for line in open(p):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if 'config' in e:
            found += 1
print(f'THE FIVE  pattern {PAT}')
print(f'  enumerated so far : {found}   (archived run recorded 0)')

path = f'results/tier3_checks/{tag}.json'
if not os.path.exists(path):
    print('  verdicts          : not started')
else:
    try:
        rows = json.load(open(path))
    except (json.JSONDecodeError, ValueError):
        print('  verdicts          : file being written')
        rows = []
    ref = sum(1 for r in rows if r.get('status') == 'INFEASIBLE')
    over = sum(1 for r in rows if (r.get('value') or 0) > 1786)
    und = len(rows) - ref - over
    print(f'  verdicts          : {len(rows)} decided, {ref} refuted, '
          f'{und} undecided, {over} ABOVE 1786')
    if over:
        print('  *** a configuration exceeds 1786 -- the record would fall ***')
    elif rows and ref == len(rows):
        print('  all refuted: the gap the stale checkpoint left is closed')
EOF
}

if [ "$ONCE" = "1" ]; then
  snapshot
  exit 0
fi

while true; do
  clear 2>/dev/null || true
  snapshot
  hr
  echo "refreshing every ${INTERVAL}s -- Ctrl-C to stop"
  sleep "$INTERVAL"
done
