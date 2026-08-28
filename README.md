# YouTube Autopilot

An automation-first system for producing **original** faceless YouTube content without copying other creators.

## What it does

`trend discovery -> multi-source research -> topic selection -> original script -> AI voice -> stock visuals -> captions -> thumbnail -> quality gate -> YouTube upload -> analytics feedback`

The production schedule is **one Short every day plus one long-form video on Monday, Wednesday and Friday**. The schedule can be changed in `.env`.

## Safety defaults

- Uploading is off locally unless `ENABLE_UPLOADS=true`.
- Cloud uploads start as **private**.
- Public publishing has a second lock: `ALLOW_PUBLIC_UPLOADS=true`.
- Secrets and OAuth tokens stay out of Git.
- Recent-topic history prevents repeated/repackaged videos.
- Scripts are grounded in multiple research sources and are instructed not to imitate creators.
- Pexels footage is attributed in the video description when used.

## Local commands

```bash
python -m autopilot.cli doctor
python -m autopilot.cli auth-youtube
python -m autopilot.cli run --dry-run
python -m autopilot.cli run --render --format short
python -m autopilot.cli daily
python -m autopilot.cli daily --live
python -m autopilot.cli analytics
```

## Unattended cloud operation

`.github/workflows/daily.yml` runs every day in GitHub Actions at approximately 18:00 Asia/Kolkata. It safely skips production until the required repository secrets exist, then renders/uploads the daily content and commits only non-secret topic/analytics history back to `state/history.json`.

See [`docs/SETUP.md`](docs/SETUP.md) for the one-time account authorization steps.

## Architecture

- `discovery.py` — fresh topic signals and repeat avoidance
- `research.py` — multi-source research packs
- `providers/llm.py` — original grounded script/topic planning
- `providers/tts.py` — narration
- `providers/visuals.py` — Pexels stock-video sourcing
- `captions.py` — timed subtitles
- `render.py` — FFmpeg assembly
- `thumbnail.py` — automatic 1280x720 thumbnails
- `quality.py` — originality/production gates
- `youtube.py` — OAuth, resumable upload, thumbnails
- `analytics.py` — YouTube performance feedback
- `state.py` — persistent history and performance terms

## Current stage

The code path for the complete automated workflow is implemented. The remaining blocker is account-specific: add the OpenAI/Pexels credentials, perform one YouTube OAuth consent flow, place encoded OAuth files in GitHub Actions secrets, and run the first private cloud test.
