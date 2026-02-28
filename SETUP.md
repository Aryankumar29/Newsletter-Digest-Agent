# Newsletter Digest Agent — Setup Guide

A local agent that fetches Gmail newsletters daily, summarizes them with Claude Haiku, and publishes a categorized digest to Notion.

## Architecture

```
Gmail (Newsletter label)
    │
    ▼  [1 list + 1 batch API call]
Fetch & Extract HTML→Text (local)
    │
    ▼  [1-2 API calls]
Claude Haiku 4.5 (extract + categorize)
    │
    ▼  [1 API call]
Notion Database Page (categorized digest)
```

**Total: ~4 API calls/day | ~$0.05/day | ~$1.50/month**

---

## Step 1: Clone & Install

```bash
cd newsletter-digest
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 2: Gmail API Setup (one-time, ~5 min)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (e.g., "Newsletter Digest")
3. Enable the **Gmail API**:
   - APIs & Services → Library → Search "Gmail API" → Enable
4. Create OAuth credentials:
   - APIs & Services → Credentials → Create Credentials → **OAuth 2.0 Client ID**
   - Application type: **Desktop App**
   - Name: "Newsletter Digest"
   - Download the JSON → save as `credentials.json` in this folder
5. Configure OAuth consent screen:
   - User type: **External** (or Internal if using Workspace)
   - Add your email as a test user
   - Scopes: `gmail.readonly`

6. Run the one-time auth:
```bash
python setup_gmail.py
```
This opens a browser for Google sign-in. After auth, `token.json` is saved locally.

## Step 3: Notion Integration Setup (one-time, ~3 min)

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Create a new integration:
   - Name: "Newsletter Digest Agent"
   - Capabilities: **Read + Insert content**
3. Copy the **Internal Integration Token** (starts with `ntn_`)
4. The database is already created. Share it with your integration:
   - Open the database in Notion
   - Click "..." → "Connections" → Add your integration

## Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
NOTION_API_KEY=ntn_your-key-here
NOTION_DATABASE_ID=de147ceba38f440f836177556f12c777
```

## Step 5: Test Run

```bash
# Dry run (no Notion publish, saves JSON locally)
python main.py --dry-run

# Process yesterday's newsletters
python main.py

# Process a specific date
python main.py --date 2025-02-27

# Process today's newsletters
python main.py --today
```

## Step 6: Set Up Daily Cron

```bash
chmod +x run_daily.sh

# Edit crontab
crontab -e

# Add this line (runs at 8 AM daily):
0 8 * * * /full/path/to/newsletter-digest/run_daily.sh
```

### Verify cron is working:
```bash
# List cron jobs
crontab -l

# Check logs after first run
tail -f digest.log
```

---

## Output: What the Notion Page Looks Like

Each daily page contains:

### 📋 Executive Summary
> A 3-4 sentence overview of the most important items across all newsletters.

### 🎯 Specter-Relevant
> Callout blocks for anything related to legal tech, mass tort, medical records, or litigation tools.

### Categorized Insights
- 🤖 **AI & ML** — Bullet points with source attribution
- 💰 **Funding & Deals** — Who raised, how much, from whom
- 📈 **Market Trends** — Industry movements
- ⚖️ **Legal Tech** — Legal industry specific
- 🚀 **Product Launches** — New tools and products
- 📜 **Policy & Regulation** — Government/regulatory updates

### Source Details
> Toggle blocks for each newsletter with individual summaries, key facts, and links.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `No newsletters found` | Check your Gmail label name matches `GMAIL_LABEL` in `.env` |
| `Gmail token expired` | Delete `token.json` and run `setup_gmail.py` again |
| `Notion 401` | Re-check `NOTION_API_KEY` and that the database is shared with the integration |
| `Notion 400 on Categories` | Ensure category names in the prompt match the database schema exactly |
| `LLM JSON parse error` | Check `digest.log` — the fallback handler will still create a partial page |

## File Structure

```
newsletter-digest/
├── .env                  # Your secrets (git-ignored)
├── .env.example          # Template
├── config.py             # Configuration management
├── gmail_fetcher.py      # Gmail API — fetch + HTML→text
├── summarizer.py         # Claude Haiku — extract + categorize
├── notion_publisher.py   # Notion API — create daily page
├── main.py               # Orchestrator + CLI
├── setup_gmail.py        # One-time Gmail OAuth
├── run_daily.sh          # Cron wrapper
├── requirements.txt      # Python dependencies
├── credentials.json      # Google OAuth creds (git-ignored)
├── token.json            # Gmail auth token (git-ignored, auto-generated)
├── digest.log            # Pipeline logs
└── SETUP.md              # This file
```

## API Call Budget Per Run

| API | Calls | Cost |
|---|---|---|
| Gmail: list messages | 1 | Free |
| Gmail: batch get bodies | 1 | Free |
| Claude Haiku: extraction + synthesis | 1-2 | ~$0.03-0.06 |
| Notion: create page | 1 | Free |
| **Total** | **4-5** | **~$0.05/day** |
