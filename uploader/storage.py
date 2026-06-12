"""
storage.py
==========
Archives generated videos and metadata to Google Cloud Storage.

Uploads use if_generation_match=0 so a run cannot overwrite an existing object.
That keeps daily outputs immutable and makes retry behavior predictable.
"""

import json
import os
from pathlib import Path
from typing import Any

from google.cloud import storage

from config import GCS_BUCKET_NAME, GCS_PREFIX, REQUIRE_GCS_ARCHIVE


def archive_run(video_file: str, metadata: dict[str, Any], run_id: str) -> list[str]:
    metadata_path = Path("output/run_metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not GCS_BUCKET_NAME:
        if REQUIRE_GCS_ARCHIVE:
            raise EnvironmentError(
                "GCS_BUCKET_NAME is not set and REQUIRE_GCS_ARCHIVE=true."
            )
        print("     · GCS_BUCKET_NAME not set; skipping bucket archive.")
        return []

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    date_part = metadata.get("date") or metadata.get("topic_date") or "unknown-date"
    prefix = f"{GCS_PREFIX}/{date_part}/{run_id}"

    uploads = [
        (video_file, f"{prefix}/final_video.mp4", "video/mp4"),
        (str(metadata_path), f"{prefix}/run_metadata.json", "application/json"),
    ]

    archived = []
    for local_path, object_name, content_type in uploads:
        if not os.path.exists(local_path):
            continue
        blob = bucket.blob(object_name)
        blob.upload_from_filename(
            local_path,
            content_type=content_type,
            if_generation_match=0,
        )
        uri = f"gs://{GCS_BUCKET_NAME}/{object_name}"
        print(f"     → Archived: {uri}")
        archived.append(uri)
    return archived
