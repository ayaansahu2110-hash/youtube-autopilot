import uuid
from pathlib import Path

from autopilot.captions import write_srt
from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.editorial import ByteVexaEditorialSystem
from autopilot.models import PipelineRun, ResearchPack, TopicCandidate
from autopilot.providers.hybrid_visuals import HybridVisualDirector
from autopilot.providers.premium_planner import PremiumScriptPlanner
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
        self.editorial = ByteVexaEditorialSystem()
        self.planner = PremiumScriptPlanner(settings)
        self.tts = EdgeTTSProvider(
            settings.edge_tts_voice,
            rate=settings.edge_tts_rate,
            pitch=settings.edge_tts_pitch,
            volume=settings.edge_tts_volume,
        )
        self.visuals = PexelsVideoProvider(settings.pexels_api_key)
        self.hybrid_visuals = HybridVisualDirector(self.visuals)
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

        # Treat the live YouTube channel as the source of truth for duplicate protection.
        # This runs before discovery for Shorts AND long-form, so a topic already covered
        # in either format is blocked even if local/GitHub history was lost.
        if self.settings.youtube_token_file.exists():
            try:
                self.state.sync_recent_uploads(self.uploader.recent_uploads(limit=40))
            except Exception:
                # Production can continue using persisted history; quality gates remain active.
                pass

        candidate, research = self._candidate_with_research(topic)
        research = self.editorial.enrich(candidate, research)
        plan = self.planner.create_plan(research, chosen_format)
        self._append_research_sources(plan, research)
        quality = self.quality.evaluate(plan, research, strict=not dry_run)
        result = PipelineRun(run_id=run_id, plan=plan, research=research, quality=quality)

        run_dir = self.settings.ensure_artifacts_dir() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        result.metadata["selected_topic_score"] = candidate.score
        result.metadata["research_source_count"] = len(research.sources)
        result.metadata["scene_count"] = len(plan.scenes)

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
                words_per_caption=3 if plan.format == "short" else 6,
            )

            max_clips = (
                self.settings.max_visual_clips_short
                if plan.format == "short"
                else self.settings.max_visual_clips_long
            )
            min_clips = (
                self.settings.min_visual_clips_short
                if plan.format == "short"
                else self.settings.min_visual_clips_long
            )

            if plan.scenes:
                assets = self.hybrid_visuals.build_assets(
                    plan.scenes,
                    run_dir / "visuals",
                    vertical=plan.format == "short",
                    allowed_source_urls=plan.source_urls,
                    limit=max_clips,
                )
            else:
                assets = self.visuals.fetch_assets(
                    plan.visual_queries,
                    run_dir / "visuals",
                    vertical=plan.format == "short",
                    limit=max_clips,
                )

            result.metadata["visual_assets"] = len(assets)
            result.metadata["visual_modes"] = {
                mode: sum(1 for asset in assets if asset.visual_mode == mode)
                for mode in ("ui", "motion", "stock")
            }

            if len(assets) < min_clips:
                result.status = "failed"
                result.notes.append(
                    f"Premium visual gate blocked upload: only {len(assets)} usable scenes; need {min_clips}."
                )
                self._write_manifest(manifest_path, result)
                return result

            if plan.scenes:
                covered_scene_indexes = {
                    asset.scene_index for asset in assets if asset.scene_index is not None
                }
                required_coverage = max(min_clips, int(len(plan.scenes) * 0.85))
                if len(covered_scene_indexes) < required_coverage:
                    result.status = "failed"
                    result.notes.append(
                        "Scene-match gate blocked upload: too many narration beats lack their own visual."
                    )
                    self._write_manifest(manifest_path, result)
                    return result

            stock_assets = [asset for asset in assets if asset.visual_mode == "stock"]
            attribution = self.visuals.attribution_lines(stock_assets)
            if attribution:
                plan.description = self._append_section(plan.description, "Visual credits", attribution)

            scene_word_counts = (
                [len(scene.narration.split()) for scene in plan.scenes]
                if plan.scenes
                else None
            )
            video_path = self.renderer.render(
                audio_path,
                run_dir / "video.mp4",
                vertical=plan.format == "short",
                captions_path=captions_path,
                visual_assets=assets,
                clip_seconds=self.settings.visual_clip_seconds,
                scene_word_counts=scene_word_counts,
            )
            thumbnail_path = self.thumbnail.create(
                plan.thumbnail_text,
                run_dir / "thumbnail.jpg",
                title=plan.title,
                brief=plan.thumbnail_brief,
            )
            result.video_path = video_path
            result.thumbnail_path = thumbnail_path
            result.status = "rendered"

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

    def _candidate_with_research(self, topic: str | None) -> tuple[TopicCandidate, ResearchPack]:
        if topic:
            candidate = TopicCandidate(title=topic, score=60, reason="Manual topic override.")
            return candidate, self.researcher.research(candidate)

        candidates = self.discovery.discover()
        if not candidates:
            candidate = TopicCandidate(title=DEFAULT_TOPIC, score=50, reason="Evergreen fallback.")
            return candidate, self.researcher.research(candidate)

        preferred = self.planner.choose_topic(candidates)
        ordered = [preferred]
        ordered.extend(item for item in candidates if item.title != preferred.title)

        best_candidate = preferred
        best_research = self.researcher.research(preferred)
        minimum = self.settings.min_research_sources
        if len(best_research.sources) >= minimum:
            return best_candidate, best_research

        for candidate in ordered[1:8]:
            research = self.researcher.research(candidate)
            if len(research.sources) > len(best_research.sources):
                best_candidate, best_research = candidate, research
            if len(research.sources) >= minimum:
                return candidate, research

        return best_candidate, best_research

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
