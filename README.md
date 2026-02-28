# Newsletter Digest Agent

A lightweight agentic pipeline that fetches newsletters from Gmail daily, summarizes them with Claude Haiku 4.5, and publishes a categorized intelligence digest to Notion — all in ~4 API calls per run.

## The Problem

Staying on top of 10-20+ daily newsletters (AI, funding, market trends, legal tech) takes 30-60 minutes. Most of that time is spent scanning for the 20% of content that actually matters.

## The Solution

This agent runs daily via cron and produces a single Notion page with:

- **Executive Summary** — 3-4 sentence overview of the day's most important items
- **Categorized Insights** — AI & ML, Funding & Deals, Market Trends, Legal Tech, Product Launches, Policy & Regulation — with source attribution
- **Domain-Specific Flags** — Items relevant to your specific domain (configured for legal tech / mass tort by default)
- **Per-Source Details** — Expandable toggle blocks with individual newsletter summaries, key facts, and links

## Architecture
```
Gmail (label filter + date range)
  │  [1 list + 1 batch API call]
  ▼
HTML → Plain Text (local, BeautifulSoup)
  │  [0 API calls]
  ▼
Claude Haiku 4.5 (extract + categorize + synthesize)
  │  [1-2 API calls]
  ▼
Notion Database Page (properties + rich content blocks)
     [1 API call]
```

**Total: ~4 API calls/day · ~$0.05/day · ~$1.50/month**

## Quick Start

### Prerequisites

- Python 3.11+
- Gmail account with newsletters in a labeled folder
- [Anthropic API key](https://console.anthropic.com/)
- [Notion Integration](https://www.notion.so/my-integrations)

### 1. Clone & Install
```bash
git clone https://github.com/YOUR_USERNAME/newsletter-digest.git
cd newsletter-digest
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Gmail API Setup (one-time, ~5 min)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Gmail API**
3. Create **OAuth 2.0 Client ID** (Desktop App)
4. Download JSON → save as `credentials.json` in project root
```bash
python setup_gmail.py
```

This opens a browser for Google sign-in. After auth, `token.json` is saved locally for automated use.

### 3. Notion Setup (one-time, ~3 min)

1. Create a [Notion Integration](https://www.notion.so/my-integrations) with Read + Insert content permissions
2. Create a database in Notion with these properties:

| Property | Type | Options |
|---|---|---|
| Title | Title | — |
| Date | Date | — |
| Newsletter Count | Number | — |
| Categories | Multi-select | `AI & ML`, `Funding & Deals`, `Market Trends`, `Legal Tech`, `Product Launches`, `Policy & Regulation`, `Specter-Relevant` |
| Sources | Text | — |

3. Share the database with your integration (... → Connections → Add)
4. Copy the Database ID from the URL

### 4. Configure
```bash
cp .env.example .env
```

Fill in your keys:
```env
ANTHROPIC_API_KEY=sk-ant-xxxxx
NOTION_API_KEY=ntn_xxxxx
NOTION_DATABASE_ID=your-32-char-database-id
GMAIL_LABEL=Newsletter
```

### 5. Run
```bash
# Test run (saves JSON locally, doesn't publish to Notion)
python main.py --dry-run

# Process yesterday's newsletters
python main.py

# Process a specific date
python main.py --date 2025-02-27

# Process today's newsletters
python main.py --today
```

### 6. Schedule (Daily Cron)
```bash
chmod +x run_daily.sh
crontab -e
# Add: 0 8 * * * /full/path/to/newsletter-digest/run_daily.sh
```

On Windows, use Task Scheduler to run `python main.py` daily.

## Project Structure
```
newsletter-digest/
├── config.py             # Environment variables, validation, constants
├── gmail_fetcher.py      # Gmail API — OAuth, batch fetch, HTML→text
├── summarizer.py         # Claude Haiku — extraction, categorization, JSON parsing
├── notion_publisher.py   # Notion API — block building, page creation
├── main.py               # CLI orchestrator, pipeline coordination
├── setup_gmail.py        # One-time Gmail OAuth flow
├── run_daily.sh          # Cron wrapper script
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
└── .gitignore
```

## How It Works

### Fetch (gmail_fetcher.py)

Uses Gmail's batch API to fetch all newsletters matching your label in a single HTTP request. HTML emails are converted to clean plain text locally using BeautifulSoup — no API calls for extraction. Individual newsletters are capped at 15K characters to prevent context window domination.

### Summarize (summarizer.py)

Sends all newsletters to Claude Haiku 4.5 in a single prompt (when under 75K tokens). The prompt produces structured JSON with per-source summaries, categorized insights, and domain-specific flags. For high-volume days (25+ newsletters), content is automatically chunked and synthesized.

Includes JSON repair logic for truncated LLM responses — closes open strings, brackets, and braces before falling back to raw text.

### Publish (notion_publisher.py)

Creates a single Notion page per day with:
- **Database properties** — Date, newsletter count, active categories, source list (for filtering/sorting)
- **Page content** — Executive summary callout, domain-relevant callouts, categorized bullet lists with source attribution, and expandable per-newsletter toggle blocks

## Cost Breakdown

| Component | Per Run | Monthly |
|---|---|---|
| Gmail API | Free | Free |
| Claude Haiku 4.5 (~25K input tokens) | ~$0.05 | ~$1.50 |
| Notion API | Free | Free |
| **Total** | **~$0.05** | **~$1.50** |

## Customization

### Change Categories

Edit the `CATEGORIES` list in `summarizer.py` and update the `EXTRACTION_PROMPT` to match.

### Change Domain Flags

Modify the "Specter-Relevant" section in `EXTRACTION_PROMPT` within `summarizer.py` to flag topics relevant to your domain.

### Switch LLM

Update `Config.MODEL` in `config.py`. Compatible with any Anthropic model — use Sonnet for higher quality, Haiku for lower cost.

## Troubleshooting

| Issue | Fix |
|---|---|
| `No newsletters found` | Verify `GMAIL_LABEL` in `.env` matches your Gmail label exactly |
| `Gmail token expired` | Delete `token.json`, re-run `python setup_gmail.py` |
| `Notion 401 Unauthorized` | Check `NOTION_API_KEY` and that the database is shared with the integration |
| `JSON parse error in logs` | Usually a truncated response — the repair logic handles most cases automatically |
| `UnicodeEncodeError` on Windows | Ensure `digest.log` uses UTF-8 encoding (already set in main.py) |

## License

MIT

---

Built as internal tooling for [Specter AI](https://specterai.com) — AI-powered litigation intelligence for law firms.
