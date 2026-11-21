# Aaj Ka Itihaas — Daily Hindi YouTube Shorts

Automated GitHub Actions pipeline that publishes one Hindi Short every day:

1. **Topic** — `TOPIC_MODE=trending` (default): the YouTube Data API's
   most-popular chart for India is ranked by view count, Gemini picks the
   theme behind the top Hindi view-getters that can be covered with fully
   original, family-friendly content, and that theme is grounded in a
   Wikipedia article. `TOPIC_MODE=history`, or any trending failure: Wikipedia's
   "On this day" API provides the verified events for today's date. Either
   way the LLM never invents facts.
2. Gemini picks the most India-relevant event, writes the Hindi script,
   and generates the title, description, and tags.
3. Edge TTS renders the Hindi narration.
4. AI backgrounds and FFmpeg create a vertical 9:16 MP4 with burned-in
   Hindi subtitles and an "AI Generated" badge in the bottom-right corner of
   every frame.
5. YouTube Data API uploads the Short with resumable upload, with
   `containsSyntheticMedia: true` (YouTube's altered/synthetic disclosure)
   and an AI disclosure line in the description.
6. Optional Google Cloud Storage archiving stores the MP4 and run metadata.

The pipeline is designed so secrets are explicit and stable. If a token or
secret name is wrong, `preflight.py` fails before generation or upload starts.

## Required GitHub Secrets

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Gemini API key for topic picking, script, and SEO metadata |
| `YOUTUBE_CREDENTIALS` | OAuth JSON from `python setup_auth.py` |
| `YOUTUBE_API_KEY` | Optional. Trending mode first tries this, then `GEMINI_API_KEY` (works if YouTube Data API v3 is enabled on its Google Cloud project), then `YOUTUBE_CREDENTIALS`, then Gemini + Google Search |

Repository variable `TOPIC_MODE`: `trending` (default) or `history`.

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

## Kids Rhyme Shorts — पीलू बतख (second workflow)

`.github/workflows/kids_rhyme.yml` publishes one original Hindi nursery-rhyme Short a day
(17:47 IST) as **made for kids**: a 66-second song-story about Peelu the duckling, her mama,
a frog and a fish, ending with a simple lesson.

1. **Episode** — when `GEMINI_API_KEY` is set, Gemini writes a new episode (12 rhyming lines on
   a fixed beat sheet, bubbles, moral card, SEO) that is validated (Devanagari only, line length,
   kid-safe words, structure). Without a key, or if Gemini fails, the next unused hand-written
   episode in `kids/episodes/` is used. Published episodes are recorded in `kids/history.json`
   (committed back by the workflow) so nothing repeats.
2. **Voices** — edge-tts neural voices per character (gTTS + pitch shift as fallback), fitted to a
   100 BPM grid; each line must fit its two-bar slot.
3. **Music & sound effects** — synthesized from scratch (no licensed audio).
4. **Animation** — 3D-shaded characters and a painted pond rendered in Python (`kids/chars.py`,
   `kids/bg.py`, `kids/render.py`), karaoke lyrics, "AI Generated" label on every frame.
5. **Upload** — the existing uploader with `selfDeclaredMadeForKids: true`,
   `containsSyntheticMedia: true` and a custom thumbnail (needs a verified channel).

Episode events available to the animation: `wander` (butterfly lures Peelu away), `rain`
(rain + thunder, she hides) and `treat` (a mango falls, she keeps it to herself).

| Setting (repository variable) | Default | Meaning |
| --- | --- | --- |
| `KIDS_UPLOAD` | `true` | `false` = build only (video kept as a workflow artifact) |
| `KIDS_PRIVACY` | `public` | `public`, `unlisted` or `private` |
| `KIDS_SOURCE` | `auto` | `auto` (Gemini, else library), `library`, `gemini` |

Run it by hand from the Actions tab (**Kids Rhyme Short → Run workflow**); you can force a library
episode (e.g. `ep02_baarish`) and untick *upload* for a test. Local dry run:

```bash
KIDS_UPLOAD=false KIDS_EPISODE=ep02_baarish python -m kids.main   # → output/kids/final_video.mp4
```

Fonts: Baloo 2 and Mukta (SIL Open Font License, see `assets/fonts/`).
