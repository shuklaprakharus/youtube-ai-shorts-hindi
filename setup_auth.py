#!/usr/bin/env python3
"""
setup_auth.py  —  Run this ONCE on your local machine.
=======================================================
This script opens a browser so you can log in with your YouTube account
and grant upload permission. It then prints a JSON blob you save as a
GitHub Secret (YOUTUBE_CREDENTIALS). After that, everything runs
automatically in the cloud — no browser, no manual steps.

Prerequisites (run first):
  pip install google-auth-oauthlib google-api-python-client

You also need a client_secrets.json file in this folder.
Get it from: https://console.cloud.google.com/
  → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Desktop App)
  → Download JSON → rename to client_secrets.json
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("\n" + "="*62)
    print("  YouTube OAuth Setup — run this once, never again")
    print("="*62)
    print("\nA browser window will open. Log in and click Allow.\n")

    flow  = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent",
                                  access_type="offline")

    creds_json = creds.to_json()

    print("\n" + "="*62)
    print("✅  Done!  Copy everything between the lines below and")
    print("   save it as a GitHub Secret named: YOUTUBE_CREDENTIALS")
    print("="*62 + "\n")
    print(creds_json)
    print("\n" + "="*62)
    print("Once saved, delete client_secrets.json from your computer.")
    print("="*62 + "\n")

if __name__ == "__main__":
    main()
