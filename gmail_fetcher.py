"""Gmail API integration for fetching newsletters.

Efficiency strategy:
- 1 API call to list message IDs matching label + date filter
- 1 batch API call to fetch all message bodies
- Local HTML→text conversion (zero API calls)
"""

import base64
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import Config

logger = logging.getLogger(__name__)

# Read-only Gmail access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Authenticate and return Gmail API service. Reuses cached token."""
    creds = None

    if Config.GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(Config.GMAIL_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth flow (first time setup)...")
            flow = InstalledAppFlow.from_client_secrets_file(str(Config.GMAIL_CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        Config.GMAIL_TOKEN_PATH.write_text(creds.to_json())
        logger.info(f"Token saved to {Config.GMAIL_TOKEN_PATH}")

    return build("gmail", "v1", credentials=creds)


def _html_to_text(html: str) -> str:
    """Convert HTML email body to clean plain text. Zero API calls."""
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, and tracking elements
    for tag in soup(["script", "style", "img", "meta", "link", "noscript"]):
        tag.decompose()

    # Remove tracking pixels and tiny images
    for img in soup.find_all("img"):
        img.decompose()

    # Get text with reasonable whitespace
    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]  # Remove empty lines

    # Deduplicate consecutive identical lines (common in newsletters)
    deduped = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return "\n".join(deduped)


def _extract_body(payload: dict) -> str:
    """Recursively extract text/html or text/plain from email payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    # Direct body
    if body_data and mime_type in ("text/html", "text/plain"):
        decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        if mime_type == "text/html":
            return _html_to_text(decoded)
        return decoded

    # Multipart — prefer HTML over plain text
    parts = payload.get("parts", [])
    html_body = ""
    plain_body = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data", "")

        if part_mime == "text/html" and part_data:
            decoded = base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
            html_body = _html_to_text(decoded)
        elif part_mime == "text/plain" and part_data:
            plain_body = base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part_mime.startswith("multipart/"):
            # Recurse into nested multipart
            nested = _extract_body(part)
            if nested:
                html_body = html_body or nested

    return html_body or plain_body


def _get_header(headers: list, name: str) -> str:
    """Extract a header value by name."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_date(headers: list) -> Optional[str]:
    """Parse the Date header into ISO format."""
    date_str = _get_header(headers, "Date")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return None


def fetch_newsletters(date: Optional[datetime] = None) -> list[dict]:
    """
    Fetch newsletters from Gmail for a given date.

    Args:
        date: Date to fetch newsletters for. Defaults to yesterday.

    Returns:
        List of dicts with keys: subject, sender, date, body, message_id
    """
    if date is None:
        date = datetime.now() - timedelta(days=1)

    # Date range: target day 00:00 to next day 00:00
    after_epoch = int(date.replace(hour=0, minute=0, second=0).timestamp())
    before_epoch = int((date + timedelta(days=1)).replace(hour=0, minute=0, second=0).timestamp())

    service = get_gmail_service()

    # --- API Call 1: List message IDs ---
    query = f"label:{Config.GMAIL_LABEL} after:{after_epoch} before:{before_epoch}"
    logger.info(f"Gmail query: {query}")

    message_ids = []
    page_token = None

    while True:
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=Config.MAX_NEWSLETTERS,
            pageToken=page_token,
        ).execute()

        messages = result.get("messages", [])
        message_ids.extend([m["id"] for m in messages])

        page_token = result.get("nextPageToken")
        if not page_token or len(message_ids) >= Config.MAX_NEWSLETTERS:
            break

    if not message_ids:
        logger.info("No newsletters found for this date.")
        return []

    logger.info(f"Found {len(message_ids)} newsletters. Fetching bodies...")

    # --- API Call 2: Batch fetch message bodies ---
    # Use batch API for efficiency (single HTTP request, up to 100 messages)
    newsletters = []

    def _callback(request_id, response, exception):
        if exception:
            logger.warning(f"Failed to fetch message {request_id}: {exception}")
            return

        headers = response.get("payload", {}).get("headers", [])
        subject = _get_header(headers, "Subject")
        sender = _get_header(headers, "From")
        date_iso = _parse_date(headers)
        body = _extract_body(response.get("payload", {}))

        if not body or len(body.strip()) < 50:
            logger.warning(f"Skipping empty/tiny newsletter: {subject}")
            return

        newsletters.append({
            "subject": subject,
            "sender": sender,
            "date": date_iso,
            "body": body[:15000],  # Cap individual newsletter at ~15K chars (~3.7K tokens)
            "message_id": response["id"],
        })

    batch = service.new_batch_http_request(callback=_callback)
    for msg_id in message_ids[:Config.MAX_NEWSLETTERS]:
        batch.add(
            service.users().messages().get(
                userId="me",
                id=msg_id,
                format="full",
            )
        )
    batch.execute()

    logger.info(f"Successfully fetched {len(newsletters)} newsletters.")

    # Deduplicate by subject (some senders double-send)
    seen_subjects = set()
    unique = []
    for nl in newsletters:
        key = nl["subject"].lower().strip()
        if key not in seen_subjects:
            seen_subjects.add(key)
            unique.append(nl)

    logger.info(f"After dedup: {len(unique)} unique newsletters.")
    return unique
