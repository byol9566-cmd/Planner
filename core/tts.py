from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class TTS:
    def __init__(self, voice: str = "ko-KR-SunHiNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self._fallback_engine = None

    def speak(self, text: str) -> None:
        try:
            self._speak_edge(text)
        except Exception as e:
            logger.warning("Edge-TTS failed (%s), falling back to pyttsx3", e)
            self._speak_pyttsx3(text)

    def _speak_edge(self, text: str) -> None:
        import edge_tts
        import winsound

        async def _run() -> Path:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = Path(f.name)
            await communicate.save(str(tmp_path))
            return tmp_path

        tmp_path = asyncio.run(_run())
        try:
            winsound.PlaySound(str(tmp_path), winsound.SND_FILENAME)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def _speak_pyttsx3(self, text: str) -> None:
        if self._fallback_engine is None:
            import pyttsx3
            self._fallback_engine = pyttsx3.init()
            self._fallback_engine.setProperty("rate", 160)
        self._fallback_engine.say(text)
        self._fallback_engine.runAndWait()
