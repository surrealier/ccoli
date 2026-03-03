"""
에이전트 모드 처리 모듈
- 가정용 AI 어시스턴트 기능 제공
- 대화 기록 관리 및 컨텍스트 유지
- 감정 분석, 정보 서비스, 스케줄링 통합
- TTS 음성 합성 및 오디오 처리
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from emotion_system import EmotionSystem
from info_services import InfoServices
from proactive_interaction import ProactiveInteraction
from scheduler import Scheduler
from src.integrations import IntegrationRegistry, WeatherIntegration, build_tts_debug_message
from src.memory_manager import MemoryManager
from src.intent_parser import parse_intent

log = logging.getLogger(__name__)


class AgentMode:
    """에이전트 모드 메인 클래스 - 가정용 AI 어시스턴트 기능 제공"""
    _EMOJI_RE = re.compile(
        "["
        "\U0001F1E6-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\u2600-\u27BF"
        "]",
        flags=re.UNICODE,
    )
    _EMOJI_META_RE = re.compile(r"[\u200d\ufe0e\ufe0f]")

    def __init__(
        self,
        llm_client,
        weather_api_key=None,
        lat=37.5665,
        lon=126.9780,
        proactive_enabled=True,
        proactive_interval=1800,
        tts_voice=None,
    ):
        self.llm = llm_client
        self.tts_voice = tts_voice or "ko-KR-SunHiNeural"

        # 대화 기록
        self.conversation_history = []
        self.max_history = 20
        self.conversation_count = 0

        # 메모리 매니저 (md 파일 기반)
        self.memory = MemoryManager(llm_client)

        # 서브시스템 초기화
        self.emotion_system = EmotionSystem()
        self.info_services = InfoServices(weather_api_key, lat=lat, lon=lon)
        self.integrations = IntegrationRegistry()
        self.integrations.register(WeatherIntegration(weather_api_key, lat=lat, lon=lon), enabled=True)
        self.proactive = ProactiveInteraction(proactive_enabled, proactive_interval)
        self.scheduler = Scheduler()

    def _sanitize_response(self, text: str) -> str:
        """LLM 응답 후처리: 자기소개/이모지 제거 + 공백 정리"""
        cleaned = " ".join((text or "").split()).strip()
        if not cleaned:
            return ""

        # 콜리 자기소개 패턴 제거
        intro_patterns = [
            r"^(안녕하세요[!,. ]*)?(저는|전|제가)?\s*콜리\s*(입니다|이에요|예요)?[!,. ]*",
            r"^(제 이름은|내 이름은)\s*콜리\s*(입니다|이에요|예요)?[!,. ]*",
        ]
        for pattern in intro_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

        cleaned = self._EMOJI_RE.sub("", cleaned)
        cleaned = self._EMOJI_META_RE.sub("", cleaned)
        cleaned = " ".join(cleaned.split()).strip()
        return cleaned

    @staticmethod
    def _pick_split_index(text: str, min_idx: int, max_idx: int) -> int:
        """min/max 범위 내에서 자연스러운 분할 위치 선택"""
        max_idx = max(0, min(max_idx, len(text) - 1))
        min_idx = max(0, min(min_idx, max_idx))

        for i in range(max_idx, min_idx - 1, -1):
            if text[i] in ".?!,;:。！？":
                return i + 1
        for i in range(max_idx, min_idx - 1, -1):
            if text[i].isspace():
                return i + 1
        return max_idx + 1

    def split_text_for_tts(self, text: str, max_chunks: int = 3):
        """
        TTS용 텍스트 분할.
        - 짧은 문장은 그대로 유지
        - 긴 문장은 2~3개 청크로 분할
        """
        normalized = " ".join((text or "").split()).strip()
        if not normalized:
            return []

        max_chunks = max(1, max_chunks)
        if len(normalized) <= 44 or max_chunks == 1:
            return [normalized]

        target_chunks = 2 if len(normalized) <= 92 else 3
        target_chunks = min(target_chunks, max_chunks)

        chunks = []
        start = 0
        remaining_chunks = target_chunks
        text_len = len(normalized)

        while remaining_chunks > 1 and start < text_len:
            remaining_len = text_len - start
            target_len = remaining_len // remaining_chunks
            min_idx = start + max(10, target_len - 10)
            max_idx = start + min(remaining_len - 10, target_len + 12)
            if max_idx <= min_idx:
                max_idx = min(start + target_len, text_len - 1)
                min_idx = max(start + 6, max_idx - 6)

            split_idx = self._pick_split_index(normalized, min_idx, max_idx)
            piece = normalized[start:split_idx].strip()
            if piece:
                chunks.append(piece)

            start = split_idx
            while start < text_len and normalized[start].isspace():
                start += 1
            remaining_chunks -= 1

        tail = normalized[start:].strip()
        if tail:
            chunks.append(tail)

        if not chunks:
            return [normalized]

        merged = []
        for piece in chunks:
            if merged and len(piece) < 6:
                merged[-1] = f"{merged[-1]} {piece}".strip()
            else:
                merged.append(piece)
        return merged

    def prepare_tts_chunks(self, text: str, max_chunks: int = 3):
        """TTS 전송용 텍스트 청크 준비 (정제 + 분할)"""
        cleaned = self._sanitize_response(text)
        return self.split_text_for_tts(cleaned, max_chunks=max_chunks)

    @staticmethod
    def merge_audio_chunks(audio_chunks: list[bytes], sr: int = 16000, crossfade_ms: float = 12.0) -> bytes:
        """
        여러 PCM16LE 청크를 하나의 오디오로 결합.
        청크 경계 클릭 노이즈를 줄이기 위해 짧은 crossfade를 적용한다.
        """
        valid_chunks = [chunk for chunk in audio_chunks if chunk]
        if not valid_chunks:
            return b""
        if len(valid_chunks) == 1:
            return valid_chunks[0]

        import numpy as np

        arrays = []
        for chunk in valid_chunks:
            if len(chunk) < 2:
                continue
            arrays.append(np.frombuffer(chunk, dtype="<i2").astype(np.float32))
        if not arrays:
            return b""

        fade_len = max(0, int(sr * max(0.0, float(crossfade_ms)) / 1000.0))
        merged = arrays[0]
        for nxt in arrays[1:]:
            if merged.size == 0:
                merged = nxt
                continue
            n = min(fade_len, merged.size, nxt.size)
            if n > 0:
                fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
                fade_in = 1.0 - fade_out
                overlap = merged[-n:] * fade_out + nxt[:n] * fade_in
                merged = np.concatenate((merged[:-n], overlap, nxt[n:]))
            else:
                merged = np.concatenate((merged, nxt))

        pcm16 = np.clip(merged, -32768.0, 32767.0).astype("<i2")
        return pcm16.tobytes()

    @staticmethod
    def crossfade_audio_boundaries(
        audio_chunks: list[bytes],
        sr: int = 16000,
        crossfade_ms: float = 12.0,
    ) -> list[bytes]:
        """
        청크 단위 전송을 유지하면서 경계만 crossfade 처리한다.
        반환값은 동일한 순서의 PCM16LE 청크 리스트다.
        """
        valid_chunks = [chunk for chunk in audio_chunks if chunk]
        if len(valid_chunks) <= 1:
            return valid_chunks

        import numpy as np

        arrays = []
        for chunk in valid_chunks:
            if len(chunk) < 2:
                arrays.append(np.zeros(0, dtype=np.float32))
                continue
            arrays.append(np.frombuffer(chunk, dtype="<i2").astype(np.float32))

        n = max(0, int(sr * max(0.0, float(crossfade_ms)) / 1000.0))
        if n <= 0:
            return valid_chunks

        out_arrays = []
        prev = arrays[0]
        for nxt in arrays[1:]:
            if prev.size == 0:
                out_arrays.append(prev)
                prev = nxt
                continue
            overlap = min(n, prev.size, nxt.size)
            if overlap > 0:
                fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
                fade_in = 1.0 - fade_out
                mixed = prev[-overlap:] * fade_out + nxt[:overlap] * fade_in
                prev = np.concatenate((prev[:-overlap], mixed))
                nxt = nxt[overlap:]
            out_arrays.append(prev)
            prev = nxt
        out_arrays.append(prev)

        result = []
        for arr in out_arrays:
            if arr.size == 0:
                result.append(b"")
                continue
            pcm16 = np.clip(arr, -32768.0, 32767.0).astype("<i2")
            result.append(pcm16.tobytes())
        return result

    def _get_system_prompt(self) -> str:
        """시스템 프롬프트 생성 - MemoryManager가 md 파일에서 조립"""
        return self.memory.build_system_prompt()

    def generate_response(self, text: str, is_proactive: bool = False) -> tuple[str, str]:
        """응답 생성. Returns (response_text, intent)."""
        if not self.llm:
            return "모델이 로드되지 않았습니다.", "none"

        try:
            if not is_proactive:
                self.proactive.update_interaction()

            # 정보 서비스 요청 처리 (날씨, 뉴스 등) → LLM 컨텍스트로 주입
            info_context = None
            if not is_proactive:
                info_data = self._resolve_info_data(text)
                if info_data and info_data.get("type") == "integration_error":
                    return info_data.get("message", "요청 처리 중 오류가 발생했어요."), "none"
                if info_data:
                    import json
                    info_context = json.dumps(info_data, ensure_ascii=False)
                    log.info("Info data for LLM context: %s", info_context)

                schedule_response = self.scheduler.process_schedule_request(text)
                if schedule_response:
                    info_context = schedule_response if isinstance(schedule_response, str) else str(schedule_response)

            detected_emotion = self.emotion_system.analyze_emotion(text)

            self.conversation_history.append(
                {
                    "role": "user",
                    "content": text,
                    "timestamp": datetime.now().isoformat(),
                    "emotion": detected_emotion,
                }
            )

            # LLM 응답 생성
            system_prompt = self._get_system_prompt()
            if info_context:
                system_prompt += f"\n\n[참고 데이터]\n{info_context}\n위 데이터를 바탕으로 자연스럽게 답변하세요."
            messages = [{"role": "system", "content": system_prompt}]
            for conv in self.conversation_history[-self.max_history:]:
                messages.append({"role": conv["role"], "content": conv["content"]})

            raw = self.llm.chat(messages, temperature=0.8, max_tokens=256)
            intent, clean_text = parse_intent(raw)
            response = self._sanitize_response(clean_text)
            if not response:
                response = "음, 잘 못 알아들었어요. 다시 한번 말씀해주시겠어요?"

            # sleep 의도 처리
            if intent == "sleep":
                self.proactive.sleep_mode = True
                self.proactive.sleep_until = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

            response_emotion = self.emotion_system.analyze_emotion(response)
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                    "emotion": response_emotion,
                }
            )

            self.conversation_count += 1
            self.memory.after_turn(self.conversation_history)

            log.info("Agent Response (intent=%s): %s", intent, response)
            return response, intent
        except Exception as exc:
            log.error("LLM generation failed: %s", exc)
            return "죄송해요, 오류가 발생했어요.", "none"

    def _resolve_info_data(self, text: str):
        text_lower = (text or "").lower()
        weather_keywords = ["날씨", "기온", "온도", "비", "눈"]
        if any(keyword in text_lower for keyword in weather_keywords):
            weather_result = self.integrations.execute("weather", "weather.current", {})
            if weather_result:
                if weather_result.ok:
                    return weather_result.data
                if weather_result.error:
                    log.warning("weather integration error: %s %s", weather_result.error.code, weather_result.error.debug)
                    return {
                        "type": "integration_error",
                        "integration": "weather",
                        "code": weather_result.error.code.value,
                        "message": build_tts_debug_message("weather", "날씨", weather_result.error.code),
                    }
        return self.info_services.process_info_request(text)

    async def _tts_gen(self, text, output_file):
        """TTS 생성 - Edge TTS를 사용한 음성 합성"""
        import edge_tts

        communicate = edge_tts.Communicate(text, self.tts_voice)
        await communicate.save(output_file)

    def text_to_audio(self, text: str, trim_pad_ms: float = 140.0):
        """텍스트를 오디오로 변환 - TTS 생성 및 오디오 후처리"""
        tmp_mp3 = None
        try:
            import os
            import importlib
            import tempfile

            missing = []
            for mod in ("numpy", "librosa", "soundfile", "edge_tts"):
                try:
                    importlib.import_module(mod)
                except ModuleNotFoundError:
                    missing.append(mod)
            if missing:
                log.error(
                    "TTS dependency missing: %s (install: pip install %s)",
                    ", ".join(missing),
                    " ".join(missing),
                )
                return b""

            import numpy as np
            import librosa
            try:
                from .audio_processor import normalize_to_dbfs, qc, trim_energy
                audio_proc_available = True
            except ModuleNotFoundError:
                audio_proc_available = False
                log.warning(
                    "audio_processor not found; skipping trim/normalize/qc post-processing"
                )
            with tempfile.NamedTemporaryFile(prefix="tts_", suffix=".mp3", delete=False) as tf:
                tmp_mp3 = tf.name

            log.info("Generating TTS for: %s", text[:50])

            # 이벤트 루프 설정 및 TTS 생성
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(self._tts_gen(text, tmp_mp3))
            except Exception as exc:
                log.error("TTS generation failed in _tts_gen: %s", exc, exc_info=True)
                return b""
            if not os.path.exists(tmp_mp3):
                log.error("TTS file not created: %s", tmp_mp3)
                return b""

            # 오디오 로드 및 리샘플링 (16kHz, mono)
            pcm_f32, sr = librosa.load(tmp_mp3, sr=16000, mono=True)

            if pcm_f32.size == 0:
                log.error("TTS audio empty after decoding: %s", tmp_mp3)
                return b""

            # 오디오 후처리 - DC 오프셋 제거 및 무음 구간 트림
            pcm_f32 = (pcm_f32 - np.mean(pcm_f32)).astype(np.float32, copy=False)
            if audio_proc_available:
                # 청크형 TTS에서는 pad를 과도하게 주면 경계마다 불필요한 무음이 커진다.
                pcm_f32 = trim_energy(
                    pcm_f32,
                    sr=sr,
                    top_db=35.0,
                    pad_ms=max(0.0, float(trim_pad_ms)),
                )

                # 음량 정규화 - RMS 기반 볼륨 조정
                pcm_f32 = normalize_to_dbfs(pcm_f32, target_dbfs=-18.0, max_gain_db=18.0)
                peak = float(np.max(np.abs(pcm_f32))) if pcm_f32.size else 0.0
                if peak > 0.90:
                    pcm_f32 = (pcm_f32 / peak * 0.90).astype(np.float32, copy=False)

            # 청크 경계 클릭 노이즈 완화용 짧은 페이드 인/아웃
            fade_len = int(sr * 0.008)
            if pcm_f32.size > 2 and fade_len > 0:
                fade_len = min(fade_len, pcm_f32.size // 2)
                if fade_len > 0:
                    fade = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
                    pcm_f32[:fade_len] *= fade
                    pcm_f32[-fade_len:] *= fade[::-1]

            # 16-bit PCM 변환 (PCM16LE)
            pcm_16 = (pcm_f32 * 32767.0).astype("<i2")
            audio_bytes = pcm_16.tobytes()

            # 오디오 품질 검증 및 로깅
            if audio_proc_available:
                rms_db, peak, clip = qc(pcm_f32)
                log.info(
                    "TTS generated: %d bytes, %.2f seconds, RMS: %.2f dBFS, peak: %.3f, clip: %.2f%%",
                    len(audio_bytes),
                    len(pcm_16) / 16000.0,
                    rms_db,
                    peak,
                    clip,
                )
            else:
                log.info(
                    "TTS generated: %d bytes, %.2f seconds (post-processing skipped)",
                    len(audio_bytes),
                    len(pcm_16) / 16000.0,
                )
            return audio_bytes
        except ModuleNotFoundError as exc:
            log.error("TTS dependency missing at runtime: %s", exc, exc_info=True)
            log.error("Install: pip install edge-tts librosa soundfile")
            return b""
        except Exception as exc:
            log.error("TTS failed: %s", exc, exc_info=True)
            return b""
        finally:
            if tmp_mp3:
                try:
                    Path(tmp_mp3).unlink(missing_ok=True)
                except Exception:
                    pass
