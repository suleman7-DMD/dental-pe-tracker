#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/refresh_$(date +%Y-%m-%d_%H%M).log
PROJECT=~/dental-pe-tracker

echo "==========================================" | tee -a "$LOGFILE"
echo "  DENTAL PE TRACKER — FULL REFRESH"        | tee -a "$LOGFILE"
echo "  Started: $(date)"                         | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "[1/8] Backing up database..." | tee -a "$LOGFILE"
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

run_step "[2/8] Scraping PESP..."                "python3 $PROJECT/scrapers/pesp_scraper.py"
run_step "[3/8] Scraping GDN..."                 "python3 $PROJECT/scrapers/gdn_scraper.py"
run_step "[4/8] Importing PitchBook CSVs..."     "python3 $PROJECT/scrapers/pitchbook_importer.py --auto"
run_step "[5/8] Scraping ADSO locations..."       "python3 $PROJECT/scrapers/adso_location_scraper.py"
run_step "[6/8] Checking ADA HPI for updates..."  "python3 $PROJECT/scrapers/ada_hpi_downloader.py"
run_step "[7/8] Classifying DSO affiliations..."  "python3 $PROJECT/scrapers/dso_classifier.py"
run_step "[8/8] Merging and scoring..."           "python3 $PROJECT/scrapers/merge_and_score.py"

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
python3 -c "
import gzip, shutil
with open('data/dental_pe_tracker.db','rb') as f:
    with gzip.open('data/dental_pe_tracker.db.gz','wb',6) as gz:
        shutil.copyfileobj(f, gz)
print('  Compressed.')
" 2>&1 | tee -a "$LOGFILE"

git add data/dental_pe_tracker.db.gz && \
  git commit -m "Auto-refresh $(date +%Y-%m-%d)" 2>&1 | tee -a "$LOGFILE" && \
  git push 2>&1 | tee -a "$LOGFILE" && \
  echo "  Pushed to GitHub — Streamlit Cloud will auto-deploy." | tee -a "$LOGFILE" || \
  echo "  Git push skipped (no changes or error)." | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "DONE: $(date)" | tee -a "$LOGFILE"
