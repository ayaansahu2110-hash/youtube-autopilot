import asyncio
import base64
import subprocess
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
        gemini_api_key: str | None = None,
        ffmpeg_binary: str = "ffmpeg",
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.gemini_api_key = gemini_api_key
        self.ffmpeg_binary = ffmpeg_binary

    @staticmethod
    def _prepare_text(text: str) -> str:
        # TTS sounds more human when the script contains deliberate breathing room.
        import re

        cleaned = re.sub(r"\\s+", " ", text).strip()
        cleaned = re.sub(r"([.!?])\\s+", r"\\1  ", cleaned)
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

    async def _save_edge_with_retry(self, text: str, output: Path) -> None:
        last_error: Exception | None = None
        for attempt, delay in enumerate((0, 2, 5), start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self._save(text, output)
                return
            except Exception as exc:
                last_error = exc
                if output.exists():
                    output.unlink()
                if attempt == 3:
                    break
        assert last_error is not None
        raise last_error

    def _save_with_gemini(self, text: str, output: Path) -> None:
        if not self.gemini_api_key:
            raise RuntimeError("Gemini TTS fallback is unavailable because GEMINI_API_KEY is empty.")

        from google import genai

        client = genai.Client(api_key=self.gemini_api_key)
        interaction = client.interactions.create(
            model="gemini-3.8-flash-tts",
            input=[{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": self._prepare_text(text),
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": (
                            "Natural premium documentary narration; confident, warm and "
                            "conversational; moderate pace; clear emphasis without hype."
                        ),
                    }],
                }],
            }],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": "Orus"}]},
        )
        payload = interaction.output_audio.data
        audio = base64.b64decode(payload) if isinstance(payload, str) else bytes(payload)
        if not audio:
            raise RuntimeError("Gemini TTS returned an empty audio response.")

        output.parent.mkdir(parents=True, exist_ok=True)
        wav_path = output.with_suffix(".gemini.wav")
        wav_path.write_bytes(audio)
        try:
            subprocess.run(
                [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(output),
                ],
                check=True,
                capture_output=True,
            )
        finally:
            wav_path.unlink(missing_ok=True)

    def synthesize(self, text: str, output: Path) -> Path:
        try:
            asyncio.run(self._save_edge_with_retry(text, output))
        except Exception:
            # Edge's undocumented consumer WebSocket can reject cloud runners.
            # Use the configured, studio-grade Gemini TTS API rather than
            # lowering narration quality or publishing a silent video.
            self._save_with_gemini(text, output)
        return output
