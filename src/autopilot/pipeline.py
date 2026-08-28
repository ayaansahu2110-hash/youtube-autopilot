import uuid
from pathlib import Path

from autopilot.config import Settings
from autopilot.models import PipelineRun
from autopilot.providers.llm import ScriptPlanner
from autopilot.providers.tts import EdgeTTSProvider
from autopilot.render import FFmpegRenderer
from autopilot.youtube import YouTubeUploader


DEFAULT_TOPIC = "3 AI tools that can save a student time this week"


class AutopilotPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.planner = ScriptPlanner(settings)
        self.tts = EdgeTTSProvider(settings.edge_tts_voice)
        self.renderer = FFmpegRenderer(settings.ffmpeg_binary)
        self.uploader = YouTubeUploader(settings)

    def run(self, *, topic: str | None = None, dry_run: bool = True) -> PipelineRun:
        run_id = uuid.uuid4().hex[:12]
        topic = topic or DEFAULT_TOPIC
        plan = self.planner.create_plan(topic, self.settings.default_video_format)
        result = PipelineRun(run_id=run_id, plan=plan)

        run_dir = self.settings.ensure_artifacts_dir() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"

        if dry_run:
            result.notes.append("Dry run: narration, rendering and upload skipped.")
            self._write_manifest(manifest_path, result)
            return result

        audio_path = self.tts.synthesize(plan.script, run_dir / "voice.mp3")
        video_path = self.renderer.render_simple(
            audio_path,
            run_dir / "video.mp4",
            vertical=plan.format == "short",
        )
        result.video_path = video_path
        result.status = "rendered"

        if self.settings.enable_uploads:
            result.youtube_video_id = self.uploader.upload(video_path, plan)
            result.status = "uploaded"
        else:
            result.notes.append("Video rendered but upload is disabled.")

        self._write_manifest(manifest_path, result)
        return result

    @staticmethod
    def _write_manifest(path: Path, result: PipelineRun) -> None:
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
