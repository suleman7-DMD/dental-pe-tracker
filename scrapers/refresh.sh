#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/refresh_$(date +%Y-%m-%d_%H%M).log
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

echo "==========================================" | tee -a "$LOGFILE"
echo "  DENTAL PE TRACKER — FULL REFRESH"        | tee -a "$LOGFILE"
echo "  Started: $(date)"                         | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "[1/11] Backing up database..." | tee -a "$LOGFILE"
if [ -f "$PROJECT/data/dental_pe_tracker.db" ]; then
    cp "$PROJECT/data/dental_pe_tracker.db" \
       "$PROJECT/backups/dental_pe_tracker_$(date +%Y-%m-%d).db"
    echo "  Backup created." | tee -a "$LOGFILE"
else
    echo "  No existing database to backup." | tee -a "$LOGFILE"
fi

run_step() {
    local step="$1"
    local cmd="$2"
    local timeout_min="${3:-15}"   # default 15 minutes per step
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
            # the subshell's children (python + tee) so the scraper actually stops.
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

run_step "[2/11] Scraping PESP..."                "$PYTHON $PROJECT/scrapers/pesp_scraper.py"              15
run_step "[3/11] Scraping GDN..."                 "$PYTHON $PROJECT/scrapers/gdn_scraper.py"               15
run_step "[4/11] Importing PitchBook CSVs..."     "$PYTHON $PROJECT/scrapers/pitchbook_importer.py --auto"  5
run_step "[5/11] Scraping ADSO locations..."       "$PYTHON $PROJECT/scrapers/adso_location_scraper.py"    30
run_step "[6/11] Checking ADA HPI for updates..."  "$PYTHON $PROJECT/scrapers/ada_hpi_downloader.py"       10
run_step "[7/11] Classifying DSO affiliations..."  "$PYTHON $PROJECT/scrapers/dso_classifier.py"           15
# Pass 3: entity type classification (watched ZIPs only) — audit §14.4 / §15 #6
# dso_classifier.py skips Pass 3 by default (--entity-types-only flag required).
# Running it separately ensures entity_classification is populated for all watched-ZIP
# practices after every refresh, without altering the global Pass 1+2 run above.
run_step "[7b/11] Entity type classification (Pass 3)..." "$PYTHON $PROJECT/scrapers/dso_classifier.py --entity-types-only"  20
run_step "[8/11] Merging and scoring..."           "$PYTHON $PROJECT/scrapers/merge_and_score.py"          10

# Weekly qualitative research (only if ANTHROPIC_API_KEY is configured)
if [ -n "$ANTHROPIC_API_KEY" ]; then
    run_step "[9/11] Weekly qualitative research..." "$PYTHON $PROJECT/scrapers/weekly_research.py --budget 5" 15
fi

run_step "[10/11] Computing Warroom signals..." "$PYTHON $PROJECT/scrapers/compute_signals.py" 10

# Sync to Supabase (only if SUPABASE_DATABASE_URL is configured)
if [ -n "$SUPABASE_DATABASE_URL" ]; then
    run_step "[11/11] Syncing to Supabase..." "$PYTHON $PROJECT/scrapers/sync_to_supabase.py" 60
fi

echo "" | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"
echo "  REFRESH COMPLETE: $(date)"               | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

# Housekeeping: prune old backups (>90 days) and old logs (>90 days)
find "$PROJECT/backups/" -name "*.db" -mtime +90 -delete 2>/dev/null
find "$PROJECT/logs/" -name "*.log" -mtime +90 -delete 2>/dev/null

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
  git commit -m "Auto-refresh $(date +%Y-%m-%d)" 2>&1 | tee -a "$LOGFILE" && \
  {
    if [ -n "$GITHUB_TOKEN" ]; then
      git -c "credential.https://github.com.helper=!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f" push 2>&1 | tee -a "$LOGFILE"
    else
      git push 2>&1 | tee -a "$LOGFILE"
    fi
  } && \
  echo "  Pushed to GitHub — Streamlit Cloud will auto-deploy." | tee -a "$LOGFILE" || \
  echo "  Git push skipped (no changes or error)." | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "DONE: $(date)" | tee -a "$LOGFILE"
