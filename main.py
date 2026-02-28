#!/usr/bin/env python3
"""
Newsletter Digest Agent — Main Orchestrator

Fetches newsletters from Gmail, summarizes with Claude Haiku,
and publishes a categorized daily digest to Notion.

Usage:
    python main.py                  # Process yesterday's newsletters
    python main.py --date 2025-02-27  # Process specific date
    python main.py --today          # Process today's newsletters
    python main.py --dry-run        # Fetch + summarize but don't publish to Notion
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import Config
from gmail_fetcher import fetch_newsletters
from summarizer import summarize_newsletters
from notion_publisher import publish_digest

# Setup logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / "digest.log"),
    ],
)
logger = logging.getLogger("newsletter-digest")


def run(target_date: datetime, dry_run: bool = False):
    """Execute the full pipeline for a given date."""
    date_str = target_date.strftime("%Y-%m-%d")
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting newsletter digest for {date_str}")

    # Step 1: Fetch from Gmail
    logger.info("=" * 50)
    logger.info("STEP 1: Fetching newsletters from Gmail...")
    newsletters = fetch_newsletters(target_date)

    if not newsletters:
        logger.info("No newsletters found. Nothing to do.")
        return

    logger.info(f"Fetched {len(newsletters)} newsletters:")
    for nl in newsletters:
        logger.info(f"  📧 {nl['sender'][:50]} — {nl['subject'][:60]}")

    # Step 2: Summarize with Claude
    logger.info("=" * 50)
    logger.info("STEP 2: Summarizing with Claude Haiku...")
    digest = summarize_newsletters(newsletters, target_date)

    # Log summary stats
    active_cats = digest.get("active_categories", [])
    specter_items = digest.get("specter_relevant", [])
    logger.info(f"  Categories: {', '.join(active_cats) or 'None'}")
    logger.info(f"  Specter-relevant items: {len(specter_items)}")
    logger.info(f"  Executive summary: {digest.get('executive_summary', '')[:100]}...")

    if dry_run:
        # Save to local file instead of Notion
        output_path = Path(__file__).parent / f"digest_{date_str}.json"
        output_path.write_text(json.dumps(digest, indent=2))
        logger.info(f"[DRY RUN] Digest saved to {output_path}")
        print(f"\n📋 Executive Summary:\n{digest.get('executive_summary', 'N/A')}")
        return

    # Step 3: Publish to Notion
    logger.info("=" * 50)
    logger.info("STEP 3: Publishing to Notion...")
    page_url = publish_digest(digest, target_date, len(newsletters))

    logger.info("=" * 50)
    logger.info(f"✅ Done! Digest published: {page_url}")
    logger.info(f"   Newsletters processed: {len(newsletters)}")
    logger.info(f"   Categories: {', '.join(active_cats)}")
    logger.info(f"   Specter-relevant items: {len(specter_items)}")


def main():
    parser = argparse.ArgumentParser(description="Newsletter Digest Agent")
    parser.add_argument(
        "--date",
        type=str,
        help="Target date in YYYY-MM-DD format (default: yesterday)",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Process today's newsletters instead of yesterday's",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and summarize but don't publish to Notion",
    )
    args = parser.parse_args()

    # Validate config
    try:
        Config.validate()
    except EnvironmentError as e:
        logger.error(str(e))
        sys.exit(1)

    # Determine target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)
    elif args.today:
        target_date = datetime.now()
    else:
        target_date = datetime.now() - timedelta(days=1)

    try:
        run(target_date, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
