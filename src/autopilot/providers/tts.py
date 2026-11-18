import asyncio
import base64
import re
import subprocess
from pathlib import Path

import edge_tts


# ---------------------------------------------------------------------------
# OpenAI TTS Provider — highest quality, most human-like, used for GTA6Hub
# ---------------------------------------------------------------------------

class OpenAITTSProvider:
    """
    Premium TTS using OpenAI's tts-1-hd model.
    Significantly more human-like than Edge TTS — natural breath, rhythm, emotion.
    Used for GTA6Hub where vocal quality is a core differentiator.
    """

    VOICE_MAP = {
        # Best voices for gaming / energetic commentary
        "onyx": "onyx",    # Deep, authoritative, male — perfect for GTA gaming channel
        "echo": "echo",    # Clear, confident male
        "fable": "fable",  # British male, great for storytelling
        "nova": "nova",    # Energetic female
        "shimmer": "shimmer",  # Warm female
        "alloy": "alloy",  # Neutral, versatile
    }

    def __init__(
        self,
        voice: str = "onyx",
        *,
        model: str = "tts-1-hd",
        speed: float = 1.08,  # Slightly faster — gaming energy pace
        openai_api_key: str | None = None,
        ffmpeg_binary: str = "ffmpeg",
        # Fallback TTS if OpenAI fails
        fallback_voice: str = "en-US-GuyNeural",
        fallback_rate: str = "+3%",
        fallback_pitch: str = "-1Hz",
        gemini_api_key: str | None = None,
    ):
        self.voice = voice if voice in self.VOICE_MAP else "onyx"
        self.model = model
        self.speed = speed
        self.openai_api_key = openai_api_key
        self.ffmpeg_binary = ffmpeg_binary
        self.fallback_voice = fallback_voice
        self.fallback_rate = fallback_rate
        self.fallback_pitch = fallback_pitch
        self.gemini_api_key = gemini_api_key

    @staticmethod
    def _prepare_text(text: str) -> str:
        """Clean and format text for natural speech synthesis."""
        cleaned = re.sub(r"\s+", " ", text).strip()
        # Add pauses after major punctuation for natural rhythm
        cleaned = re.sub(r"([.!?])\s+", r"\1  ", cleaned)
        # Convert em-dashes to natural pause
        cleaned = cleaned.replace(" — ", ".  ")
        # Remove on-screen text markers if accidentally included
        cleaned = re.sub(r"\[.*?\]", "", cleaned).strip()
        return cleaned

    def _synthesize_openai(self, text: str, output: Path) -> None:
        """Generate ultra-realistic speech using OpenAI TTS HD."""
        from openai import OpenAI
        client = OpenAI(api_key=self.openai_api_key)

        output.parent.mkdir(parents=True, exist_ok=True)
        mp3_raw = output.with_suffix(".openai_raw.mp3")

        response = client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=self._prepare_text(text),
            speed=self.speed,
            response_format="mp3",
        )
        response.stream_to_file(mp3_raw)

        # Convert to standard mp3 with optimized settings for YouTube
        subprocess.run(
            [
                self.ffmpeg_binary, "-y",
                "-i", str(mp3_raw),
                "-codec:a", "libmp3lame",
                "-q:a", "0",          # Highest quality VBR
                "-ar", "44100",        # 44.1kHz for YouTube
                "-ac", "2",            # Stereo
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        mp3_raw.unlink(missing_ok=True)

    def synthesize(self, text: str, output: Path) -> Path:
        """Synthesize speech with OpenAI HD, falling back to Edge/Gemini."""
        if self.openai_api_key:
            try:
                self._synthesize_openai(text, output)
                return output
            except Exception as e:
                print(f"OpenAI TTS failed ({e}), falling back to Edge TTS")

        # Fallback: Edge TTS (same quality as other channels)
        fallback = EdgeTTSProvider(
            self.fallback_voice,
            rate=self.fallback_rate,
            pitch=self.fallback_pitch,
            gemini_api_key=self.gemini_api_key,
            ffmpeg_binary=self.ffmpeg_binary,
        )
        return fallback.synthesize(text, output)



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
