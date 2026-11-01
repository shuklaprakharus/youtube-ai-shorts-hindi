"""
trend_agent.py
==============
Picks today's topic from what Indian viewers are actually watching — ranked by
VIEW COUNT — then grounds it in a Wikipedia article so the script never
invents facts.

Flow:
  1. YouTube Data API `videos.list(chart=mostPopular, regionCode=IN)` returns
     the official most-popular list with real view counts, using the repo's
     existing secrets (see _fetch_most_popular). If none can read it, Gemini
     with Google Search grounding provides an approximate ranking.
  2. Hindi videos are ranked by views and by views-per-hour since upload.
  3. Gemini reads that ranked list and picks the THEME behind the top
     view-getters that we can cover with ORIGINAL, family-friendly,
     non-political content (e.g. a film release driving devotional songs →
     the festival/story behind it). We never remake or reuse anyone's video,
     music, footage or characters. It must name a Wikipedia article.
  4. The Wikipedia REST summary of that article is fetched and becomes the
     only fact source ("wikipedia_quote") for ScriptAgent — the same grounding
     contract history mode uses.

If anything fails (no key, API error, no suitable theme, article missing),
`get_trending_topic()` returns None and main.py falls back to history mode.
"""

import datetime
import json
import os
import re
import urllib.parse

import requests

from agents.gemini_client import generate_json

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_UA = {"User-Agent": "AajKaItihaas/1.1 (educational content)"}


# ─── 1. Most-popular videos in India, with view counts ───────────────────────

def _fetch_most_popular(max_pages: int = 4) -> list[dict]:
    """
    Official most-popular chart with real view counts. Uses the secrets the
    repo already has, in order:
      1. YOUTUBE_API_KEY (optional dedicated key)
      2. GEMINI_API_KEY — a Google Cloud API key; works for YouTube Data API v3
         when that API is enabled on the same project and the key is not
         restricted to Gemini only
      3. YOUTUBE_CREDENTIALS OAuth token (works if it carries a read scope)
    """
    attempts = []
    for name in ("YOUTUBE_API_KEY", "GEMINI_API_KEY"):
        if os.environ.get(name):
            attempts.append((name, {"key": os.environ[name]}, {}))
    token = _oauth_token()
    if token:
        attempts.append(("YOUTUBE_CREDENTIALS", {}, {"Authorization": f"Bearer {token}"}))

    last_err = None
    for name, extra_params, extra_headers in attempts:
        try:
            items = _list_most_popular(extra_params, extra_headers, max_pages)
            print(f"     · Most-popular chart fetched with {name} ({len(items)} videos)")
            return items
        except requests.RequestException as exc:
            last_err = exc
            print(f"     · YouTube chart via {name} failed: {str(exc)[:160]}")
    raise RuntimeError(f"No credential could read the YouTube chart: {last_err}")


def _list_most_popular(extra_params: dict, extra_headers: dict, max_pages: int) -> list[dict]:
    params = {"part": "snippet,statistics", "chart": "mostPopular",
              "regionCode": "IN", "maxResults": 50, **extra_params}
    headers = {**_UA, **extra_headers}
    items, page_token = [], None
    for _ in range(max_pages):
        if page_token:
            params["pageToken"] = page_token
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def _search_grounded_ranking() -> list[dict]:
    """
    Last resort when no credential can read the chart: Gemini with Google
    Search grounding lists today's most-viewed Hindi videos in India. View
    counts here are approximate; the video's FACTS still come only from the
    Wikipedia article chosen later.
    """
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    prompt = (
        "Using Google Search, list up to 25 of the most-viewed Hindi-language YouTube "
        "videos trending in India in the last 3 days (YouTube trending charts, kworb.net, "
        "creatordb.app). Return ONLY a JSON array of objects with keys: title, channel, "
        "views (integer), hours_since_upload (integer, estimate if unknown). No prose."
    )
    resp = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.2),
    )
    m = re.search(r"\[.*\]", resp.text or "", re.DOTALL)
    rows = json.loads(m.group(0)) if m else []
    out = []
    for r in rows:
        try:
            views = int(r.get("views", 0)); hours = max(1, int(r.get("hours_since_upload", 24)))
        except (TypeError, ValueError):
            continue
        out.append({"title": str(r.get("title", ""))[:140], "channel": str(r.get("channel", "")),
                    "category_id": "", "views": views, "views_per_hour": int(views / hours),
                    "hours_since_upload": hours, "url": ""})
    out.sort(key=lambda r: r["views"], reverse=True)
    return out[:30]


def _oauth_token() -> str | None:
    """Use the upload credentials if the user granted a read scope too."""
    raw = os.environ.get("YOUTUBE_CREDENTIALS")
    if not raw:
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        d = json.loads(raw)
        creds = Credentials(None, refresh_token=d.get("refresh_token"),
                            token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
                            client_id=d.get("client_id"), client_secret=d.get("client_secret"))
        creds.refresh(Request())
        return creds.token
    except Exception as exc:  # noqa: BLE001 — any failure just disables this path
        print(f"     · OAuth token for trending unavailable: {exc}")
        return None


