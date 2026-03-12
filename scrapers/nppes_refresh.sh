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
