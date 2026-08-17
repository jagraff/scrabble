#!/usr/bin/env bash
# Clean end-to-end re-run, from an empty checkpoint directory.
#
# Every stage writes into results/ and is followed by the check that can
# fail it. The order matters: each stage's output selects the next stage's
# work, so a stage that quietly produced fewer patterns than before would
# otherwise shrink everything downstream of it and still look complete.
#
# Deliberately NOT resumable. A re-run whose point is that no stale artifact
# was reused must not itself reuse one; if it dies, start it again.
set -u -o pipefail

cd "$(dirname "$0")"
export PYTHONHASHSEED=0
PY=.venv/bin/python
LOG=results/rerun
mkdir -p "$LOG"

step() {
  local name="$1"; shift
  echo "=== $(date '+%H:%M:%S')  $name" | tee -a "$LOG/rerun.log"
  local t0=$SECONDS
  if ! "$@" >"$LOG/$name.out" 2>&1; then
    echo "!!! $name FAILED after $((SECONDS - t0))s -- see $LOG/$name.out" \
      | tee -a "$LOG/rerun.log"
    tail -20 "$LOG/$name.out" | tee -a "$LOG/rerun.log"
    exit 1
  fi
  echo "    $name ok in $((SECONDS - t0))s" | tee -a "$LOG/rerun.log"
}

echo "clean re-run starting $(date)" | tee "$LOG/rerun.log"
$PY -m scrabble_max.provenance | tee -a "$LOG/rerun.log"

# The checkpoint directory must be empty of *this run's* namespace. It is
# namespaced by the run digest, so a previous run at the same settings would
# be reused -- which is exactly what a clean re-run must not do.
#
# `--resume` is the one legitimate exception, and it is narrow. It keeps the
# existing namespace so a run interrupted *after* its enumeration finished
# can carry on. What makes that sound is not the operator's word: the cells
# are identity-bound, so any that were produced under a different lexicon,
# threshold, partition or model source are refused on sight, and the ones
# that remain are proofs about the model being run now. The move-aside
# exists to stop a *different* computation being reused, and the identity
# gate already does that job -- this only avoids discarding twelve hours of
# valid work when the interruption was a crash in a later stage.
RESUME=0
if [ "${1:-}" = '--resume' ]; then
  RESUME=1
fi

RUNDIR=$($PY -c "
from scrabble_max import identity as ID
from scrabble_max.provenance import LEXICON_PATH
run = ID.run_manifest(lexicon_path=LEXICON_PATH, threshold=1786,
                      word='OXYPHENBUTAZONE', n_blocks=4)
print(ID.run_dir('results/enum_cells', run))")
if [ -d "$RUNDIR" ] && [ "$RESUME" = '0' ]; then
  echo "moving aside a previous run at the same settings: $RUNDIR" \
    | tee -a "$LOG/rerun.log"
  mv "$RUNDIR" "${RUNDIR}.superseded.$(date +%s)"
elif [ "$RESUME" = '1' ]; then
  n_done=$(grep -l '"complete"' "$RUNDIR"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
  n_all=$(ls "$RUNDIR"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
  echo "--resume: keeping $RUNDIR ($n_done of $n_all cells already complete;" \
    "each is identity-bound and re-verified before reuse)" \
    | tee -a "$LOG/rerun.log"
fi
echo "cells will be written to $RUNDIR" | tee -a "$LOG/rerun.log"

# Tests first. A run that certifies results produced by code which does not
# pass its own tests certifies nothing, and finding that out after two and a
# half hours of solving is the expensive way to find it out.
step tests-fast $PY -m pytest tests/ -q -m "not slow"
step tests-slow $PY -m pytest tests/ -q -m slow

step stage-a   $PY -m scrabble_max.bounds --threshold 1786
step stage-b   $PY -m scrabble_max.tighten --time-limit 240
# `--six-tiles`, not `--max-placed 6 --word ... --out ...`. The latter is
# what REPORT.md documented and it does something else entirely: it takes
# the ordinary candidate path and writes a two-row list, where Theorem 3
# needs the per-row, per-mask dictionary `--six-tiles` produces. The
# documented command did not reproduce the committed artifact.
step six-tiles $PY -m scrabble_max.tighten --six-tiles
step tier-2    $PY -m scrabble_max.patterns --stop-after-row1
step sweep     $PY -m scrabble_max.blank_tier2
step tier-3    $PY -m scrabble_max.tier3 --workers 4 --blocks 4
step reach     $PY -m scrabble_max.reachability
step racks     $PY -m scrabble_max.racks
step directional $PY -m scrabble_max.check_rerun
step manifest  $PY -m scrabble_max.manifest

echo "=== $(date '+%H:%M:%S')  done in $((SECONDS / 60)) min" \
  | tee -a "$LOG/rerun.log"
tail -20 "$LOG/manifest.out" | tee -a "$LOG/rerun.log"
