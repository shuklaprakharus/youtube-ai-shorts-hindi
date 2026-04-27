# 🇮🇳 Daily Hindi YouTube Shorts — Aaj Ka Itihaas (आज का इतिहास)

Fully automated daily Hindi YouTube Shorts about **why today's date is significant in Indian history** — picked, scripted, voiced, illustrated and uploaded with zero manual steps after setup.

This is a fork of the English `youtube-ai-shorts` pipeline. **All your existing GitHub Secrets work as-is** (`GROQ_API_KEY` + `YOUTUBE_CREDENTIALS`). No new keys required.

---

## What's different from the English version?

| Step | English version | Hindi version |
|------|-----------------|---------------|
| Topic | Picked from `topics.json` list | Auto-discovered: today's India-relevant date significance |
| Script | English, illustrated explainer style | Hindi (Devanagari) script with `image_prompt` per slide |
| Voiceover | gTTS English | `edge-tts` `hi-IN-SwaraNeural` (warm Hindi female) |
| Slides | Cream + emoji + sparkles (PIL) | AI-generated cinematic backgrounds (Pollinations.ai) + Hindi text overlay |
| Subtitles | Arial (Latin) | Noto Sans Devanagari |
| Category | 28 (Sci/Tech) | 27 (Education) |
| Cron | 14:00 UTC | 02:30 UTC = 8 AM IST |

Everything else (FFmpeg pipeline, Ken Burns, xfade transitions, YouTube Data API uploader, OAuth flow, history tracking) is **identical** to your English version.

---

## Setup (~5 minutes — much shorter than original because secrets are reused)

### Step 1 — Add Devanagari font for local testing (optional)

If you want to run locally, install Noto Sans Devanagari:
- **Ubuntu/Debian:** `sudo apt install fonts-noto-core libraqm-dev`
- **macOS:** `brew install --cask font-noto-sans-devanagari`
- **Or** drop `NotoSansDevanagari-Bold.ttf` into `assets/fonts/` (auto-detected)

GitHub Actions installs the font automatically — no setup needed for the cron run.

### Step 2 — Reuse your existing GitHub Secrets

The workflow expects the same two secrets your English channel already has:

| Secret name | Value |
|-------------|-------|
| `GROQ_API_KEY` | Same key as your English channel |
| `YOUTUBE_CREDENTIALS` | **New** — see below |

**Important:** if you want to upload to a different YouTube channel for the Hindi shorts, you need to re-run `python setup_auth.py` while logged into that channel and save the new JSON blob as `YOUTUBE_CREDENTIALS` in this repo's secrets. If you want to upload to the same channel as the English shorts, just copy the existing secret value over.

### Step 3 — Push and trigger

1. Push this repo to GitHub
2. **Settings → Actions → General → Workflow permissions → Read and write permissions**
3. **Actions tab → "🇮🇳 Daily Hindi YouTube Short" → Run workflow**
4. ~3 minutes later, check YouTube Studio.

---

## Project structure

```
youtube-ai-shorts/
├── .github/workflows/
│   └── daily_video.yml         ← daily cron (UNCHANGED logic, new font install)
├── agents/
│   ├── topic_agent.py          ← MODIFIED: today's India date significance
│   ├── script_agent.py         ← MODIFIED: Hindi script + image_prompt per slide
│   └── seo_agent.py            ← MODIFIED: Hindi/India SEO
├── video/
│   ├── tts.py                  ← MODIFIED: edge-tts hi-IN-SwaraNeural
│   ├── slide_creator.py        ← MODIFIED: AI bg + Hindi overlay
│   └── assembler.py            ← MODIFIED: Hindi font for subtitles
├── uploader/
│   └── youtube.py              ← UNCHANGED
├── main.py                     ← UNCHANGED
├── config.py                   ← MODIFIED: Hindi voice + image gen settings
├── setup_auth.py               ← UNCHANGED
├── topics.json                 ← REPURPOSED: date-history dedup file
└── requirements.txt            ← +edge-tts, +requests
```

---

## Customising

| Want to… | Edit this |
|---|---|
| Change posting time | `cron` in `.github/workflows/daily_video.yml` |
| Change the Hindi voice | `HINDI_VOICE` in `config.py` |
| Use DALL-E instead of free Pollinations | Set `IMAGE_PROVIDER = "dalle"` and add `OPENAI_API_KEY` secret |
| Make voice slower/faster | `VOICE_RATE = "-10%"` etc. |
| Change colour accents | `THEMES` in `config.py` |
| Add your channel branding to slides | Add a draw call in `video/slide_creator.py` `_make_slide()` |

---

## Cost per video

- **Groq (script + topic + SEO):** $0 (well within free tier)
- **edge-tts (voice):** $0 (no API key)
- **Pollinations.ai (5 backgrounds):** $0 (no API key)
- **YouTube Data API:** $0 (10k unit/day free quota)
- **GitHub Actions:** $0 (~3 min/run, well under free 2000 min/month)
- **Total:** **$0/month**

---

## Troubleshooting

**Hindi text shows as boxes (□□□):**
The Devanagari font isn't installed. The GitHub Actions workflow installs `fonts-noto-core` automatically. For local runs, see Step 1 above.

**edge-tts fails with "WebSocket connection rejected":**
Microsoft sometimes rate-limits IPs. The pipeline auto-falls back to gTTS Hindi.

**Pollinations.ai slow / times out:**
First request to a prompt takes ~30-60s on a cold queue. The pipeline retries 3× with exponential backoff. Switch to DALL-E if it consistently fails (`IMAGE_PROVIDER = "dalle"` in `config.py`).

**Topic agent picks the same event two days in a row:**
Check `topics.json` — the `history` array should be growing daily. The workflow auto-commits it back to the repo. If your repo doesn't have write permission for Actions, run **Settings → Actions → General → Workflow permissions → Read and write**.

**Script agent JSON parse error:**
`json-repair` should catch most cases. If it persists, it's usually because Groq is overloaded. Re-run the workflow.
