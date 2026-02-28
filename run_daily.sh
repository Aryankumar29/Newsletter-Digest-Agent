#!/bin/bash
# Newsletter Digest Agent — Daily Cron Runner
# 
# Add to crontab:
#   crontab -e
#   0 8 * * * /path/to/newsletter-digest/run_daily.sh
#
# This runs at 8:00 AM daily, processing yesterday's newsletters.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Run the digest pipeline
python main.py 2>&1 | tee -a digest_cron.log

echo "[$(date)] Cron run complete" >> digest_cron.log
