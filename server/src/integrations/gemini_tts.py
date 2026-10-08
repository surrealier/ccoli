"""Gemini 3.8 TTS adapter. Returns mono 16 kHz PCM16LE for the ESP32 link."""
from __future__ import annotations

import base64
import binascii
import io
import math
import re
import wave

import numpy as np
import requests
from scipy.signal import resample_poly


class GeminiTTS:
    """Synthesize one transcript with the explicitly configured Gemini TTS model."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-flash-lite-tts",
        voice: str = "Kore",
    ) -> None:
        if not api_key:
            raise ValueError("Gemini TTS API key is required")
        if not re.fullmatch(r"gemini-[a-z0-9.-]+-tts", model):
            raise ValueError("Unsupported Gemini TTS model identifier")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", voice):
            raise ValueError("Invalid Gemini TTS voice identifier")
        self._api_key = api_key
        self.model = model
        self.voice = voice

    @staticmethod
    def _decode_audio(part: dict) -> bytes:
        inline = part.get("inlineData")
        if not isinstance(inline, dict):
            raise ValueError("Missing TTS audio")
        encoded = inline.get("data")
        if not isinstance(encoded, str):
            raise ValueError("Missing TTS audio data")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid TTS audio encoding") from exc
        mime = str(inline.get("mimeType", "")).lower()
        if audio[:4] == b"RIFF":
            with wave.open(io.BytesIO(audio), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                    raise ValueError("Unsupported TTS WAV format")
                sample_rate = wav.getframerate()
                pcm = wav.readframes(wav.getnframes())
        else:
            if not mime.startswith("audio/l16"):
                raise ValueError("Unsupported TTS audio format")
            rate = re.search(r"(?:^|;)\s*rate\s*=\s*(\d+)", mime)
            channels = re.search(r"(?:^|;)\s*channels\s*=\s*(\d+)", mime)
            if rate is None or channels is None or channels.group(1) != "1":
                raise ValueError("Unsupported TTS raw audio metadata")
            sample_rate = int(rate.group(1))
            pcm = audio
        if not 8000 <= sample_rate <= 48000 or not pcm or len(pcm) % 2:
            raise ValueError("Invalid TTS PCM payload")
        if sample_rate == 16000:
            return pcm
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        divisor = math.gcd(sample_rate, 16000)
        resampled = resample_poly(samples, 16000 // divisor, sample_rate // divisor)
        return np.clip(np.rint(resampled), -32768, 32767).astype("<i2").tobytes()

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        body = {
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": text,
                    "speech_metadata": {"style": "warm and clear"},
                }],
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"voice": self.voice}},
            },
        }
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            json=body,
            timeout=(3.05, 6),
        )
        response.raise_for_status()
        candidates = response.json().get("candidates") or []
        if not candidates:
            raise ValueError("Gemini TTS returned no candidate")
        parts = candidates[0].get("content", {}).get("parts") or []
        for part in parts:
            if isinstance(part, dict) and part.get("inlineData"):
                return self._decode_audio(part)
        raise ValueError("Gemini TTS returned no audio")
