import asyncio
from pathlib import Path

import edge_tts


class EdgeTTSProvider:
    def __init__(self, voice: str):
        self.voice = voice

    async def _save(self, text: str, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text=text, voice=self.voice)
        await communicate.save(str(output))

    def synthesize(self, text: str, output: Path) -> Path:
        asyncio.run(self._save(text, output))
        return output
