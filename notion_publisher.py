"""Notion API integration for publishing daily digests.

Creates a single page per day in the Newsletter Digests database.
Uses the official notion-client SDK for a single API call.
"""

import json
import logging
from datetime import datetime

from notion_client import Client

from config import Config

logger = logging.getLogger(__name__)

notion = Client(auth=Config.NOTION_API_KEY)


def _build_rich_text(text: str) -> dict:
    """Build a Notion rich text block."""
    return {"type": "text", "text": {"content": text[:2000]}}  # Notion limit per block


def _build_paragraph(text: str) -> dict:
    """Build a paragraph block, splitting if text exceeds 2000 chars."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [_build_rich_text(text)]
        }
    }


def _build_heading(text: str, level: int = 2) -> dict:
    """Build a heading block (level 1, 2, or 3)."""
    heading_type = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {
            "rich_text": [_build_rich_text(text)]
        }
    }


def _build_bulleted_item(text: str) -> dict:
    """Build a bulleted list item."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [_build_rich_text(text)]
        }
    }


def _build_callout(text: str, emoji: str = "🔍") -> dict:
    """Build a callout block (used for Specter-relevant items)."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [_build_rich_text(text)],
            "icon": {"type": "emoji", "emoji": emoji},
        }
    }


def _build_toggle(title: str, children: list[dict]) -> dict:
    """Build a toggle block with children."""
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [_build_rich_text(title)],
            "children": children,
        }
    }


def _build_divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _build_page_content(digest: dict) -> list[dict]:
    """Convert digest dict into Notion block children."""
    blocks = []

    # --- Executive Summary ---
    blocks.append(_build_heading("Executive Summary", 2))
    blocks.append(_build_callout(digest.get("executive_summary", "No summary available."), "📋"))
    blocks.append(_build_divider())

    # --- Specter-Relevant (if any) ---
    specter_items = digest.get("specter_relevant", [])
    if specter_items:
        blocks.append(_build_heading("🎯 Specter-Relevant", 2))
        for item in specter_items:
            blocks.append(_build_callout(item, "⚡"))
        blocks.append(_build_divider())

    # --- Categorized Insights ---
    categories = digest.get("categories", {})
    if categories:
        blocks.append(_build_heading("Categorized Insights", 2))
        for category, insights in categories.items():
            if not insights:
                continue

            # Category as H3
            emoji_map = {
                "AI & ML": "🤖",
                "Funding & Deals": "💰",
                "Market Trends": "📈",
                "Legal Tech": "⚖️",
                "Product Launches": "🚀",
                "Policy & Regulation": "📜",
                "Specter-Relevant": "🎯",
            }
            emoji = emoji_map.get(category, "📌")
            blocks.append(_build_heading(f"{emoji} {category}", 3))

            for insight in insights:
                blocks.append(_build_bulleted_item(insight))

        blocks.append(_build_divider())

    # --- Per-Source Summaries (in toggles for clean UX) ---
    per_source = digest.get("per_source", [])
    if per_source:
        blocks.append(_build_heading("Source Details", 2))

        for source in per_source:
            source_name = source.get("source", "Unknown")
            summary = source.get("summary", "")
            key_facts = source.get("key_facts", [])
            links = source.get("links", [])

            # Build toggle children
            toggle_children = []
            if summary:
                toggle_children.append(_build_paragraph(summary))
            if key_facts:
                for fact in key_facts:
                    toggle_children.append(_build_bulleted_item(f"📌 {fact}"))
            if links:
                for link in links:
                    toggle_children.append(_build_bulleted_item(f"🔗 {link}"))

            if not toggle_children:
                toggle_children.append(_build_paragraph("No details extracted."))

            blocks.append(_build_toggle(f"📰 {source_name}", toggle_children))

    # Notion API limit: max 100 blocks per request
    if len(blocks) > 100:
        logger.warning(f"Truncating blocks from {len(blocks)} to 100 (Notion limit)")
        blocks = blocks[:99]
        blocks.append(_build_paragraph("⚠️ Content truncated due to Notion block limit."))

    return blocks


def publish_digest(digest: dict, date: datetime, newsletter_count: int) -> str:
    """
    Publish digest to Notion database.

    Args:
        digest: Structured digest from summarizer
        date: Date of the digest
        newsletter_count: Number of newsletters processed

    Returns:
        URL of the created Notion page
    """
    date_str = date.strftime("%B %d, %Y")
    title = f"📬 Newsletter Digest — {date_str}"

    # Build multi-select categories
    active_categories = digest.get("active_categories", [])
    category_options = [{"name": cat} for cat in active_categories if cat in [
        "AI & ML", "Funding & Deals", "Market Trends", "Legal Tech",
        "Product Launches", "Policy & Regulation", "Specter-Relevant",
    ]]

    # Build source list as comma-separated string
    sources_text = ", ".join(
        s.get("source", "Unknown") for s in digest.get("per_source", [])
    )

    # Determine status
    status = "Generated"
    if digest.get("_parse_error"):
        status = "Partial"
    if not digest.get("executive_summary") or digest["executive_summary"].startswith("Failed"):
        status = "Failed"

    # Build page content blocks
    children = _build_page_content(digest)

    # --- Single API call: Create page with properties + content ---
    logger.info(f"Creating Notion page: {title}")

    try:
        page = notion.pages.create(
            parent={"database_id": Config.NOTION_DATABASE_ID},
            properties={
                "Title": {"title": [{"text": {"content": title}}]},
                "Date": {"date": {"start": date.strftime("%Y-%m-%d")}},
                "Newsletter Count": {"number": newsletter_count},
                "Categories": {"multi_select": category_options},
                "Status": {"select": {"name": status}},
                "Sources": {"rich_text": [{"text": {"content": sources_text[:2000]}}]},
            },
            children=children,
        )

        page_url = page["url"]
        logger.info(f"✅ Notion page created: {page_url}")
        return page_url

    except Exception as e:
        logger.error(f"Failed to create Notion page: {e}")
        raise
