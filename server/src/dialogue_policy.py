"""Turn-scoped language policy and bounded, memory-only speech reuse."""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from typing import Callable, Hashable

SUPPORTED_LANGUAGES = ('ko', 'en', 'zh', 'ja', 'es')
LANGUAGE_NAMES = {'ko': 'Korean', 'en': 'English', 'zh': 'Chinese', 'ja': 'Japanese', 'es': 'Spanish'}
VOICES = {'ko': 'ko-KR-SunHiNeural', 'en': 'en-US-JennyNeural', 'zh': 'zh-CN-XiaoxiaoNeural',
          'ja': 'ja-JP-NanamiNeural', 'es': 'es-ES-ElviraNeural'}


def normalize_language(value: str | None, *, allow_auto: bool = False) -> str:
    if value is None and allow_auto:
        return 'auto'
    if not isinstance(value, str):
        raise ValueError('Choose auto, ko, en, zh, ja, or es')
    language = value.strip().lower().replace('_', '-').split('-')[0]
    if language in SUPPORTED_LANGUAGES or (allow_auto and language == 'auto'):
        return language
    raise ValueError('Choose auto, ko, en, zh, ja, or es')


def detect_language(text: str, fallback: str = 'ko') -> str:
    """Resolve recognizable text without a remote classifier; fixed choice wins."""
    if re.search(r'[\u3040-\u30ff]', text):
        return 'ja'
    if re.search(r'[\uac00-\ud7a3]', text):
        return 'ko'
    if re.search(r'[\u3400-\u9fff]', text):
        # Han-only text is ambiguous between Japanese and Chinese. Keep a known Japanese turn.
        return 'ja' if fallback == 'ja' else 'zh'
    if re.search(r'[¿¡ñáéíóúü]|\b(hola|gracias|tareas?|recuerd[oa]s?|enciende|apaga|añade|muéstrame|muestra|como|puedes|quiero|explica|por favor)\b', text, re.I):
        return 'es'
    if re.search(r'\b(hello|hi|how|what|please|show|tasks?|remember|turn|explain|thanks|thank|the|you|my)\b', text, re.I):
        return 'en'
    if re.search(r'[A-Za-z]', text):
        # Latin words with no strong signal continue Spanish, otherwise default to English.
        return 'es' if fallback == 'es' else 'en'
    return normalize_language(fallback)


def resolve_language(text: str, language: str | None = None, configured: str = 'auto', fallback: str = 'ko') -> str:
    chosen = normalize_language(language if language is not None else configured, allow_auto=True)
    return detect_language(text, fallback) if chosen == 'auto' else chosen


def voice_for_language(language: str) -> str:
    return VOICES[normalize_language(language)]


def conversation_instructions(language: str, short_responses: bool, text: str) -> str:
    detail = bool(re.search(r'자세|상세|구체|단계별|\b(detail|detailed|step.by.step|exhaustive|detall|paso a paso)\w*|详细|詳細|詳しく|詳しい|くわしく', text, re.I))
    style = ('Use natural, warm spoken language. Answer directly, without an introduction, repeated self-identification, '
             'markdown, emojis, or unsolicited follow-up questions. Follow the current request and relevant recent context. '
             'Do not invent facts or claim actions without verified results. ')
    if short_responses and not detail:
        style += 'Default to 1–2 sentences; keep ordinary conversation under 40 words. Preserve needed IDs, results, and failure guidance. '
    else:
        style += 'Provide the requested detail; keep the explanation focused and useful. '
    return f'[Conversation policy] Reply in {LANGUAGE_NAMES[normalize_language(language)]}. ' + style


def phrase(language: str, ko: str, en: str, zh: str, ja: str, es: str) -> str:
    return {'ko': ko, 'en': en, 'zh': zh, 'ja': ja, 'es': es}[normalize_language(language)]