def rank_videos(items: list[dict], now: datetime.datetime | None = None, top: int = 30) -> list[dict]:
    """Keep Hindi-language videos, rank by views; attach views-per-hour."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for it in items:
        sn, st = it.get("snippet", {}), it.get("statistics", {})
        title = sn.get("title", "")
        lang = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "").lower()
        if not (lang.startswith("hi") or _DEVANAGARI.search(title)):
            continue
        try:
            views = int(st.get("viewCount", 0))
        except ValueError:
            continue
        try:
            pub = datetime.datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
            hours = max(1.0, (now - pub).total_seconds() / 3600)
        except ValueError:
            hours = 24.0
        rows.append({
            "title": title[:140],
            "channel": sn.get("channelTitle", ""),
            "category_id": sn.get("categoryId", ""),
            "views": views,
            "views_per_hour": int(views / hours),
            "hours_since_upload": int(hours),
            "url": f"https://www.youtube.com/watch?v={it.get('id', '')}",
        })
    rows.sort(key=lambda r: r["views"], reverse=True)
    return rows[:top]


# ─── 2. Gemini picks the theme (ranked list in, Wikipedia article out) ───────

_PICK_PROMPT = """You are the content strategist for a Hindi YouTube channel that
publishes ONE original, AI-generated, family-friendly video a day.

Below are TODAY'S most-popular Hindi videos in India, ranked by VIEW COUNT
(views, views per hour since upload). Today is {today}.

{ranked}

Recently covered topics (do NOT repeat): {recent}

Pick the THEME behind the highest-view videos that we can cover with fully
ORIGINAL content. Examples: devotional songs from a mythological film → the
festival or traditional story behind it; festival songs → the festival's
history/science; a space mission in the news → the mission explained.

HARD RULES:
- Never cover the video itself, its film, its stars, its music or lyrics,
  and never reuse anyone's footage, characters or audio.
- Skip politics, elections, gossip, crime, violence, adult content, gaming
  streams, sports results, breaking news and anything controversial.
- Categories allowed: festival/culture story, science, space, history, facts,
  inspiration, nature.
- The topic MUST be well covered by an existing ENGLISH Wikipedia article;
  give its exact title.
- Religious topics are told respectfully as belief (मान्यता).

Return STRICT JSON only:
{{
  "theme_en": "short English description of the chosen topic",
  "headline_hindi": "6-10 word Hindi hook",
  "wikipedia_title": "Exact English Wikipedia article title",
  "category": "festival | science | space | history | culture | facts | inspiration | nature",
  "why": "one sentence: which ranked videos (with view counts) point to this theme",
  "signal_rank": 1,
  "backup_wikipedia_titles": ["second best article title", "third"]
}}
"""


def _wiki_summary(title: str) -> dict | None:
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
    try:
        r = requests.get(url, headers=_UA, timeout=20)
        if r.status_code != 200:
            return None
        d = r.json()
        if d.get("type") == "disambiguation" or len(d.get("extract", "")) < 200:
            return None
        return d
    except requests.RequestException:
        return None


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in trend pick:\n{raw[:400]}")
    return json.loads(m.group(0))


def get_trending_topic(recent: str = "") -> dict | None:
    """Return a topic payload grounded in Wikipedia, or None to fall back."""
    try:
        ranked = rank_videos(_fetch_most_popular())
    except Exception as exc:  # noqa: BLE001
        print(f"     ⚠️  YouTube chart unavailable: {exc}")
        ranked = []
    if len(ranked) < 5:
        try:
            print("     · Trying Gemini + Google Search for today's most-viewed Hindi videos …")
            ranked = _search_grounded_ranking()
        except Exception as exc:  # noqa: BLE001
            print(f"     ⚠️  Search-grounded ranking failed: {exc}")
            ranked = []
    if len(ranked) < 5:
        print(f"     ⚠️  Only {len(ranked)} Hindi trending videos — falling back.")
        return None

    ranked_text = "\n".join(
        f"{i + 1}. {r['title']} — {r['channel']} — {r['views']:,} views "
        f"({r['views_per_hour']:,}/hr, {r['hours_since_upload']}h old)"
        for i, r in enumerate(ranked)
    )
    today = datetime.date.today()
    try:
        pick = _extract_json(generate_json(
            prompt=_PICK_PROMPT.format(today=today.strftime("%d %B %Y"),
                                       ranked=ranked_text, recent=recent or "none"),
            system_instruction="You are a careful, brand-safe content strategist. Return ONE valid JSON object.",
            max_tokens=900,
        ))
    except Exception as exc:  # noqa: BLE001
        print(f"     ⚠️  Trend pick failed: {exc}")
        return None

    summary = None
    for title in [pick.get("wikipedia_title", "")] + list(pick.get("backup_wikipedia_titles", [])):
        if title and (summary := _wiki_summary(title)):
            break
    if not summary:
        print("     ⚠️  No usable Wikipedia article for the trend pick — falling back.")
        return None

    rank = max(1, min(len(ranked), int(pick.get("signal_rank") or 1)))
    signal = ranked[rank - 1]
    return {
        "mode": "trending",
        "date_iso": today.isoformat(),
        "headline_hindi": pick.get("headline_hindi", ""),
        "main_event_en": pick.get("theme_en", ""),
        "category": pick.get("category", "culture"),
        "wikipedia_title": summary.get("title", ""),
        "wikipedia_url": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "wikipedia_quote": summary.get("extract", "")[:2500],
        "trend_reason": pick.get("why", ""),
        "trend_signal": {k: signal[k] for k in ("title", "views", "views_per_hour", "url")},
        "top_views_snapshot": ranked[:10],
    }
