#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/refresh_$(date +%Y-%m-%d_%H%M).log
PROJECT=~/dental-pe-tracker

echo "==========================================" | tee -a "$LOGFILE"
echo "  DENTAL PE TRACKER — REFRESH PIPELINE"    | tee -a "$LOGFILE"
echo "  Started: $(date)"                         | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "[1/6] Backing up database..." | tee -a "$LOGFILE"
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
    echo "" | tee -a "$LOGFILE"
    echo "$step" | tee -a "$LOGFILE"
    if $cmd 2>&1 | tee -a "$LOGFILE"; then
        true
    else
        echo "  WARNING: $step had errors (exit code: ${PIPESTATUS[0]}). Continuing." | tee -a "$LOGFILE"
    fi
}

run_step "[2/6] Scraping PESP..."             "python3 $PROJECT/scrapers/pesp_scraper.py"
run_step "[3/6] Scraping GDN..."              "python3 $PROJECT/scrapers/gdn_scraper.py"
run_step "[4/6] Importing PitchBook CSVs..."  "python3 $PROJECT/scrapers/pitchbook_importer.py --auto"
run_step "[5/6] Classifying DSO affiliations..." "python3 $PROJECT/scrapers/dso_classifier.py"
run_step "[6/6] Merging and scoring..."       "python3 $PROJECT/scrapers/merge_and_score.py"

echo "" | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"
echo "  REFRESH COMPLETE: $(date)"               | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

find "$PROJECT/backups/" -name "*.db" -mtime +90 -delete 2>/dev/null
find "$PROJECT/logs/" -name "*.log" -mtime +90 -delete 2>/dev/null
