import asyncio
import re
from pathlib import Path

import edge_tts


class EdgeTTSProvider:
    def __init__(
        self,
        voice: str,
        *,
        rate: str = "+2%",
        pitch: str = "-2Hz",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

    @staticmethod
    def _prepare_text(text: str) -> str:
        # TTS sounds more human and musical when deliberate breathing room is provided.
        # For multi-line nursery rhymes and poems, ensure each line ends with expressive punctuation.
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if len(lines) >= 3:
            processed = []
            for line in lines:
                if not line.endswith((".", "!", "?", ",", ";", ":", "—")):
                    line += "!"
                processed.append(line)
            return "  ".join(processed)

        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = re.sub(r"([.!?])\s+", r"\1  ", cleaned)
        cleaned = cleaned.replace(" — ", ".  ")
        return cleaned

    async def _save(self, text: str, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(
            text=self._prepare_text(text),
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume,
        )
        await communicate.save(str(output))

    def synthesize(self, text: str, output: Path) -> Path:
        asyncio.run(self._save(text, output))
        return output
