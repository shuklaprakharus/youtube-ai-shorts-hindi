# Aaj Ka Itihaas — Daily Hindi History YouTube Shorts

Automated GitHub Actions pipeline that publishes one Hindi "today in history"
Short every day:

1. Wikipedia's "On this day" API provides the verified list of events for
   today's date — the LLM never invents facts.
2. Gemini picks the most India-relevant event, writes the Hindi script,
   and generates the title, description, and tags.
3. Edge TTS renders the Hindi narration.
4. AI backgrounds and FFmpeg create a vertical 9:16 MP4 with burned-in
   Hindi subtitles.
5. YouTube Data API uploads the Short with resumable upload.
6. Optional Google Cloud Storage archiving stores the MP4 and run metadata.

The pipeline is designed so secrets are explicit and stable. If a token or
secret name is wrong, `preflight.py` fails before generation or upload starts.

## Required GitHub Secrets

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Gemini API key for topic picking, script, and SEO metadata |
| `YOUTUBE_CREDENTIALS` | OAuth JSON from `python setup_auth.py` |

## Optional Bucket Archive Secrets

| Secret or variable | Purpose |
| --- | --- |
| `GCS_BUCKET_NAME` | Existing bucket name for archiving outputs |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Service account JSON with write access to that bucket |
| `REQUIRE_GCS_ARCHIVE` | Repository variable. Set to `true` if bucket archive must succeed |
| `GCS_PREFIX` | Repository variable. Defaults to `youtube-ai-shorts-hindi` |

Bucket uploads use `if_generation_match=0`, so an existing object is never
overwritten by a retry or duplicate job.

## One-Time YouTube Setup

```bash
pip install -r requirements.txt
python setup_auth.py
```

Save the printed JSON as the GitHub Secret `YOUTUBE_CREDENTIALS`.

## Create A New Bucket

Authenticate locally with Google Cloud credentials, then run:

```bash
python create_bucket.py --bucket YOUR-UNIQUE-BUCKET --project YOUR_PROJECT_ID --location US
```

Give your GitHub Actions service account `storage.objects.create` permission on
that bucket, then save the service account JSON as
`GOOGLE_APPLICATION_CREDENTIALS_JSON`.

## Daily Schedule

The workflow runs at `02:30 UTC` daily and can also be started manually from the
GitHub Actions tab.

## Fact Grounding

Topic selection never asks the LLM "what happened today?" — that hallucinates
badly for specific calendar dates. Instead, `topic_agent.py` fetches the
editorially curated event list from Wikipedia's free "On this day" API and asks
Gemini only to *pick* one and write the headline. A validation step checks that
the picked quote actually appears in the Wikipedia data, with a deterministic
fallback if not. Covered events are recorded in `topics.json` (committed back
by the workflow) so the channel doesn't repeat itself.

## Notes

- YouTube uploads use category `27` (Education).
- YouTube Data API projects created after July 28, 2020 may upload videos as
  private until the API project is verified by Google.
