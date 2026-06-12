#!/usr/bin/env python3
"""
Create the Google Cloud Storage bucket used to archive daily song runs.

Run once after authenticating locally with Google Cloud credentials:
  python create_bucket.py --bucket YOUR-UNIQUE-BUCKET --project YOUR_PROJECT_ID
"""

import argparse

from google.cloud import storage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True, help="Globally unique GCS bucket name")
    parser.add_argument("--project", required=True, help="Google Cloud project ID")
    parser.add_argument("--location", default="US", help="Bucket location, e.g. US or us-central1")
    args = parser.parse_args()

    client = storage.Client(project=args.project)
    bucket = storage.Bucket(client, name=args.bucket)
    bucket.storage_class = "STANDARD"
    created = client.create_bucket(bucket, location=args.location)
    print(f"Created gs://{created.name} in {args.location}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
