import subprocess
import tempfile
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

    def normalize_short_voice_duration(
        self,
        audio_path: Path,
        duration: float,
        *,
        max_seconds: float = 64.5,
        max_speedup: float = 1.15,
    ) -> float:
        """Apply a mild tempo correction with room for MP3 encoder padding."""
        if duration <= max_seconds:
            return duration
        speed = duration / max_seconds
        if speed > max_speedup:
            return duration

        with tempfile.NamedTemporaryFile(
            suffix=audio_path.suffix,
            dir=audio_path.parent,
            delete=False,
        ) as handle:
            normalized_path = Path(handle.name)
        try:
            subprocess.run(
                [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(audio_path),
                    "-filter:a",
                    f"atempo={speed:.6f}",
                    "-vn",
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(normalized_path),
                ],
                check=True,
                capture_output=True,
            )
            normalized_path.replace(audio_path)
        finally:
            normalized_path.unlink(missing_ok=True)
        return self.probe_duration(audio_path)

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
        scene_labels: list[str] | None = None,
        facts_style: bool = False,
        channel_profile: str = "bytevexa",
        bgm_path: Path | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = self.probe_duration(audio_path)

        # Ambient background music generator to enrich video audio production
        if not bgm_path:
            bgm_candidate = output_path.parent / "ambient_bgm.wav"
            try:
                bgm_path = self._generate_ambient_bgm(
                    bgm_candidate, duration=duration, channel_profile=channel_profile
                )
            except Exception:
                bgm_path = None

        if visual_assets:
            video_track = self._build_visual_track(
                visual_assets,
                output_path.parent,
                duration,
                vertical=vertical,
                clip_seconds=clip_seconds,
                scene_word_counts=scene_word_counts,
                scene_labels=scene_labels,
                facts_style=facts_style,
            )
            self._mux(
                video_track,
                audio_path,
                output_path,
                captions_path=captions_path,
                vertical=vertical,
                bgm_path=bgm_path,
            )
        else:
            self._fallback(
                audio_path,
                output_path,
                duration,
                vertical=vertical,
                captions_path=captions_path,
                bgm_path=bgm_path,
            )
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
        scene_labels: list[str] | None,
        facts_style: bool,
    ) -> Path:
        # Shorts stay at native 1080x1920. Long-form is rendered at 1440p so
        # browser text and UI survive YouTube transcoding more cleanly.
        width, height = (1080, 1920) if vertical else (1920, 1080)
        timeline = self._timeline(assets, duration, scene_word_counts, clip_seconds)
        # CurioAxiom provides one unique asset per short scene. Do not split a
        # scene into repeated copies of the same still or clip to fill time.
        segments: list[Path] = []

        for index, (asset, segment_seconds) in enumerate(timeline):
            segment = workdir / f"segment-{index:02d}.mp4"
            safe_duration = max(1.0, segment_seconds)
            fade_out = max(0.1, safe_duration - 0.14)
            command = [self.ffmpeg_binary, "-y"]

            if asset.asset_kind == "image":
                command += ["-loop", "1", "-i", str(asset.local_path)]
                frames = max(30, int(safe_duration * 30))
                motion = index % 4
                zoom = "min(zoom+0.0022,1.16)" if motion != 3 else "if(eq(on,1),1.15,max(1.0,zoom-0.0018))"
                x = "iw/2-(iw/zoom/2)" if motion < 2 else "(iw-iw/zoom)*on/duration"
                vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={width}:{height},"
                    f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:"
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
                    f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={width}:{height},"
                    "eq=contrast=1.04:saturation=1.05:brightness=-0.01,"
                    f"fade=t=in:st=0:d=0.10,fade=t=out:st={fade_out:.2f}:d=0.14,"
                    "fps=30,format=yuv420p"
                )

            if facts_style:
                label = ""
                if scene_labels and asset.scene_index is not None and asset.scene_index < len(scene_labels):
                    label = scene_labels[asset.scene_index]
                vf += self._fact_overlay(label)

            command += [
                "-t", f"{safe_duration:.3f}",
                "-an", "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
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
            "-t", str(duration), "-c", "copy", str(track),
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

    @staticmethod
    def _rapid_timeline(
        timeline: list[tuple[VisualAsset, float]], *, max_seconds: float
    ) -> list[tuple[VisualAsset, float]]:
        rapid: list[tuple[VisualAsset, float]] = []
        for asset, seconds in timeline:
            parts = max(1, int((seconds + max_seconds - 0.001) // max_seconds))
            for _ in range(parts):
                rapid.append((asset, seconds / parts))
        return rapid

    @staticmethod
    def _fact_overlay(label: str) -> str:
        safe = (label or "VERIFIED FACT").upper().replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        safe = " ".join(safe.split())[:34]
        font_spec = "font='Arial'"
        for font_candidate in (
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ):
            if font_candidate.exists():
                escaped_path = font_candidate.as_posix().replace(":", r"\:")
                font_spec = f"fontfile='{escaped_path}'"
                break
        return (
            ",drawbox=x=0:y=120:w=iw:h=116:color=0xF6C90E@0.96:t=fill"
            f",drawtext=text='{safe}':fontcolor=0x111111:fontsize=52:{font_spec}:"
            "x=(w-text_w)/2:y=151:borderw=1:bordercolor=0x111111"
        )

    def _caption_filter(self, captions_path: Path, *, vertical: bool) -> str:
        if vertical:
            style = (
                "PlayResX=1080,PlayResY=1920,FontName=Segoe UI,FontSize=56,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=5,Shadow=1,Alignment=2,MarginV=380,"
                "MarginL=80,MarginR=80"
            )
        else:
            style = (
                "PlayResX=1920,PlayResY=1080,FontName=Segoe UI,FontSize=42,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=4,Shadow=1,Alignment=2,MarginV=90,"
                "MarginL=140,MarginR=140"
            )
        return f"subtitles='{self._filter_path(captions_path)}':force_style='{style}'"

    def _generate_ambient_bgm(
        self, output_path: Path, *, duration: float, channel_profile: str
    ) -> Path:
        dur = max(2.0, duration + 2.0)
        chord_specs = {
            "wondertales": "sine=frequency=261.6:duration={d},volume=0.15[a];sine=frequency=329.6:duration={d},volume=0.12[b];sine=frequency=392:duration={d},volume=0.10[c];[a][b][c]amix=inputs=3,lowpass=f=800",
            "mokshavani": "sine=frequency=108:duration={d},volume=0.20[a];sine=frequency=216:duration={d},volume=0.15[b];sine=frequency=432:duration={d},volume=0.08[c];[a][b][c]amix=inputs=3,lowpass=f=600",
            "apexstoic": "sine=frequency=73.4:duration={d},volume=0.25[a];sine=frequency=110:duration={d},volume=0.18[b];sine=frequency=146.8:duration={d},volume=0.12[c];[a][b][c]amix=inputs=3,lowpass=f=450",
            "chronosenigma": "sine=frequency=65.4:duration={d},volume=0.25[a];sine=frequency=98:duration={d},volume=0.18[b];sine=frequency=130.8:duration={d},volume=0.12[c];[a][b][c]amix=inputs=3,lowpass=f=400",
            "empirepulse": "sine=frequency=130.8:duration={d},volume=0.18[a];sine=frequency=196:duration={d},volume=0.14[b];sine=frequency=261.6:duration={d},volume=0.10[c];[a][b][c]amix=inputs=3,lowpass=f=700",
            "curioaxiom": "sine=frequency=110:duration={d},volume=0.20[a];sine=frequency=164.8:duration={d},volume=0.15[b];sine=frequency=220:duration={d},volume=0.10[c];[a][b][c]amix=inputs=3,lowpass=f=600",
            "bytevexa": "sine=frequency=146.8:duration={d},volume=0.18[a];sine=frequency=220:duration={d},volume=0.14[b];sine=frequency=293.6:duration={d},volume=0.10[c];[a][b][c]amix=inputs=3,lowpass=f=750",
        }
        spec = chord_specs.get(channel_profile, chord_specs["bytevexa"]).format(d=f"{dur:.1f}")
        cmd = [
            self.ffmpeg_binary, "-y",
            "-f", "lavfi", "-i", spec,
            "-t", f"{dur:.2f}",
            "-f", "wav", str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def _mux(
        self,
        video_track: Path,
        audio_path: Path,
        output_path: Path,
        *,
        captions_path: Path | None,
        vertical: bool,
        bgm_path: Path | None = None,
    ) -> None:
        command = [self.ffmpeg_binary, "-y", "-i", str(video_track), "-i", str(audio_path)]
        filter_complex = []
        map_video = "0:v:0"
        map_audio = "1:a:0"

        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            filter_complex.append(f"[0:v]{self._caption_filter(captions_path, vertical=vertical)}[vout]")
            map_video = "[vout]"

        if bgm_path and bgm_path.exists():
            command += ["-stream_loop", "-1", "-i", str(bgm_path)]
            filter_complex.append(
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.12[bgm];"
                "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
            )
            map_audio = "[aout]"
        else:
            filter_complex.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
            map_audio = "[aout]"

        if filter_complex:
            command += ["-filter_complex", ";".join(filter_complex)]

        command += [
            "-map", map_video, "-map", map_audio, "-shortest", "-c:v", "libx264",
            "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
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
        bgm_path: Path | None = None,
    ) -> None:
        size = "1080x1920" if vertical else "1920x1080"
        command = [
            self.ffmpeg_binary, "-y", "-f", "lavfi", "-i",
            f"color=c=0x0B1020:s={size}:r=30:d={duration}", "-i", str(audio_path),
        ]
        filter_complex = []
        map_video = "0:v:0"
        map_audio = "1:a:0"

        if captions_path and captions_path.exists() and captions_path.stat().st_size:
            filter_complex.append(f"[0:v]{self._caption_filter(captions_path, vertical=vertical)}[vout]")
            map_video = "[vout]"

        if bgm_path and bgm_path.exists():
            command += ["-stream_loop", "-1", "-i", str(bgm_path)]
            filter_complex.append(
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.12[bgm];"
                "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
            )
            map_audio = "[aout]"
        else:
            filter_complex.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
            map_audio = "[aout]"

        if filter_complex:
            command += ["-filter_complex", ";".join(filter_complex)]

        command += [
            "-map", map_video, "-map", map_audio, "-shortest", "-c:v", "libx264",
            "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "192k", "-movflags", "+faststart", str(output_path),
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
