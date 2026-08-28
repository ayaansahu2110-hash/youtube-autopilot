# YouTube Autopilot

A modular, automation-first pipeline for producing original faceless YouTube content.

## Goal

Research a topic -> create an original script -> synthesize narration -> render video -> generate metadata -> upload to YouTube -> later feed analytics back into topic selection.

The project starts in **safe dry-run mode**. Real YouTube uploads stay disabled until OAuth is configured and `ENABLE_UPLOADS=true` is set explicitly.

## Principles

- Original content only; do not clone or lightly rewrite other creators' videos.
- Secrets never enter Git.
- Provider adapters keep LLM, TTS, visuals, and analytics replaceable.
- Every stage produces inspectable artifacts.
- Uploads default to `private`.

## Quick start

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -e .[dev]
copy .env.example .env
python -m autopilot.cli doctor
python -m autopilot.cli run --dry-run
```

## Pipeline

1. Topic discovery and scoring
2. Fact/research pack
3. Script + hook + shot plan
4. Voice generation
5. Visual sourcing/generation
6. FFmpeg rendering and captions
7. Title/description/tags/thumbnail brief
8. Quality + copyright/reuse checks
9. YouTube OAuth upload
10. Analytics-driven feedback loop

## YouTube authentication

Use a Google Cloud OAuth **Desktop app** credential and enable the YouTube Data API v3. The app requests upload + read-only analytics scopes so a single consent flow can publish and later learn from channel performance. Keep the downloaded client JSON outside the repository and point `YOUTUBE_CLIENT_SECRETS_FILE` to it.

## Current status

Implemented foundation plus production core:

- Typed `.env` configuration and secret protection
- Persistent topic/video history
- Automated Google News RSS trend discovery
- Multi-source research packs
- OpenAI-backed script planner with no-key fallback mode
- Edge TTS narration adapter
- Pexels stock-video provider with attribution support
- Caption and thumbnail generators
- Originality/quality gate
- FFmpeg rendering adapter
- Guarded YouTube OAuth uploader
- YouTube Analytics feedback client
- Dry-run and render pipeline
- Daily scheduler CLI
- Pytest safety tests and GitHub Actions CI

Next: connect these modules into the production runner, add resilient uploads/thumbnails, cloud daily workflow, and one-time credential setup instructions.
