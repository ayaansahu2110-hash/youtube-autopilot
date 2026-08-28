import math
from pathlib import Path


def write_srt(script: str, duration_seconds: float, output_path: Path, *, words_per_caption: int = 5) -> Path:
    words = script.split()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not words:
        output_path.write_text("", encoding="utf-8")
        return output_path

    chunks = [words[index:index + words_per_caption] for index in range(0, len(words), words_per_caption)]
    total_words = max(1, len(words))
    cursor = 0.0
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        share = len(chunk) / total_words
        length = duration_seconds * share
        end = duration_seconds if index == len(chunks) else min(duration_seconds, cursor + length)
        lines.extend([str(index), f"{_stamp(cursor)} --> {_stamp(end)}", " ".join(chunk), ""])
        cursor = end
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _stamp(seconds: float) -> str:
    milliseconds = max(0, int(math.floor(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
