import subprocess
from pathlib import Path

from autopilot.models import VisualAsset


class FFmpegRenderer:
    def __init__(self, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe"):
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary

    def probe_duration(self, media_path: Path) -> float:
        command = [
            self.ffprobe_binary,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return max(0.1, float(result.stdout.strip()))

    def render(
        self,
        audio_path: Path,
        output_path: Path,
        *,
        vertical: bool,
        captions_path: Path | None,
        visual_assets: list[VisualAsset],
        clip_seconds: float = 2.8,
        scene_word_counts: list[int] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = self.probe_duration(audio_path)
        if visual_assets:
            video_track = self._build_visual_track(
                visual_assets,
                output_path.parent,
                duration,
                vertical=vertical,
                clip_seconds=clip_seconds,
                scene_word_counts=scene_word_counts,
            )
            self._mux(video_track, audio_path, output_path, captions_path=captions_path, vertical=vertical)
        else:
            self._fallback(audio_path, output_path, duration, vertical=vertical, captions_path=captions_path)
        return output_path

    def _build_visual_track(
        self,
        assets: list[VisualAsset],
        workdir: Path,
        duration: float,
        *,
        vertical: bool,
        clip_seconds: float,
        scene_word_counts: list[int] | None,
    ) -> Path:
        width, height = (1080, 1920) if vertical else (1920, 1080)
        timeline = self._timeline(assets, duration, scene_word_counts, clip_seconds)
        segments: list[Path] = []

        for index, (asset, segment_seconds) in enumerate(timeline):
            segment = workdir / f"segment-{index:02d}.mp4"
            safe_duration = max(1.0, segment_seconds)
            fade_out = max(0.1, safe_duration - 0.14)
            command = [self.ffmpeg_binary, "-y"]

            if asset.asset_kind == "image":
                command += ["-loop", "1", "-i", str(asset.local_path)]
                # Browser captures and branded cards get a slow push-in so they
                # feel like edited video rather than a static slideshow.
                frames = max(30, int(safe_duration * 30))
                vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"zoompan=z='min(zoom+0.00065,1.045)':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:"
                    f"s={width}x{height}:fps=30,"
                    f"fade=t=in:st=0:d=0.10,fade=t=out:st={fade_out:.2f}:d=0.14,"
                    "format=yuv420p"
                )
            else:
                source_duration = self.probe_duration(asset.local_path)
                if source_duration < safe_duration:
                    command += ["-stream_loop", "-1"]
                command += ["-i", str(asset.local_path)]
                vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    "eq=contrast=1.04:saturation=1.05:brightness=-0.01,"
                    f"fade=t=in:st=0:d=0.10,fade=t=out:st={fade_out:.2f}:d=0.14,"
                    "fps=30,format=yuv420p"
                )

            command += [
                "-t", f"{safe_duration:.3f}",
                "-an", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-pix_fmt", "yuv420p", str(segment),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True)
                segments.append(segment)
            except subprocess.CalledProcessError:
                segment.unlink(missing_ok=True)

        if not segments:
            raise RuntimeError("No visual scenes could be normalized by FFmpeg.")

        concat_file = workdir / "visuals.txt"
        lines = []
        for segment in segments:
            safe = segment.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{safe}'")
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        track = workdir / "visual-track.mp4"
        command = [
            self.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-t", str(duration), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(track),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return track

    @staticmethod
    def _timeline(
        assets: list[VisualAsset],
        duration: float,
        scene_word_counts: list[int] | None,
        fallback_seconds: float,
    ) -> list[tuple[VisualAsset, float]]:
        if not scene_word_counts:
            return [(asset, fallback_seconds) for asset in assets]

        indexed = {asset.scene_index: asset for asset in assets if asset.scene_index is not None}
        if not indexed:
            return [(asset, fallback_seconds) for asset in assets]

        available = sorted(indexed)
        total_words = max(1, sum(max(1, count) for count in scene_word_counts))
        raw = [duration * max(1, count) / total_words for count in scene_word_counts]
        minimum = 1.35
        adjusted = [max(minimum, value) for value in raw]
        scale = duration / max(0.1, sum(adjusted))
        adjusted = [value * scale for value in adjusted]

        timeline: list[tuple[VisualAsset, float]] = []
        for scene_index, seconds in enumerate(adjusted):
            asset = indexed.get(scene_index)
            if asset is None:
                nearest = min(available, key=lambda value: abs(value - scene_index))
                asset = indexed[nearest]
            timeline.append((asset, seconds))
        return timeline

    def _caption_filter(self, captions_path: Path, *, vertical: bool) -> str:
        font_size = 20 if vertical else 18
        margin = 150 if vertical else 70
        style = (
            f"FontName=DejaVu Sans,FontSize={font_size},Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
            f"BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={margin}"
        )
        return f"subtitles='{self._filter_path(captions_path)}':force_style='{style}'"

    def _mux(
        self,
        video_track: Path,
        audio_path: Path,
        output_path: Path,
        *,
        captions_path: Path | None,
        vertical: bool,
    ) -> None:
        command = [self.ffmpeg_binary, "-y", "-i", str(video_track), "-i", str(audio_path)]
        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            command += ["-vf", self._caption_filter(captions_path, vertical=vertical)]
        command += [
            "-map", "0:v:0", "-map", "1:a:0", "-shortest", "-c:v", "libx264",
            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "192k", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-movflags", "+faststart", str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True)

    def _fallback(
        self,
        audio_path: Path,
        output_path: Path,
        duration: float,
        *,
        vertical: bool,
        captions_path: Path | None,
    ) -> None:
        size = "1080x1920" if vertical else "1920x1080"
        command = [
            self.ffmpeg_binary, "-y", "-f", "lavfi", "-i",
            f"color=c=0x0B1020:s={size}:r=30:d={duration}", "-i", str(audio_path),
        ]
        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            command += ["-vf", self._caption_filter(captions_path, vertical=vertical)]
        command += [
            "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-movflags", "+faststart",
            str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True)

    @staticmethod
    def _filter_path(path: Path) -> str:
        return path.resolve().as_posix().replace(":", "\\:").replace("'", "\\'")

    def render_simple(self, audio_path: Path, output_path: Path, vertical: bool = True) -> Path:
        return self.render(
            audio_path,
            output_path,
            vertical=vertical,
            captions_path=None,
            visual_assets=[],
        )
