#!/usr/bin/env python3
"""
One-time setup: Authenticate with Gmail and save token.

Run this interactively ONCE to complete the OAuth flow.
It will open a browser window for Google sign-in.
After auth, the token is saved locally for automated use.

Usage:
    python setup_gmail.py
"""

from config import Config
from gmail_fetcher import get_gmail_service


def main():
    print("🔐 Gmail OAuth Setup")
    print("=" * 40)
    print(f"Credentials file: {Config.GMAIL_CREDENTIALS_PATH}")
    print(f"Token will be saved to: {Config.GMAIL_TOKEN_PATH}")
    print()

    if not Config.GMAIL_CREDENTIALS_PATH.exists():
        print(f"❌ Credentials file not found at {Config.GMAIL_CREDENTIALS_PATH}")
        print()
        print("To get credentials:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a project (or select existing)")
        print("3. Enable the Gmail API")
        print("4. Go to Credentials → Create Credentials → OAuth 2.0 Client ID")
        print("5. Select 'Desktop App' as application type")
        print("6. Download the JSON and save as 'credentials.json' in this folder")
        return

    print("Opening browser for Google sign-in...")
    print("(If no browser opens, copy the URL from the terminal)")
    print()

    try:
        service = get_gmail_service()

        # Verify by fetching labels
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        label_names = [l["name"] for l in labels]

        print(f"\n✅ Authentication successful!")
        print(f"Token saved to: {Config.GMAIL_TOKEN_PATH}")
        print(f"\nFound {len(labels)} labels in your Gmail.")

        # Check if the Newsletter label exists
        if Config.GMAIL_LABEL in label_names:
            print(f"✅ Label '{Config.GMAIL_LABEL}' found!")
        else:
            print(f"⚠️  Label '{Config.GMAIL_LABEL}' NOT found.")
            print(f"   Available labels: {', '.join(sorted(label_names))}")
            print(f"   Create the label in Gmail or update GMAIL_LABEL in .env")

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        raise


if __name__ == "__main__":
    main()