# Only exact server-owned error strings are translated, never stored item content.
_MESSAGES = {
    '도구 실행에 실패했어요. 입력과 연결 설정을 확인해 주세요.': ('The action failed. Check the input and connection settings.', '操作失败了。请检查输入和连接设置。', '操作に失敗しました。入力と接続設定を確認してください。', 'La operación falló. Revisa los datos y la conexión.'),
    '요청을 8000자 이내로 입력해 주세요.': ('Keep the request under 8000 characters.', '请输入8000字以内的请求。', 'リクエストは8000文字以内にしてください。', 'Escribe una solicitud de menos de 8000 caracteres.'),
    '사용자 식별자를 확인해 주세요.': ('Check your user identifier.', '请检查用户标识。', 'ユーザー識別子を確認してください。', 'Revisa tu identificador de usuario.'),
    '항목 번호를 확인해 주세요.': ('Check the item number.', '请检查项目编号。', '項目番号を確認してください。', 'Revisa el número del elemento.'),
    '홈 제어를 사용하려면 Home Assistant 연결과 허용 목록을 설정해 주세요.': ('Connect Home Assistant and choose the devices you want to allow.', '请连接Home Assistant并选择允许控制的设备。', 'Home Assistantを接続し、操作を許可する機器を選んでください。', 'Conecta Home Assistant y elige los dispositivos permitidos.'),
    '홈 제어 요청이 너무 많아요. 요청을 나누어 주세요.': ('There are too many home actions. Split the request.', '家庭设备操作过多。请分次请求。', 'ホーム操作が多すぎます。リクエストを分けてください。', 'Hay demasiadas acciones. Divide la solicitud.'),
    '같은 이름의 홈 기기가 여러 개예요. 정확한 기기 ID를 알려주세요.': ('Several devices share that name. Give the exact device ID.', '多个设备同名。请提供准确的设备ID。', '同名の機器があります。正確な機器IDを教えてください。', 'Hay varios dispositivos con ese nombre. Indica su ID exacto.'),
    '홈 기기 상태를 확인하지 못했어요. Home Assistant 연결과 허용 목록을 확인해 주세요.': ('I could not verify the device state. Check Home Assistant and the allowed devices.', '无法确认设备状态。请检查Home Assistant连接和允许的设备。', '機器の状態を確認できません。Home Assistantと許可した機器を確認してください。', 'No pude verificar el estado. Revisa Home Assistant y los dispositivos permitidos.'),
    '허용된 홈 기기를 찾지 못했어요. 정확한 이름 또는 기기 ID를 확인해 주세요.': ('I could not find an allowed device. Check its name or ID.', '未找到允许的设备。请检查名称或ID。', '許可された機器が見つかりません。名前またはIDを確認してください。', 'No encontré un dispositivo permitido. Revisa su nombre o ID.'),
    '요청한 작업의 실행 또는 조회 결과를 확인하지 못했어요. 다시 요청해 주세요.': ('I could not verify the requested result. Please try again.', '无法确认请求的结果。请重试。', 'リクエストの結果を確認できません。もう一度お願いします。', 'No pude verificar el resultado. Inténtalo de nuevo.'),
    '답변 엔진에 연결하지 못했어요. 모델 설정을 확인해 주세요.': ('I could not connect to the answer engine. Check the model settings.', '无法连接回答引擎。请检查模型设置。', '応答エンジンに接続できません。モデル設定を確認してください。', 'No pude conectar con el modelo. Revisa su configuración.'),
    '응답이 너무 길어요. 요청을 나누어 다시 말씀해 주세요.': ('The response is too long. Split the request and try again.', '回答过长。请分次请求。', '応答が長すぎます。リクエストを分けてください。', 'La respuesta es demasiado larga. Divide la solicitud.'),
    '홈 기기를 바꾸려면 이번 요청에서 기기 이름과 켜기 또는 끄기를 직접 말씀해 주세요.': ('To control a device, say its name and explicitly ask to turn it on or off.', '要控制设备，请明确说出设备名称和打开或关闭。', '機器を操作するには、名前とオンまたはオフを明確に指示してください。', 'Para controlar un dispositivo, indica su nombre y pide encenderlo o apagarlo.'),
    '이번 요청의 도구 실행 한도에 도달했어요. 요청을 나누어 주세요.': ('The action limit for this request was reached. Split the request.', '已达到本次操作上限。请分次请求。', 'このリクエストの操作上限に達しました。分けてください。', 'Se alcanzó el límite de acciones. Divide la solicitud.'),
    '결과가 너무 많아요. 검색어를 좁혀 주세요.': ('There are too many results. Narrow the search.', '结果过多。请缩小搜索范围。', '結果が多すぎます。検索範囲を絞ってください。', 'Hay demasiados resultados. Acota la búsqueda.'),
    '응답을 처리하지 못했어요. 잠시 후 다시 말씀해 주세요.': ('I could not process the response. Please try again shortly.', '无法处理回答。请稍后重试。', '応答を処理できませんでした。少し待って再度お願いします。', 'No pude procesar la respuesta. Inténtalo de nuevo en un momento.'),
    '잘 이해하지 못했어요. 한 번만 다시 말씀해 주세요.': ('I did not quite understand. Please say it again.', '没听明白，请再说一次。', 'うまく理解できませんでした。もう一度お願いします。', 'No lo entendí bien. Repítelo, por favor.'),
    '죄송해요, 오류가 발생했어요.': ('Something went wrong. Please try again.', '发生错误了。请重试。', 'エラーが発生しました。もう一度お願いします。', 'Ocurrió un error. Inténtalo de nuevo.'),
    '모델이 로드되지 않았습니다.': ('The model is not loaded. Check its configuration.', '模型未加载。请检查设置。', 'モデルが読み込まれていません。設定を確認してください。', 'El modelo no está cargado. Revisa su configuración.'),
}


