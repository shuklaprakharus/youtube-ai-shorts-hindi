"""
Preflight checks for GitHub Actions and local runs.
Fail early if required secrets are missing or malformed.
"""

import json
import os


def validate_environment(require_youtube: bool = True) -> None:
    missing = []
    for name in ["GEMINI_API_KEY"]:
        if not os.environ.get(name):
            missing.append(name)

    if require_youtube and not os.environ.get("YOUTUBE_CREDENTIALS"):
        missing.append("YOUTUBE_CREDENTIALS")

    if os.environ.get("REQUIRE_GCS_ARCHIVE", "false").lower() == "true":
        for name in ["GCS_BUCKET_NAME", "GOOGLE_APPLICATION_CREDENTIALS_JSON"]:
            if not os.environ.get(name):
                missing.append(name)

    if missing:
        raise EnvironmentError(
            "Missing required environment variables: " + ", ".join(sorted(set(missing)))
        )

    raw_youtube = os.environ.get("YOUTUBE_CREDENTIALS")
    if raw_youtube:
        data = json.loads(raw_youtube)
        required = ["refresh_token", "client_id", "client_secret", "token_uri"]
        absent = [key for key in required if not data.get(key)]
        if absent:
            raise EnvironmentError(
                "YOUTUBE_CREDENTIALS JSON is missing: " + ", ".join(absent)
            )

    raw_google_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw_google_creds:
        creds_path = "output/google_application_credentials.json"
        os.makedirs("output", exist_ok=True)
        json.loads(raw_google_creds)
        with open(creds_path, "w", encoding="utf-8") as f:
            f.write(raw_google_creds)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
