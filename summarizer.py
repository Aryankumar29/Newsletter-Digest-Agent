"""Newsletter summarization using Claude Haiku 4.5.

Strategy for minimal API calls:
- If total content fits in one context window: 1 API call (combined extract + synthesize)
- If content is too large: batch into chunks → 1 call per chunk + 1 synthesis call
- Typical day (10-15 newsletters): 1-2 API calls total
"""

import json
import logging
from datetime import datetime

import anthropic

from config import Config

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

CATEGORIES = [
    "AI & ML",
    "Funding & Deals",
    "Market Trends",
    "Legal Tech",
    "Product Launches",
    "Policy & Regulation",
    "Specter-Relevant",
]

EXTRACTION_PROMPT = """You are a senior analyst creating a daily intelligence briefing from newsletters. 
Today's date: {date}

You will receive the full text of {count} newsletters. Your job:

1. **Per-Newsletter Summary**: For each newsletter, extract:
   - Source (sender name)
   - 2-3 sentence summary of the most important points
   - Key facts, numbers, or quotes worth noting
   - Any links or resources mentioned

2. **Categorized Digest**: Group ALL insights across all newsletters into these categories:
   {categories}
   
   For each category that has relevant content:
   - Write 3-5 bullet points synthesizing across sources
   - Note which source(s) each insight came from
   - Highlight anything time-sensitive or actionable

3. **Executive Summary**: Write a 3-4 sentence overview of the most important things from today's newsletters. What should the reader pay attention to?

4. **Specter-Relevant Flag**: Specifically flag anything related to:
   - Legal technology, litigation tools, AI in law
   - Mass tort / class action news
   - Medical record processing, healthcare data
   - Funding rounds in legal tech or adjacent spaces

Output format - respond with ONLY valid JSON (no markdown fences):
{{
    "executive_summary": "...",
    "categories": {{
        "AI & ML": ["insight 1 (Source: X)", "insight 2 (Source: Y)"],
        "Funding & Deals": ["..."],
        ...
    }},
    "per_source": [
        {{
            "source": "Newsletter Name",
            "summary": "2-3 sentence summary",
            "key_facts": ["fact 1", "fact 2"],
            "links": ["url1", "url2"]
        }}
    ],
    "specter_relevant": ["specific item 1", "specific item 2"],
    "active_categories": ["AI & ML", "Funding & Deals"]
}}

Only include categories that have actual content. The "active_categories" array should list the category names that have insights.

---

Here are today's newsletters:

{newsletters}
"""

CHUNK_SYNTHESIS_PROMPT = """You are combining multiple partial newsletter analyses into one final daily briefing.
Today's date: {date}

Below are partial analyses from different batches of newsletters. Merge them into a single coherent briefing.

Combine and deduplicate insights. Produce the same JSON format:
{{
    "executive_summary": "...",
    "categories": {{...}},
    "per_source": [...],
    "specter_relevant": [...],
    "active_categories": [...]
}}

Partial analyses:
{chunks}
"""


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // Config.CHARS_PER_TOKEN


def _format_newsletters_block(newsletters: list[dict]) -> str:
    """Format newsletters into a single text block for the prompt."""
    blocks = []
    for i, nl in enumerate(newsletters, 1):
        blocks.append(
            f"=== NEWSLETTER {i} ===\n"
            f"From: {nl['sender']}\n"
            f"Subject: {nl['subject']}\n"
            f"Date: {nl.get('date', 'Unknown')}\n"
            f"---\n"
            f"{nl['body']}\n"
        )
    return "\n\n".join(blocks)


def _call_llm(prompt: str) -> str:
    """Single LLM call with error handling."""
    logger.info(f"LLM call: ~{_estimate_tokens(prompt)} input tokens")

    response = client.messages.create(
        model=Config.MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling common issues."""
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]  # Remove first line
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.debug(f"Raw response: {text[:500]}")
        # Return a minimal valid structure
        return {
            "executive_summary": "Failed to parse newsletter digest. Check logs.",
            "categories": {},
            "per_source": [],
            "specter_relevant": [],
            "active_categories": [],
            "_parse_error": str(e),
            "_raw_response": text[:2000],
        }


def summarize_newsletters(newsletters: list[dict], date: datetime) -> dict:
    """
    Summarize newsletters into a structured digest.

    Automatically batches if content exceeds context window limits.

    Returns:
        dict with keys: executive_summary, categories, per_source,
                       specter_relevant, active_categories
    """
    if not newsletters:
        return {
            "executive_summary": "No newsletters received today.",
            "categories": {},
            "per_source": [],
            "specter_relevant": [],
            "active_categories": [],
        }

    date_str = date.strftime("%B %d, %Y")
    categories_str = "\n   ".join(f"- {c}" for c in CATEGORIES)

    # Check if everything fits in one call
    all_content = _format_newsletters_block(newsletters)
    total_tokens = _estimate_tokens(all_content) + 2000  # Prompt overhead

    if total_tokens <= Config.MAX_INPUT_TOKENS:
        # === SINGLE CALL PATH (most common) ===
        logger.info(f"Single-call mode: {len(newsletters)} newsletters, ~{total_tokens} tokens")

        prompt = EXTRACTION_PROMPT.format(
            date=date_str,
            count=len(newsletters),
            categories=categories_str,
            newsletters=all_content,
        )

        response_text = _call_llm(prompt)
        return _parse_json_response(response_text)

    else:
        # === CHUNKED MODE (rare, 20+ newsletters) ===
        logger.info(f"Chunked mode: {len(newsletters)} newsletters, ~{total_tokens} tokens")

        # Split newsletters into chunks that fit
        chunks = []
        current_chunk = []
        current_tokens = 2000  # Prompt overhead

        for nl in newsletters:
            nl_tokens = _estimate_tokens(nl["body"]) + 200  # Header overhead
            if current_tokens + nl_tokens > Config.MAX_INPUT_TOKENS and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 2000

            current_chunk.append(nl)
            current_tokens += nl_tokens

        if current_chunk:
            chunks.append(current_chunk)

        logger.info(f"Split into {len(chunks)} chunks")

        # Process each chunk
        partial_results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i + 1}/{len(chunks)} ({len(chunk)} newsletters)")
            chunk_content = _format_newsletters_block(chunk)
            prompt = EXTRACTION_PROMPT.format(
                date=date_str,
                count=len(chunk),
                categories=categories_str,
                newsletters=chunk_content,
            )
            result_text = _call_llm(prompt)
            partial_results.append(result_text)

        # Synthesize chunks into final digest
        logger.info("Synthesizing chunks into final digest...")
        synthesis_prompt = CHUNK_SYNTHESIS_PROMPT.format(
            date=date_str,
            chunks="\n\n---\n\n".join(partial_results),
        )
        final_text = _call_llm(synthesis_prompt)
        return _parse_json_response(final_text)