def localize_message(text: str, language: str) -> str:
    language = normalize_language(language)
    values = _MESSAGES.get(text)
    return values[SUPPORTED_LANGUAGES.index(language) - 1] if language != 'ko' and values else text


class AudioCache:
    """LRU/TTL PCM cache; coalesce identical synthesis without persisting audio."""
    def __init__(self, max_bytes: int = 8 * 1024 * 1024, ttl_seconds: float = 300,
                 max_entries: int = 128, clock: Callable[[], float] = time.monotonic):
        if max_bytes < 1 or ttl_seconds <= 0 or max_entries < 1:
            raise ValueError('Invalid audio cache limits')
        self.max_bytes, self.ttl_seconds, self.max_entries = max_bytes, ttl_seconds, max_entries
        self.clock = clock
        self._entries: OrderedDict = OrderedDict()
        self._pending: dict[Hashable, Future] = {}
        self._lock = threading.Lock()
        self.bytes_used = 0

    def _prune(self, now: float) -> None:
        for key, (expires, value) in list(self._entries.items()):
            if expires <= now:
                self.bytes_used -= len(value)
                del self._entries[key]

    def get_or_create(self, key: Hashable, synthesize: Callable[[], bytes]) -> bytes:
        with self._lock:
            self._prune(self.clock())
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key][1]
            pending = self._pending.get(key)
            leader = pending is None
            if leader:
                pending = Future()
                self._pending[key] = pending
        if not leader:
            return pending.result()
        try:
            audio = synthesize()
            if not isinstance(audio, bytes):
                raise TypeError('Speech synthesis must return bytes')
            with self._lock:
                if audio and len(audio) <= self.max_bytes:
                    self._entries[key] = (self.clock() + self.ttl_seconds, audio)
                    self.bytes_used += len(audio)
                    while self.bytes_used > self.max_bytes or len(self._entries) > self.max_entries:
                        _, (_, removed) = self._entries.popitem(last=False)
                        self.bytes_used -= len(removed)
                pending.set_result(audio)
            return audio
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)
