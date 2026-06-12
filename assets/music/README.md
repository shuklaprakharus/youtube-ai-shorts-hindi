# Background music beds

Drop royalty-free **instrumental** MP3s here and the pipeline automatically
loops one under the voiceover (at `MUSIC_VOLUME`, see `config.py`) with fade
in/out. No files here → the Short gets the plain voiceover, as before.

## Genre matching

The day's topic JSON has a `category` field (not passed yet); tracks are picked from any subfolder or this folder. If a matching subfolder exists,
a track is picked from it; otherwise any MP3 under this folder is used:

```text
assets/music/
  lofi/
  romantic/
  dance/
  devotional/
  wedding/
  indie/
  pop/
```

The track is chosen deterministically per day, so re-runs on the same day pick
the same track.

## Where to get tracks (free, safe for YouTube)

- **YouTube Audio Library** (studio.youtube.com → Audio Library): filter by
  "Attribution not required". Safest option — zero Content ID risk.
- **Pixabay Music** (pixabay.com/music): free license, no attribution needed.

Avoid anything that requires attribution unless you add the credit to the
video description, and never use commercial songs — Content ID will flag or
demonetize the upload.

Aim for 60s+ instrumentals so the loop point rarely plays; quiet, steady
tracks (lo-fi, ambient, light percussion) sit best under a voice.
