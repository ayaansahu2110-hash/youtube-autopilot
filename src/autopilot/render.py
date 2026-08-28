import subprocess
from pathlib import Path


class FFmpegRenderer:
    def __init__(self, ffmpeg_binary: str = "ffmpeg"):
        self.ffmpeg_binary = ffmpeg_binary

    def render_simple(self, audio_path: Path, output_path: Path, vertical: bool = True) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        size = "1080x1920" if vertical else "1920x1080"
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111111:s={size}:r=30",
            "-i",
            str(audio_path),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return output_path
