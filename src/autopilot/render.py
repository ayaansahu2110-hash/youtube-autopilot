import math
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
        clip_seconds: float = 5.0,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = self.probe_duration(audio_path)
        if visual_assets:
            video_track = self._build_visual_track(
                visual_assets, output_path.parent, duration, vertical=vertical, clip_seconds=clip_seconds
            )
            self._mux(video_track, audio_path, output_path, captions_path=captions_path)
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
    ) -> Path:
        width, height = (1080, 1920) if vertical else (1920, 1080)
        segments: list[Path] = []
        for index, asset in enumerate(assets):
            segment = workdir / f"segment-{index:02d}.mp4"
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps=30,format=yuv420p"
            )
            command = [
                self.ffmpeg_binary, "-y", "-i", str(asset.local_path), "-t", str(clip_seconds),
                "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                str(segment),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True)
                segments.append(segment)
            except subprocess.CalledProcessError:
                segment.unlink(missing_ok=True)
        if not segments:
            raise RuntimeError("No downloaded visual clips could be normalized by FFmpeg.")

        repeat = max(1, math.ceil(duration / max(1.0, len(segments) * clip_seconds)) + 1)
        concat_file = workdir / "visuals.txt"
        lines = []
        for _ in range(repeat):
            for segment in segments:
                safe = segment.resolve().as_posix().replace("'", "'\\''")
                lines.append(f"file '{safe}'")
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        track = workdir / "visual-track.mp4"
        command = [
            self.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-t", str(duration), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", str(track),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return track

    def _mux(self, video_track: Path, audio_path: Path, output_path: Path, *, captions_path: Path | None) -> None:
        command = [self.ffmpeg_binary, "-y", "-i", str(video_track), "-i", str(audio_path)]
        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            command += ["-vf", f"subtitles='{self._filter_path(captions_path)}'"]
        command += [
            "-map", "0:v:0", "-map", "1:a:0", "-shortest", "-c:v", "libx264",
            "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "192k", "-movflags", "+faststart", str(output_path),
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
            f"color=c=0x111827:s={size}:r=30:d={duration}", "-i", str(audio_path),
        ]
        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            command += ["-vf", f"subtitles='{self._filter_path(captions_path)}'"]
        command += [
            "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
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
