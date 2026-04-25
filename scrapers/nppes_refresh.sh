#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/nppes_refresh_$(date +%Y-%m-%d_%H%M).log
PROJECT=~/dental-pe-tracker
PYTHON=/usr/local/bin/python3
export PYTHONPATH="$PROJECT:$PYTHONPATH"
cd "$PROJECT"

# Load environment variables
if [ -f "$PROJECT/.env" ]; then
    set -a
    source "$PROJECT/.env"
    set +a
fi

echo "NPPES Monthly Refresh — $(date)" | tee -a "$LOGFILE"

# run_step: wraps a command with a per-step timeout and descendant-kill on hang.
# Usage: run_step "<label>" "<command>" [timeout_minutes]
# Mirrors the pattern from refresh.sh so hung NPPES downloads (90+ MB files)
# can't block the pipeline indefinitely. Audit §15 #13 / §5.
run_step() {
    local step="$1"
    local cmd="$2"
    local timeout_min="${3:-30}"   # default 30 minutes (NPPES download is large)
    local timeout_sec=$(( timeout_min * 60 ))
    echo "" | tee -a "$LOGFILE"
    echo "$step (timeout: ${timeout_min}m)" | tee -a "$LOGFILE"
    # Run cmd in background so we can kill it if it hangs.
    # set -o pipefail inside the subshell ensures cmd failure propagates through the pipe.
    ( set -o pipefail; $cmd 2>&1 | tee -a "$LOGFILE" ) &
    local bgpid=$!
    local elapsed=0
    while kill -0 $bgpid 2>/dev/null; do
        sleep 10
        elapsed=$(( elapsed + 10 ))
        if [ $elapsed -ge $timeout_sec ]; then
            echo "  TIMEOUT: $step exceeded ${timeout_min}m — killing pid $bgpid and descendants" | tee -a "$LOGFILE"
            # kill $bgpid alone only terminates the subshell wrapper; the Python child is a
            # separate process in the subshell's pipe and would be orphaned. pkill -P kills
            # the subshell's children (python + tee) so the downloader actually stops.
            pkill -TERM -P $bgpid 2>/dev/null
            kill -TERM $bgpid 2>/dev/null
            sleep 30
            pkill -KILL -P $bgpid 2>/dev/null
            kill -KILL $bgpid 2>/dev/null
            return 124
        fi
    done
    wait $bgpid
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "  WARNING: $step had errors (exit code: $exit_code). Continuing." | tee -a "$LOGFILE"
    fi
}

run_step "[1/3] Downloading NPPES update..." "$PYTHON $PROJECT/scrapers/nppes_downloader.py" 90
run_step "[2/3] Classifying..."              "$PYTHON $PROJECT/scrapers/dso_classifier.py"   15
run_step "[3/3] Scoring..."                  "$PYTHON $PROJECT/scrapers/merge_and_score.py"  10

echo "NPPES refresh complete: $(date)" | tee -a "$LOGFILE"

# Sync to Supabase (only if SUPABASE_DATABASE_URL is configured)
if [ -n "$SUPABASE_DATABASE_URL" ]; then
    run_step "[4/4] Syncing to Supabase..." "$PYTHON $PROJECT/scrapers/sync_to_supabase.py" 30
fi

# Compress and push DB to Streamlit Cloud (auto-deploy)
echo "" | tee -a "$LOGFILE"
echo "[POST] Compressing + pushing DB to cloud..." | tee -a "$LOGFILE"
cd "$PROJECT"
$PYTHON -c "
import gzip, shutil
with open('data/dental_pe_tracker.db','rb') as f:
    with gzip.open('data/dental_pe_tracker.db.gz','wb',6) as gz:
        shutil.copyfileobj(f, gz)
print('  Compressed.')
" 2>&1 | tee -a "$LOGFILE"

git add data/dental_pe_tracker.db.gz && \
  git commit -m "NPPES refresh $(date +%Y-%m-%d)" 2>&1 | tee -a "$LOGFILE" && \
  {
    if [ -n "$GITHUB_TOKEN" ]; then
      git -c "credential.https://github.com.helper=!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f" push 2>&1 | tee -a "$LOGFILE"
    else
      git push 2>&1 | tee -a "$LOGFILE"
    fi
  } && \
  echo "  Pushed to GitHub — Streamlit Cloud will auto-deploy." | tee -a "$LOGFILE" || \
  echo "  Git push skipped (no changes or error)." | tee -a "$LOGFILE"
