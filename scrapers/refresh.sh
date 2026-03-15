#!/bin/bash
set -o pipefail
LOGFILE=~/dental-pe-tracker/logs/refresh_$(date +%Y-%m-%d_%H%M).log
PROJECT=~/dental-pe-tracker
PYTHON=/usr/local/bin/python3

echo "==========================================" | tee -a "$LOGFILE"
echo "  DENTAL PE TRACKER — FULL REFRESH"        | tee -a "$LOGFILE"
echo "  Started: $(date)"                         | tee -a "$LOGFILE"
echo "==========================================" | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "[1/10] Backing up database..." | tee -a "$LOGFILE"
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

run_step "[2/10] Scraping PESP..."                "$PYTHON $PROJECT/scrapers/pesp_scraper.py"
run_step "[3/10] Scraping GDN..."                 "$PYTHON $PROJECT/scrapers/gdn_scraper.py"
run_step "[4/10] Importing PitchBook CSVs..."     "$PYTHON $PROJECT/scrapers/pitchbook_importer.py --auto"
run_step "[5/10] Scraping ADSO locations..."       "$PYTHON $PROJECT/scrapers/adso_location_scraper.py"
run_step "[6/10] Checking ADA HPI for updates..."  "$PYTHON $PROJECT/scrapers/ada_hpi_downloader.py"
run_step "[7/10] Classifying DSO affiliations..."  "$PYTHON $PROJECT/scrapers/dso_classifier.py"
run_step "[8/10] Merging and scoring..."           "$PYTHON $PROJECT/scrapers/merge_and_score.py"

# Weekly qualitative research (only if ANTHROPIC_API_KEY is configured)
if [ -n "$ANTHROPIC_API_KEY" ]; then
    run_step "[9/10] Weekly qualitative research..." "$PYTHON $PROJECT/scrapers/weekly_research.py --budget 5"
fi

# Sync to Supabase (only if SUPABASE_DATABASE_URL is configured)
if [ -n "$SUPABASE_DATABASE_URL" ]; then
    run_step "[10/10] Syncing to Supabase..." "$PYTHON $PROJECT/scrapers/sync_to_supabase.py"
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
  git push 2>&1 | tee -a "$LOGFILE" && \
  echo "  Pushed to GitHub — Streamlit Cloud will auto-deploy." | tee -a "$LOGFILE" || \
  echo "  Git push skipped (no changes or error)." | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "DONE: $(date)" | tee -a "$LOGFILE"
