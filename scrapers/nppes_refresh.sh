#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/nppes_refresh_$(date +%Y-%m-%d_%H%M).log
PROJECT=~/dental-pe-tracker
PYTHON=/usr/local/bin/python3

echo "NPPES Monthly Refresh — $(date)" | tee -a "$LOGFILE"

run_step() {
    local step="$1"
    local cmd="$2"
    echo "$step" | tee -a "$LOGFILE"
    if $cmd 2>&1 | tee -a "$LOGFILE"; then
        true
    else
        echo "  WARNING: $step had errors (exit code: ${PIPESTATUS[0]})." | tee -a "$LOGFILE"
    fi
}

run_step "[1/3] Downloading NPPES update..." "$PYTHON $PROJECT/scrapers/nppes_downloader.py"
run_step "[2/3] Classifying..."              "$PYTHON $PROJECT/scrapers/dso_classifier.py"
run_step "[3/3] Scoring..."                  "$PYTHON $PROJECT/scrapers/merge_and_score.py"

echo "NPPES refresh complete: $(date)" | tee -a "$LOGFILE"

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
  git push 2>&1 | tee -a "$LOGFILE" && \
  echo "  Pushed to GitHub — Streamlit Cloud will auto-deploy." | tee -a "$LOGFILE" || \
  echo "  Git push skipped (no changes or error)." | tee -a "$LOGFILE"
