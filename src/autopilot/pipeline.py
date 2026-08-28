import uuid
from pathlib import Path

from autopilot.captions import write_srt
from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.models import PipelineRun, ResearchPack, TopicCandidate
from autopilot.providers.llm import ScriptPlanner
from autopilot.providers.tts import EdgeTTSProvider
from autopilot.providers.visuals import PexelsVideoProvider
from autopilot.quality import QualityGate
from autopilot.render import FFmpegRenderer
from autopilot.research import Researcher
from autopilot.state import StateStore
from autopilot.thumbnail import ThumbnailGenerator
from autopilot.youtube import YouTubeUploader


DEFAULT_TOPIC = "A useful AI workflow most people are underusing"


class AutopilotPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = StateStore(settings.state_file)
        self.discovery = TopicDiscovery(settings, self.state)
        self.researcher = Researcher(settings)
        self.planner = ScriptPlanner(settings)
        self.tts = EdgeTTSProvider(settings.edge_tts_voice)
        self.visuals = PexelsVideoProvider(settings.pexels_api_key)
        self.renderer = FFmpegRenderer(settings.ffmpeg_binary, settings.ffprobe_binary)
        self.thumbnail = ThumbnailGenerator()
        self.quality = QualityGate(settings, self.state)
        self.uploader = YouTubeUploader(settings)

    def run(
        self,
        *,
        topic: str | None = None,
        dry_run: bool = True,
        video_format: str | None = None,
    ) -> PipelineRun:
        run_id = uuid.uuid4().hex[:12]
        chosen_format = video_format or self.settings.default_video_format
        candidate = self._candidate(topic)
        research = self.researcher.research(candidate)
        plan = self.planner.create_plan(research, chosen_format)
        self._append_research_sources(plan, research)
        quality = self.quality.evaluate(plan, research, strict=not dry_run)
        result = PipelineRun(run_id=run_id, plan=plan, research=research, quality=quality)

        run_dir = self.settings.ensure_artifacts_dir() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"

        if dry_run:
            result.notes.append("Dry run: research/plan completed; narration, rendering and upload skipped.")
            self._write_manifest(manifest_path, result)
            return result

        if not quality.passed:
            result.status = "failed"
            result.notes.extend(quality.errors)
            self._write_manifest(manifest_path, result)
            return result

        try:
            audio_path = self.tts.synthesize(plan.script, run_dir / "voice.mp3")
            duration = self.renderer.probe_duration(audio_path)
            captions_path = write_srt(
                plan.script,
                duration,
                run_dir / "captions.srt",
                words_per_caption=4 if plan.format == "short" else 7,
            )
            max_clips = (
                self.settings.max_visual_clips_short
                if plan.format == "short"
                else self.settings.max_visual_clips_long
            )
            assets = self.visuals.fetch_assets(
                plan.visual_queries,
                run_dir / "visuals",
                vertical=plan.format == "short",
                limit=max_clips,
            )
            attribution = self.visuals.attribution_lines(assets)
            if attribution:
                plan.description = self._append_section(plan.description, "Visual credits", attribution)
            video_path = self.renderer.render(
                audio_path,
                run_dir / "video.mp4",
                vertical=plan.format == "short",
                captions_path=captions_path,
                visual_assets=assets,
                clip_seconds=self.settings.visual_clip_seconds,
            )
            thumbnail_path = self.thumbnail.create(plan.thumbnail_text, run_dir / "thumbnail.jpg")
            result.video_path = video_path
            result.thumbnail_path = thumbnail_path
            result.status = "rendered"
            result.metadata["visual_assets"] = len(assets)

            if self.settings.enable_uploads:
                result.youtube_video_id = self.uploader.upload(video_path, plan, thumbnail_path)
                result.status = "uploaded"
                self.state.record_run(result)
            else:
                result.notes.append("Video rendered but upload is disabled.")
        except Exception as exc:
            result.status = "failed"
            result.notes.append(f"Production failed safely: {type(exc).__name__}: {exc}")

        self._write_manifest(manifest_path, result)
        return result

    def _candidate(self, topic: str | None) -> TopicCandidate:
        if topic:
            return TopicCandidate(title=topic, score=60, reason="Manual topic override.")
        candidates = self.discovery.discover()
        if not candidates:
            return TopicCandidate(title=DEFAULT_TOPIC, score=50, reason="Evergreen fallback.")
        return self.planner.choose_topic(candidates)

    @staticmethod
    def _append_research_sources(plan, research: ResearchPack) -> None:
        lines = []
        seen: set[str] = set()
        for source in research.sources:
            if source.url and source.url not in seen:
                seen.add(source.url)
                lines.append(f"{source.publisher or source.title}: {source.url}")
        if lines:
            plan.description = AutopilotPipeline._append_section(plan.description, "Research sources", lines)

    @staticmethod
    def _append_section(description: str, heading: str, lines: list[str]) -> str:
        section = heading + ":\n" + "\n".join(f"- {line}" for line in lines)
        return (description.rstrip() + "\n\n" + section).strip()[:5000]

    @staticmethod
    def _write_manifest(path: Path, result: PipelineRun) -> None:
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
