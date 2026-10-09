"""
에이전트 모드 처리 모듈
- 가정용 AI 어시스턴트 기능 제공
- 대화 기록 관리 및 컨텍스트 유지
- 감정 분석, 정보 서비스, 스케줄링 통합
- TTS 음성 합성 및 오디오 처리
"""
import asyncio
import json
import logging
import os
import re
import time
import threading
import hashlib
import io
import math
from datetime import datetime

from emotion_system import EmotionSystem
from info_services import InfoServices
from proactive_interaction import ProactiveInteraction
from scheduler import Scheduler
from src.integrations import (
    GoogleCalendarIntegration,
    IntegrationRegistry,
    MapsIntegration,
    NotifyIntegration,
    SearchIntegration,
    WeatherIntegration,
    build_tts_debug_message,
)
from src.memory_manager import MemoryManager
from src.intent_parser import parse_intent
from src.dialogue_policy import (
    AudioCache, SUPPORTED_LANGUAGES, conversation_instructions, localize_message,
    normalize_language, phrase, resolve_language, voice_for_language,
)

log = logging.getLogger(__name__)

AGENT_RESPONSE_MAX_TOKENS = 768


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
        memory_dir=None,
        memory_refresh_interval=5,
        emotion_system=None,
        integration_config=None,
        agent_config=None,
        tts_backend="edge_tts",
        tts_model="gemini-3.8-flash-lite-tts",
        tts_gemini_voice="Kore",
        tts_api_key="",
        dialogue_config=None,
    ):
        self.llm = llm_client
        self.tts_voice = tts_voice or "ko-KR-SunHiNeural"
        self._dialogue_lock = threading.RLock()
        self._dialogue = {'language': 'auto', 'short_responses': True, 'fast_model': ''}
        self._owner_languages = {}
        self._audio_cache = AudioCache()
        self.configure_dialogue(**(dialogue_config or {}))
        self.tts_backend = str(tts_backend or "edge_tts").strip().lower()
        self.gemini_tts = None
        if self.tts_backend == "gemini_tts" and tts_api_key:
            from src.integrations.gemini_tts import GeminiTTS
            try:
                self.gemini_tts = GeminiTTS(
                    tts_api_key, model=tts_model, voice=tts_gemini_voice,
                )
            except ValueError:
                log.warning("Gemini TTS 설정을 확인해 주세요. Edge TTS를 사용합니다.")
        self.integration_config = integration_config or {}

        # 대화 기록
        self.conversation_history = []
        self.user_histories = {}
        self.max_history = 20
        self.conversation_count = 0

        # 메모리 매니저 (md 파일 기반)
        self.memory = MemoryManager(
            llm_client,
            memory_dir=memory_dir,
            refresh_interval=memory_refresh_interval,
        )

        # 서브시스템 초기화
        self.emotion_system = emotion_system or EmotionSystem()
        self.info_services = InfoServices(weather_api_key, lat=lat, lon=lon)
        self.integrations = IntegrationRegistry()
        self.integrations.register(
            WeatherIntegration(weather_api_key, lat=lat, lon=lon),
            enabled=self._integration_enabled("weather"),
        )
        self.integrations.register(
            SearchIntegration(self._integration_value("search", "api_key", "TAVILY_API_KEY")),
            enabled=self._integration_enabled("search"),
        )
        self.integrations.register(
            NotifyIntegration(self._integration_value("notify-slack", "api_key", "SLACK_BOT_TOKEN")),
            enabled=self._integration_enabled("notify-slack"),
        )
        self.integrations.register(
            MapsIntegration(self._integration_value("maps", "api_key", "GOOGLE_MAPS_API_KEY")),
            enabled=self._integration_enabled("maps"),
        )
        self.integrations.register(
            GoogleCalendarIntegration(
                self._integration_value("calendar-google", "client_id", "GOOGLE_CLIENT_ID"),
                self._integration_value("calendar-google", "client_secret", "GOOGLE_CLIENT_SECRET"),
                self._integration_value("calendar-google", "refresh_token", "GOOGLE_REFRESH_TOKEN"),
                calendar_id=self._integration_value("calendar-google", "calendar_id", "GOOGLE_CALENDAR_ID") or "primary",
                time_zone=self._integration_value("calendar-google", "time_zone", "GOOGLE_CALENDAR_TIME_ZONE")
                or "Asia/Seoul",
            ),
            enabled=self._integration_enabled("calendar-google"),
        )
        self.proactive = ProactiveInteraction(proactive_enabled, proactive_interval)
        self.scheduler = Scheduler()
        self.tool_agent = None
        self._tool_turn_lock = threading.Lock()
        self._tool_state_lock = threading.RLock()
        self._owner_turn_locks = {}
        if (agent_config or {}).get("enabled", False):
            from src.personal_store import PersonalStore
            from src.tool_agent import ToolAgent

            state_path = (agent_config or {}).get("state_path") or self.memory.memory_dir / "personal.sqlite3"
            home = None
            if os.getenv("HOME_ASSISTANT_URL", ""):
                from src.integrations.home_assistant import HomeAssistantIntegration
                try:
                    candidate = HomeAssistantIntegration(
                        os.getenv("HOME_ASSISTANT_URL", ""),
                        os.getenv("HOME_ASSISTANT_TOKEN", ""),
                        [item.strip() for item in os.getenv("HOME_ASSISTANT_ALLOWED_ENTITIES", "").split(",") if item.strip()],
                    )
                    if candidate.is_configured():
                        home = candidate
                except ValueError:
                    log.warning("Home Assistant 설정을 확인해 주세요. 홈 도구를 비활성화합니다.")
            self.tool_agent = ToolAgent(
                llm_client, PersonalStore(state_path), home=home,
                soul=self.memory._cache.get("Soul.md", ""), integrations=self.integrations,
            )

    def configure_dialogue(self, *, language=None, short_responses=None, fast_model=None) -> dict:
        """Validate the whole update before changing any running dialogue settings."""
        with self._dialogue_lock:
            updated = dict(self._dialogue)
            if language is not None:
                updated['language'] = normalize_language(language, allow_auto=True)
            if short_responses is not None:
                if type(short_responses) is not bool:
                    raise ValueError('short_responses must be a boolean')
                updated['short_responses'] = short_responses
            if fast_model is not None:
                if not isinstance(fast_model, str) or (fast_model and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}', fast_model)):
                    raise ValueError('Invalid fast model identifier')
                updated['fast_model'] = fast_model
            self._dialogue = updated
            return self.describe_dialogue()

    def describe_dialogue(self) -> dict:
        with self._dialogue_lock:
            return {**self._dialogue, 'supported_languages': list(SUPPORTED_LANGUAGES)}

    def _response_language(self, text: str, language: str | None, owner: str) -> str:
        settings = getattr(self, '_dialogue', {'language': 'auto'})
        previous = getattr(self, '_owner_languages', {}).get(owner, 'ko')
        return resolve_language(text, language, settings.get('language', 'auto'), previous)

    def _chat_dialogue(self, messages: list, *, temperature: float, max_tokens: int) -> str:
        fast_model = getattr(self, '_dialogue', {}).get('fast_model', '')
        if fast_model and hasattr(self.llm, 'chat_fast'):
            return self.llm.chat_fast(messages, model=fast_model, temperature=temperature, max_tokens=max_tokens)
        return self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def _integration_entry(self, name: str) -> dict:
        if not isinstance(self.integration_config, dict):
            return {}
        entry = self.integration_config.get(name, {})
        return entry if isinstance(entry, dict) else {}

    def _integration_enabled(self, name: str) -> bool:
        entry = self._integration_entry(name)
        if "enabled" not in entry:
            return True
        return bool(entry.get("enabled"))

    def _integration_value(self, name: str, field: str, env_key: str) -> str:
        env_value = os.getenv(env_key, "").strip()
        if env_value:
            return env_value
        entry = self._integration_entry(name)
        fields = entry.get("fields", {}) if isinstance(entry.get("fields"), dict) else {}
        value = fields.get(field, entry.get(field, ""))
        return str(value or "").strip()

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
    def merge_audio_chunks(audio_chunks: list[bytes], sr: int = 16000, crossfade_ms: float = 20.0) -> bytes:
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
        crossfade_ms: float = 20.0,
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

    def _recent_conversation_excerpt(self, max_messages: int = 4) -> str:
        history = self.conversation_history[-max(1, max_messages):]
        if not history:
            return "(최근 실시간 대화 없음)"

        lines = []
        for item in history:
            role = "사용자" if item.get("role") == "user" else "콜리"
            content = " ".join((item.get("content") or "").split()).strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "(최근 실시간 대화 없음)"

    @staticmethod
    def _fallback_connection_greeting(now: datetime | None = None) -> str:
        now = now or datetime.now()
        hour = now.hour

        if 5 <= hour < 9:
            tail = "잠 잘 주무셨어요?"
        elif 9 <= hour < 12:
            tail = "오늘 오전은 어떻게 보내고 계세요?"
        elif 12 <= hour < 14:
            tail = "점심은 드셨어요?"
        elif 14 <= hour < 18:
            tail = "아직 일하고 계세요?"
        elif 18 <= hour < 21:
            tail = "저녁은 드셨어요?"
        elif 21 <= hour < 24:
            tail = "오늘 하루는 어떠셨어요?"
        else:
            tail = "아직 안 주무시고 계세요?"

        return f"콜리 연결됐어요! {tail}"

    def generate_connection_greeting(self, now: datetime | None = None) -> str:
        return self._fallback_connection_greeting(now)

    def _llm_failure_response(self, language: str = 'ko') -> str:
        if not self.llm:
            return ""

        provider = (getattr(self.llm, "provider", "") or "llm").lower()
        error_code = getattr(self.llm, "last_error_code", None)
        provider_label = {
            "gemini": "Gemini",
            "claude": "Claude",
            "chatgpt": "ChatGPT",
            "ollama": "Ollama",
        }.get(provider, "LLM")

        if error_code == "missing_api_key":
            return phrase(language,
                f"지금 {provider_label} API 키가 없어서 답변을 만들 수 없어요. 설정을 확인해 주세요.",
                f"Set the {provider_label} API key to enable replies.", f"请设置{provider_label} API密钥以启用回答。",
                f"応答するには{provider_label}のAPIキーを設定してください。", f"Configura la clave API de {provider_label} para activar las respuestas.")

        if error_code in {"provider_error", "unsupported_provider"}:
            return phrase(language, "지금 답변 엔진 연결이 불안정해서 응답을 만들지 못했어요. 잠시 후 다시 말씀해 주세요.",
                "The answer engine is unavailable. Please try again shortly.", "回答引擎暂时无法连接。请稍后重试。",
                "応答エンジンに接続できません。少し待って再度お願いします。", "El modelo no está disponible. Inténtalo de nuevo en un momento.")

        return ""

    def generate_response(self, text: str, is_proactive: bool = False, speaker_id: str | None = None,
                          language: str | None = None) -> tuple[str, str]:
        """응답 생성. Returns (response_text, intent)."""
        language = self._response_language(text, language, speaker_id or 'device')
        if not self.llm:
            return localize_message("모델이 로드되지 않았습니다.", language), "none"

        if getattr(self, "tool_agent", None) is not None:
            if is_proactive:
                return self._generate_proactive_response(text, language)
            return self._generate_tool_response(text, speaker_id, language)

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
                    log.info("Info data available for LLM context (characters=%d)", len(info_context))

                schedule_response = self.scheduler.process_schedule_request(text)
                if schedule_response and not info_context:
                    info_context = schedule_response if isinstance(schedule_response, str) else str(schedule_response)

            self.emotion_system.set_body_state(sleep_mode=self.proactive.sleep_mode)
            detected_emotion = self.emotion_system.analyze_emotion(text, speaker_id=speaker_id or "default")

            history = self._history_for_user(speaker_id)

            history.append(
                {
                    "role": "user",
                    "content": text,
                    "timestamp": datetime.now().isoformat(),
                    "emotion": detected_emotion,
                }
            )

            # LLM 응답 생성
            system_prompt = self._get_system_prompt()
            system_prompt += '\n' + conversation_instructions(language, getattr(self, '_dialogue', {}).get('short_responses', True), text)
            if info_context:
                system_prompt += f"\n\n[참고 데이터]\n{info_context}\n위 데이터를 바탕으로 자연스럽게 답변하세요."
            messages = [{"role": "system", "content": system_prompt}]
            for conv in history[-self.max_history:]:
                messages.append({"role": conv["role"], "content": conv["content"]})

            raw = self._chat_dialogue(messages, temperature=0.8, max_tokens=AGENT_RESPONSE_MAX_TOKENS)
            if raw.strip():
                intent, clean_text = parse_intent(raw)
                response = self._sanitize_response(clean_text)
            else:
                intent = "none"
                response = self._llm_failure_response(language)

            if not response:
                response = localize_message("잘 이해하지 못했어요. 한 번만 다시 말씀해 주세요.", language)

            # sleep 의도 처리
            if intent == "sleep":
                self.proactive.sleep_mode = True
                self.proactive.sleep_until = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
                self.emotion_system.set_body_state(sleep_mode=True, fatigue=1.0)

            response_emotion = self.emotion_system.analyze_emotion(response, speaker_id=speaker_id or "default")
            history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                    "emotion": response_emotion,
                }
            )

            self.conversation_count += 1
            self.memory.after_turn(history)

            log.info("Agent Response intent=%s characters=%d", intent, len(response))
            return response, intent
        except Exception as exc:
            log.error("LLM generation failed: %s", exc)
            return localize_message("죄송해요, 오류가 발생했어요.", language), "none"

    @staticmethod
    def _proactive_reply_text(raw: str) -> str:
        """Suppress JSON syntax, code fences, and device intent tags in spoken text."""
        def strip_intents(value: str) -> str:
            return re.sub(r'\[INTENT:[^\]]*\]', '', value, flags=re.IGNORECASE).strip()

        text = strip_intents(raw)
        if len(text) > 12000 or text.startswith('```'):
            return ''
        if text.startswith(('{', '[')):
            try:
                payload = json.loads(text)
            except ValueError:
                return ''
            if not isinstance(payload, dict) or set(payload) != {'answer'} or not isinstance(payload['answer'], str):
                return ''
            text = strip_intents(payload['answer'])
            if text.startswith(('{', '[', '```')):
                return ''
        if any(marker in text for marker in ('{', '}', '```')):
            return ''
        return text

    def _generate_proactive_response(self, text: str, language: str = 'ko') -> tuple[str, str]:
        """An ephemeral public-context reply with no personal history or actions."""
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return '선제 대화 문장을 8000자 이내로 입력해 주세요.', 'none'
        # A background suggestion must not queue behind or re-enter a user turn.
        if not self._tool_turn_lock.acquire(blocking=False):
            return '', 'none'
        try:
            with self._tool_state_lock:
                soul = self.memory._cache.get('Soul.md', '')
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
            system = soul + '\n\n[Proactive policy; takes precedence over personality]\n' + (
                'Give a brief conversational greeting or suggestion in the prompt language. '
                'There is no identified requester. Do not infer private facts or use personal memory. '
                'Do not propose tools, claim actions completed, or emit device intent tags. '
                'Reply with conversational text only. Current local time: ' + now
            )
            system += '\n' + conversation_instructions(language, getattr(self, '_dialogue', {}).get('short_responses', True), text)
            raw = self._chat_dialogue(
                [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}],
                temperature=0.8, max_tokens=AGENT_RESPONSE_MAX_TOKENS,
            )
            if not isinstance(raw, str) or not raw.strip():
                response = self._llm_failure_response(language) or localize_message('답변 엔진에 연결하지 못했어요. 모델 설정을 확인해 주세요.', language)
            else:
                response = self._sanitize_response(self._proactive_reply_text(raw))
                if not response:
                    return '', 'none'
            with self._tool_state_lock:
                self.emotion_system.set_body_state(sleep_mode=self.proactive.sleep_mode)
                self.emotion_system.analyze_emotion(response, speaker_id='proactive')
                self.conversation_count += 1
            log.info('Proactive response characters=%d', len(response))
            return response, 'none'
        except Exception as exc:
            log.warning('Proactive response generation failed (%s)', type(exc).__name__)
            return '선제 대화 응답을 만들지 못했어요. 모델 연결을 확인해 주세요.', 'none'
        finally:
            self._tool_turn_lock.release()

    def _generate_tool_response(self, text: str, speaker_id: str | None, language: str = 'ko') -> tuple[str, str]:
        """Preserve owner turn order while local paths bypass another owner's model."""
        owner = speaker_id or "device"
        with self._tool_state_lock:
            owner_lock = self._owner_turn_locks.get(owner)
            if owner_lock is None:
                owner_lock = threading.RLock()
                self._owner_turn_locks[owner] = owner_lock
        with owner_lock:
            with self._tool_state_lock:
                self.proactive.update_interaction()
                history = self._history_for_user(speaker_id)
                self.emotion_system.set_body_state(sleep_mode=self.proactive.sleep_mode)
                self.emotion_system.analyze_emotion(text, speaker_id=speaker_id or "default")
                response = self._explicit_household_schedule(text)
                self.tool_agent.soul = self.memory._cache.get("Soul.md", "")
            # Scheduler output is data and must not become a device intent.
            if response is None:
                response = self.tool_agent.try_direct(text, owner, history, language=language)
                if response is None:
                    # Provider error/fallback state is shared, so model turns stay serial.
                    with self._tool_turn_lock:
                        settings = getattr(self, '_dialogue', {})
                        self.tool_agent.short_responses = settings.get('short_responses', True)
                        self.tool_agent.fast_model = settings.get('fast_model', '')
                        response = self.tool_agent.run(text, owner, history, language=language)
                intent, response = parse_intent(response)
            else:
                intent = "none"
            response = self._sanitize_response(response)
            with self._tool_state_lock:
                if intent == "sleep":
                    self.proactive.sleep_mode = True
                    self.proactive.sleep_until = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
                    self.emotion_system.set_body_state(sleep_mode=True, fatigue=1.0)
                now = datetime.now().isoformat()
                history.extend([
                    {"role": "user", "content": text, "timestamp": now},
                    {"role": "assistant", "content": response, "timestamp": now},
                ])
                del history[:-self.max_history]
                self.conversation_count += 1
                self._owner_languages[owner] = language
                self.emotion_system.analyze_emotion(response, speaker_id=speaker_id or "default")
            return response, intent

    def _explicit_household_schedule(self, text: str) -> str | None:
        """Keep explicit local schedule requests on the existing household scheduler."""
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return None
        if "일정" not in text or "캘린더" in text or "구글" in text:
            return None
        previous = list(self.scheduler.schedules)
        try:
            if re.search(r"(?:추가|등록|잡아)(?:해\s?줘|해\s?주세요|해|줘|주세요)?[.!?]?\s*$", text):
                if getattr(self, "_last_schedule_request", None) == text:
                    return "같은 일정 요청을 이미 처리했어요. 일정 목록을 확인해 주세요."
                response = self.scheduler.parse_and_add_schedule(text)
                persisted = json.loads(self.scheduler.schedule_file.read_text(encoding="utf-8"))
                if persisted.get("schedules") != self.scheduler.schedules:
                    raise ValueError("schedule persistence was not confirmed")
                self._last_schedule_request = text
                return response
            if any(word in text for word in ("뭐", "무엇", "확인", "알려", "있어", "목록")):
                if "오늘" in text:
                    return self.scheduler.get_today_schedules()
                return self.scheduler.process_schedule_request("일정 목록 알려줘")
        except Exception:
            self.scheduler.schedules = previous
            return "일정을 처리하지 못했어요. 날짜와 시간, 저장 경로를 확인해 주세요."
        return None

    def _history_for_user(self, speaker_id: str | None):
        if not speaker_id:
            return self.conversation_history
        history = self.user_histories.get(speaker_id)
        if history is None:
            history = []
            self.user_histories[speaker_id] = history
        return history

    def _resolve_info_data(self, text: str):
        text_lower = (text or "").lower()

        if any(keyword in text_lower for keyword in ["날씨", "기온", "온도", "비", "눈"]):
            return self._integration_or_error("weather", "weather.current", {}, "날씨")

        if any(keyword in text_lower for keyword in ["검색", "찾아줘", "검색해줘"]):
            query = (text or "").replace("검색", "").strip() or (text or "")
            return self._integration_or_error("search", "search.query", {"query": query}, "검색")

        if any(keyword in text_lower for keyword in ["일정", "캘린더"]):
            return self._integration_or_error("calendar-google", "calendar.list", {}, "캘린더")

        if any(keyword in text_lower for keyword in ["알림", "슬랙"]):
            return self._integration_or_error(
                "notify-slack",
                "notify.recent",
                {},
                "알림",
            )

        if any(keyword in text_lower for keyword in ["경로", "지도", "길찾기"]):
            return self._integration_or_error(
                "maps",
                "maps.route",
                {"origin": "현재 위치", "destination": "목적지"},
                "지도",
            )

        return self.info_services.process_info_request(text)

    def _integration_or_error(self, provider: str, intent: str, params: dict, display_name: str):
        result = self.integrations.execute(provider, intent, params)
        if result is None:
            return None
        if result.ok:
            return result.data
        if result.error:
            log.warning("%s integration error: %s", provider, result.error.code.value)
            return {
                "type": "integration_error",
                "integration": provider,
                "code": result.error.code.value,
                "message": build_tts_debug_message(provider, display_name, result.error.code),
            }
        return None

    async def _tts_gen(self, text: str, voice: str | None = None) -> bytes:
        """Receive compressed speech in memory; never write private speech to disk."""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice or self.tts_voice, connect_timeout=3, receive_timeout=8)
        chunks = []
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                chunks.append(chunk['data'])
        return b''.join(chunks)

    def text_to_audio(self, text: str, trim_pad_ms: float = 180.0, language: str | None = None):
        """Synthesize PCM16LE, falling back to the faster Edge voice when needed."""
        if not isinstance(text, str) or not text.strip():
            return b''
        if not isinstance(trim_pad_ms, (int, float)) or isinstance(trim_pad_ms, bool) or not math.isfinite(trim_pad_ms) or not 0 <= trim_pad_ms <= 5000:
            raise ValueError('Invalid speech padding')
        resolved = self._response_language(text, language, 'device')
        configured_voice = getattr(self, 'tts_voice', 'ko-KR-SunHiNeural')
        # Preserve a custom voice for its language; choose matching voices otherwise.
        voice = configured_voice if configured_voice.split('-')[0].lower() == resolved else voice_for_language(resolved)
        adapter = getattr(self, 'gemini_tts', None)
        key = (getattr(self, 'tts_backend', 'edge_tts'), getattr(adapter, 'model', ''),
               getattr(adapter, 'voice', ''), voice, resolved, hashlib.sha256(text.encode('utf-8')).digest(), float(trim_pad_ms))
        cache = getattr(self, '_audio_cache', None)
        if cache is None:
            cache = self._audio_cache = AudioCache()
        return cache.get_or_create(key, lambda: self._synthesize_audio(text, trim_pad_ms, voice))

    def _synthesize_audio(self, text: str, trim_pad_ms: float, voice: str) -> bytes:
        if getattr(self, "tts_backend", "edge_tts") == "gemini_tts":
            adapter = getattr(self, "gemini_tts", None)
            if adapter is not None:
                try:
                    audio = adapter.synthesize(text)
                    if audio:
                        log.info("Gemini TTS generated: %d bytes", len(audio))
                        return audio
                except Exception as exc:
                    log.warning("Gemini TTS failed (%s); using Edge TTS", type(exc).__name__)
            else:
                log.warning("Gemini TTS is not configured; using Edge TTS")
        return self._edge_text_to_audio(text, trim_pad_ms=trim_pad_ms, voice=voice)

    def _edge_text_to_audio(self, text: str, trim_pad_ms: float = 180.0, voice: str | None = None):
        """텍스트를 오디오로 변환 - TTS 생성 및 오디오 후처리"""
        try:
            import importlib

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
            log.info("Generating TTS (characters=%d)", len(text))

            # Each synthesis owns and closes its loop, including short-lived TTS workers.
            loop = asyncio.new_event_loop()
            try:
                mp3 = loop.run_until_complete(asyncio.wait_for(self._tts_gen(text, voice), timeout=15))
            except Exception as exc:
                log.error("TTS generation failed (%s)", type(exc).__name__)
                return b""
            finally:
                loop.close()
            if not mp3:
                log.error("TTS returned empty compressed audio")
                return b""

            # 오디오 로드 및 리샘플링 (16kHz, mono)
            pcm_f32, sr = librosa.load(io.BytesIO(mp3), sr=16000, mono=True)

            if pcm_f32.size == 0:
                log.error("TTS audio empty after decoding")
                return b""

            # 오디오 후처리 - DC 오프셋 제거 및 무음 구간 트림
            pcm_f32 = (pcm_f32 - np.mean(pcm_f32)).astype(np.float32, copy=False)
            if audio_proc_available:
                # 청크형 TTS에서는 pad를 과도하게 주면 경계마다 불필요한 무음이 커진다.
                pcm_f32 = trim_energy(
                    pcm_f32,
                    sr=sr,
                    top_db=45.0,
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
            log.error("TTS failed (%s)", type(exc).__name__)
            return b""
