// ============================================================
// protocol.cpp — 패킷 프로토콜 구현
// ============================================================
// 역할: 바이너리 패킷의 송신/수신, JSON CMD 파싱,
//       TTS 오디오 링 버퍼 관리 및 스피커 재생.
//
// 구조:
//   1) 경량 JSON 파서 (ArduinoJson 미사용, 메모리 절약)
//   2) 링 버퍼 (TTS 오디오 스트리밍 수신 → 비블로킹 재생)
//   3) 수신 상태머신 (RX_TYPE → RX_LEN0 → RX_LEN1 → RX_PAYLOAD)
//   4) 송신 (헤더 3B 단일 write + 페이로드 재시도 루프)
// ============================================================

#include "protocol.h"
#include "connection.h"
#include "config.h"
#include "led_control.h"
#include "robot_bridge.h"
#include "servo_control.h"
#include "display_control.h"
#include <M5Unified.h>
#include <CcoliRobotControl.h>
#include <ctype.h>
#include <string.h>

// ── 버퍼 크기 상수 ──
// RX_MAX_PAYLOAD는 서버가 한 프레임에 실어 보내는 최대 페이로드와 맞춘다.
// (server/src/protocol.py: DEVICE_MAX_PACKET_PAYLOAD)
// 정적 버퍼 하나로 모든 패킷을 받으므로 힙 단편화가 생기지 않고,
// 시리얼 노이즈로 만들어진 과대 길이 헤더도 버퍼를 넘길 수 없다.
#ifndef RX_MAX_PACKET_PAYLOAD
#define RX_MAX_PACKET_PAYLOAD 2048
#endif
static constexpr size_t RX_MAX_PAYLOAD = RX_MAX_PACKET_PAYLOAD;

#ifndef AUDIO_RING_BUFFER_SIZE
#define AUDIO_RING_BUFFER_SIZE 32768
#endif
static constexpr size_t AUDIO_PLAY_BUFFER_SIZE = AUDIO_RING_BUFFER_SIZE;

// ── 수신 상태머신 ──
// 패킷 구조: [1B type][2B length LE][length B payload]
// 상태: TYPE → LEN0 → LEN1 → PAYLOAD → (핸들러 호출) → TYPE
enum RxStage { RX_TYPE, RX_LEN0, RX_LEN1, RX_PAYLOAD };
static RxStage rx_stage = RX_TYPE;
static uint8_t rx_type = 0;       // 현재 수신 중인 패킷 타입
static uint16_t rx_len = 0;       // 현재 패킷의 페이로드 길이
static uint16_t rx_pos = 0;       // 현재까지 수신한 페이로드 바이트 수
static bool rx_overflow = false;  // rx_len이 버퍼보다 큰 패킷(=손상 프레임) 표시
static uint8_t rx_buf[RX_MAX_PAYLOAD];  // 모든 패킷 공용 수신 버퍼 (정적)

// ── TTS 오디오 링 버퍼 ──
// 서버에서 스트리밍되는 TTS PCM 데이터를 저장하고
// 비블로킹으로 스피커에 공급하는 원형 버퍼
static uint8_t audio_ring_buffer[AUDIO_PLAY_BUFFER_SIZE];
static size_t audio_ring_head = 0;   // 쓰기 위치
static size_t audio_ring_tail = 0;   // 읽기 위치
static size_t audio_ring_size = AUDIO_PLAY_BUFFER_SIZE;
static bool audio_playing = false;
static bool capture_locked = false;
static bool capture_lock_waiting_for_playback = false;

// PING 타이밍
static uint32_t last_ping_ms = 0;
static uint32_t last_peer_rx_ms = 0;
static Stream* robot_status_transport = nullptr;
static constexpr size_t ROBOT_STATUS_QUEUE_SIZE = 4;
static char robot_status_queue[ROBOT_STATUS_QUEUE_SIZE][RX_MAX_PAYLOAD+1];
static size_t robot_status_head=0,robot_status_count=0;
bool protocol_send_robot_status(const char* json) {
  if (!json) return false;
  const size_t len = strlen(json);
  if (len == 0 || len > RX_MAX_PAYLOAD) return false;
  // Newest state, particularly STOPPED, wins under malicious/flooded input.
  if(robot_status_count==ROBOT_STATUS_QUEUE_SIZE){
    robot_status_head=(robot_status_head+1)%ROBOT_STATUS_QUEUE_SIZE;
    --robot_status_count;
  }
  const size_t target=(robot_status_head+robot_status_count)%ROBOT_STATUS_QUEUE_SIZE;
  memcpy(robot_status_queue[target],json,len+1);++robot_status_count;
  return true;
}
void protocol_flush_robot_status() {
  if(!robot_status_transport||!robot_status_count)return;
  // Pop before sending: safety pumping may enqueue a new status while a slow
  // socket is being serviced. A stack copy keeps the in-flight frame immutable.
  char frame[RX_MAX_PAYLOAD+1];
  memcpy(frame,robot_status_queue[robot_status_head],sizeof(frame));
  robot_status_head=(robot_status_head+1)%ROBOT_STATUS_QUEUE_SIZE;--robot_status_count;
  protocol_send_packet(*robot_status_transport,PTYPE_ROBOT_STATUS,
      reinterpret_cast<const uint8_t*>(frame),static_cast<uint16_t>(strlen(frame)));
}

#define DEBUG_PRINTLN(msg) do { if (connection_debug_logging_enabled()) Serial.println(msg); } while (0)

static inline bool wired_tts_mode() {
  return connection_is_wired_mode();
}

static inline size_t audio_output_bytes_per_sample() {
  return wired_tts_mode() ? 1 : sizeof(int16_t);
}

static inline uint32_t audio_output_sample_rate() {
  return wired_tts_mode() ? WIRED_TTS_SAMPLE_RATE : AUDIO_SAMPLE_RATE;
}

static inline size_t audio_output_start_threshold_bytes() {
  // Start playback a bit earlier so the first syllable is not held back waiting
  // for a large prebuffer. Keep wired mode slightly more conservative.
  return wired_tts_mode() ? 1024 : 2048;
}

static bool stream_write_all(Stream& transport, const uint8_t* data, size_t len) {
  const uint8_t* p = data;
  size_t remaining = len;
  while (remaining > 0) {
    size_t written = connection_write(transport, p, remaining);
    if (written == 0) return false;
    p += written;
    remaining -= written;
  }
  return true;
}

static uint8_t linear16_to_mulaw(int16_t sample) {
  static constexpr int32_t MULAW_BIAS = 0x84;
  static constexpr int32_t MULAW_CLIP = 32635;

  uint8_t sign = 0x00;
  int32_t magnitude = sample;
  if (magnitude < 0) {
    sign = 0x80;
    magnitude = -magnitude;
  }
  if (magnitude > MULAW_CLIP) {
    magnitude = MULAW_CLIP;
  }

  int32_t biased = magnitude + MULAW_BIAS;
  uint8_t exponent = 7;
  int32_t mask = 0x4000;
  while (exponent > 0 && (biased & mask) == 0) {
    exponent--;
    mask >>= 1;
  }
  uint8_t mantissa = (uint8_t)((biased >> (exponent + 3)) & 0x0F);
  return (uint8_t)(~(sign | (uint8_t)(exponent << 4) | mantissa));
}

static int16_t mulaw_to_linear16(uint8_t value) {
  static constexpr int16_t MULAW_BIAS = 0x84;

  value = (uint8_t)~value;
  uint8_t sign = value & 0x80;
  uint8_t exponent = (value >> 4) & 0x07;
  uint8_t mantissa = value & 0x0F;
  int16_t sample = (int16_t)(((MULAW_BIAS + ((int16_t)mantissa << 3)) << exponent) - MULAW_BIAS);
  return sign ? (int16_t)-sample : sample;
}

static uint16_t wired_audio_encoded_length(uint16_t pcm_len) {
  uint16_t usable = (uint16_t)(pcm_len - (pcm_len % 2));
  if (usable == 0) return 0;
  return (uint16_t)((usable / 4) + ((usable % 4) ? 1 : 0));
}

// ════════════════════════════════════════════
// 경량 JSON 파서
// ════════════════════════════════════════════
// ArduinoJson 라이브러리 대신 직접 구현하여 메모리 절약.
// 서버가 보내는 CMD JSON에서 특정 키의 값을 추출.
// 지원 타입: string, int, bool

// json_get_string — JSON에서 문자열 값 추출
// 예: {"action":"SERVO_SET"} → key="action", out="SERVO_SET"
static bool json_get_string(const char* json, const char* key, char* out, size_t out_sz) {
  char pat[64];
  snprintf(pat, sizeof(pat), "\"%s\"", key);
  const char* p = strstr(json, pat);
  if (!p) return false;
  p = strchr(p, ':');
  if (!p) return false;
  p++;
  while (*p && isspace((unsigned char)*p)) p++;
  if (*p != '"') return false;
  p++;
  size_t i = 0;
  while (*p && *p != '"' && i + 1 < out_sz) {
    out[i++] = *p++;
  }
  out[i] = 0;
  return (*p == '"');
}

// json_get_int — JSON에서 정수 값 추출
// 예: {"angle":90} → key="angle", out=90
static bool json_get_int(const char* json, const char* key, int* out) {
  char pat[64];
  snprintf(pat, sizeof(pat), "\"%s\"", key);
  const char* p = strstr(json, pat);
  if (!p) return false;
  p = strchr(p, ':');
  if (!p) return false;
  p++;
  while (*p && isspace((unsigned char)*p)) p++;
  bool neg = false;
  if (*p == '-') { neg = true; p++; }
  if (!isdigit((unsigned char)*p)) return false;
  long v = 0;
  while (isdigit((unsigned char)*p)) {
    v = v * 10 + (*p - '0');
    p++;
  }
  if (neg) v = -v;
  *out = (int)v;
  return true;
}

// json_get_bool — JSON에서 불리언 값 추출
// 예: {"meaningful":true} → key="meaningful", out=true
static bool json_get_bool(const char* json, const char* key, bool* out) {
  char pat[64];
  snprintf(pat, sizeof(pat), "\"%s\"", key);
  const char* p = strstr(json, pat);
  if (!p) return false;
  p = strchr(p, ':');
  if (!p) return false;
  p++;
  while (*p && isspace((unsigned char)*p)) p++;
  if (!strncmp(p, "true", 4))  { *out = true;  return true; }
  if (!strncmp(p, "false", 5)) { *out = false; return true; }
  return false;
}

// ════════════════════════════════════════════
// TTS 오디오 링 버퍼 연산
// ════════════════════════════════════════════
// 원형 버퍼로 수신(push)과 재생(pop)을 동시에 처리.
// memcpy + wrap-around 방식으로 byte-by-byte 대비 성능 최적화.

// audio_ring_available — 쓰기 가능한 바이트 수
static size_t audio_ring_available() {
  if (audio_ring_head >= audio_ring_tail)
    return audio_ring_size - (audio_ring_head - audio_ring_tail) - 1;
  return audio_ring_tail - audio_ring_head - 1;
}

// audio_ring_used — 읽기 가능한 바이트 수 (저장된 데이터)
static size_t audio_ring_used() {
  if (audio_ring_head >= audio_ring_tail)
    return audio_ring_head - audio_ring_tail;
  return audio_ring_size - (audio_ring_tail - audio_ring_head);
}

// audio_ring_push — 데이터를 링 버퍼에 추가
// 공간 부족 시 오래된 데이터를 버리고 새 데이터 수용 (오디오 끊김 최소화)
static bool audio_ring_push(const uint8_t* data, size_t len) {
  size_t sample_bytes = audio_output_bytes_per_sample();
  // PCM16 샘플 경계 유지: tail이 홀수 바이트면 1바이트 버려 정렬 복구
  if (sample_bytes > 1 && (audio_ring_tail & 0x01)) {
    audio_ring_tail = (audio_ring_tail + 1) % audio_ring_size;
  }

  if (audio_ring_available() < len) {
    // 오버플로 방지: 오래된 데이터 드롭
    size_t to_drop = len - audio_ring_available() + 1024;
    size_t used = audio_ring_used();
    // 샘플 경계 보존
    if (sample_bytes > 1) {
      to_drop = (to_drop + 1) & ~((size_t)1);
      used &= ~((size_t)1);
    }
    if (to_drop > used) to_drop = used;
    audio_ring_tail = (audio_ring_tail + to_drop) % audio_ring_size;
    if (audio_ring_available() < len) return false;
  }
  // memcpy with wrap-around (버퍼 끝을 넘어가면 두 번에 나눠 복사)
  size_t first = audio_ring_size - audio_ring_head;
  if (first >= len) {
    memcpy(audio_ring_buffer + audio_ring_head, data, len);
  } else {
    memcpy(audio_ring_buffer + audio_ring_head, data, first);
    memcpy(audio_ring_buffer, data + first, len - first);
  }
  audio_ring_head = (audio_ring_head + len) % audio_ring_size;
  return true;
}

// audio_ring_pop — 링 버퍼에서 데이터 읽기 (스피커 재생용)
static size_t audio_ring_pop(uint8_t* data, size_t max_len) {
  size_t used = audio_ring_used();
  size_t to_read = (used < max_len) ? used : max_len;
  if (to_read == 0) return 0;
  // memcpy with wrap-around
  size_t first = audio_ring_size - audio_ring_tail;
  if (first >= to_read) {
    memcpy(data, audio_ring_buffer + audio_ring_tail, to_read);
  } else {
    memcpy(data, audio_ring_buffer + audio_ring_tail, first);
    memcpy(data + first, audio_ring_buffer, to_read - first);
  }
  audio_ring_tail = (audio_ring_tail + to_read) % audio_ring_size;
  return to_read;
}

// ════════════════════════════════════════════
// 수신 패킷 핸들러
// ════════════════════════════════════════════

// handleAudioOut — AUDIO_OUT(0x12) 패킷 처리
// 서버에서 스트리밍되는 TTS 오디오를 링 버퍼에 저장.
// 1KB 이상 축적되면 재생 시작 (짧은 응답 지연 최소화)
static void handleAudioOut(const uint8_t* payload, uint16_t len) {
  if (!wired_tts_mode()) {
    // 16-bit PCM alignment (1 sample = 2 bytes)
    if (len & 0x01) len -= 1;
    if (len < 2) return;  // 최소 1샘플(2B) 필요
  } else if (len == 0) {
    return;
  }

  if (!audio_ring_push(payload, len)) return;

  if (!audio_playing && audio_ring_used() >= audio_output_start_threshold_bytes()) {
    audio_playing = true;
    M5.Speaker.setVolume(180);
  }
}

// ── Helper functions for ROBOT_EMOTION ──
static FaceType face_from_string(const char* face) {
  if (!face) return FACE_NEUTRAL;
  if (strcmp(face, "happy") == 0) return FACE_HAPPY;
  if (strcmp(face, "sad") == 0) return FACE_SAD;
  if (strcmp(face, "angry") == 0) return FACE_ANGRY;
  if (strcmp(face, "surprised") == 0) return FACE_SURPRISED;
  if (strcmp(face, "sleepy") == 0) return FACE_SLEEPY;
  if (strcmp(face, "love") == 0) return FACE_LOVE;
  if (strcmp(face, "curious") == 0) return FACE_CURIOUS;
  if (strcmp(face, "excited") == 0) return FACE_EXCITED;
  if (strcmp(face, "confused") == 0) return FACE_CONFUSED;
  return FACE_NEUTRAL;
}

static ServoAction action_from_string(const char* action) {
  if (!action) return ACTION_NONE;
  if (strcmp(action, "nod_yes") == 0) return ACTION_NOD_YES;
  if (strcmp(action, "nod_no") == 0) return ACTION_NOD_NO;
  if (strcmp(action, "tilt_curious") == 0) return ACTION_TILT_CURIOUS;
  if (strcmp(action, "bounce_happy") == 0) return ACTION_BOUNCE_HAPPY;
  if (strcmp(action, "droop_sad") == 0) return ACTION_DROOP_SAD;
  if (strcmp(action, "shake_angry") == 0) return ACTION_SHAKE_ANGRY;
  if (strcmp(action, "startle") == 0) return ACTION_STARTLE;
  if (strcmp(action, "dance") == 0) return ACTION_DANCE;
  if (strcmp(action, "sleep_drift") == 0) return ACTION_SLEEP_DRIFT;
  if (strcmp(action, "wiggle") == 0) return ACTION_WIGGLE;
  return ACTION_NONE;
}
// handleCmdJson — CMD(0x11) 패킷 처리
// 서버가 보내는 JSON 명령을 파싱하여 서보/LED 동작 실행.
// JSON 형식: {"action":"...", "angle":N, "emotion":"...", "servo_action":"...",
//             "meaningful":bool, "recognized":bool, "sid":N}
static void handleCmdJson(const uint8_t* payload, uint16_t len) {
  // 정적 버퍼에 null-terminated 문자열로 복사
  static char json[RX_MAX_PAYLOAD + 1];
  uint16_t n = (len > RX_MAX_PAYLOAD) ? RX_MAX_PAYLOAD : len;
  memcpy(json, payload, n);
  json[n] = 0;

  if (strstr(json, "ROBOT_CONTROL") != nullptr) {
    if (robot_bridge_enabled()) robot_bridge_forward_json(json);
    else servo_handle_control_json(json, n);
    return;
  }
  // JSON 필드 추출
  char action[32] = {0};
  int sid = -1, angle = -1;
  bool meaningful = false, recognized = false;
  char emotion[32] = {0}, servo_action[32] = {0};

  bool has_action = json_get_string(json, "action", action, sizeof(action));
  json_get_int(json, "sid", &sid);
  bool has_angle = json_get_int(json, "angle", &angle);
  json_get_bool(json, "meaningful", &meaningful);
  json_get_bool(json, "recognized", &recognized);
  json_get_string(json, "emotion", emotion, sizeof(emotion));
  json_get_string(json, "servo_action", servo_action, sizeof(servo_action));

  if (has_action && strcmp(action, "MIC_LOCK") == 0) {
    capture_locked = true;
    capture_lock_waiting_for_playback = true;
    robot_bridge_set_speech_active(true);
    return;
  }
  if (has_action && strcmp(action, "MIC_UNLOCK") == 0) {
    capture_locked = false;
    capture_lock_waiting_for_playback = false;
    robot_bridge_set_speech_active(false);
    return;
  }

  // ── ROBOT_STATE: companion-forward first, local fallback second ──
  if (has_action && strcmp(action, "ROBOT_STATE") == 0) {
    if (robot_bridge_enabled()) {
      robot_bridge_forward_json(json);
    }

    char face[32] = {0};
    char display_text[32] = {0};
    json_get_string(json, "face", face, sizeof(face));
    json_get_string(json, "display_text", display_text, sizeof(display_text));

    display_show_face(face_from_string(face));
    if (display_text[0]) display_set_status_text(display_text);
    if (display_text[0]) display_set_speech_text(display_text);
    display_set_state(DS_SPEAKING);

    ServoAction sa = action_from_string(servo_action);
    if (sa != ACTION_NONE) servo_play_action(sa);

    led_show_emotion(emotion);
    return;
  }

  // ── ROBOT_EMOTION: display face + servo action + LED ──
  if (has_action && strcmp(action, "ROBOT_EMOTION") == 0) {
    char face[32] = {0};
    char display_text[32] = {0};
    json_get_string(json, "face", face, sizeof(face));
    json_get_string(json, "servo_action", servo_action, sizeof(servo_action));
    json_get_string(json, "display_text", display_text, sizeof(display_text));
    
    display_show_face(face_from_string(face));
    if (display_text[0]) display_set_status_text(display_text);
    if (display_text[0]) display_set_speech_text(display_text);
    display_set_state(DS_SPEAKING);
    
    ServoAction sa = action_from_string(servo_action);
    if (sa != ACTION_NONE) servo_play_action(sa);
    
    led_show_emotion(emotion);
    return;
  }
  // ── EMOTION 액션: LED 색상 + 서보 제스처 ──
  if (has_action && strcmp(action, "EMOTION") == 0) {
    led_show_emotion(emotion);
    if (strcmp(servo_action, "WIGGLE_FAST") == 0 || strcmp(servo_action, "WIGGLE") == 0) {
      servo_wiggle();
    } else if (strcmp(servo_action, "NOD") == 0) {
      servo_set_angle(110);
      servo_set_angle(SERVO_CENTER_ANGLE);
    } else if (strcmp(servo_action, "CENTER") == 0) {
      servo_set_angle(SERVO_CENTER_ANGLE);
    }
    return;
  }

  if (has_action && strcmp(action, "STOP") == 0) { servo_stop(); return; }
  // ── 무의미한 발화: WIGGLE만 허용 ──
  if (!meaningful) {
    if (strcmp(action, "WIGGLE") == 0) servo_wiggle();
    return;
  }

  // ── 유의미한 명령 디스패치 ──
  if (strcmp(action, "ROTATE") == 0) {
    servo_rotate();
  } else if (strcmp(action, "STOP") == 0) {
    servo_stop();
  } else if (strcmp(action, "SERVO_SET") == 0 && has_angle) {
    int servo = 0;
    json_get_int(json, "servo", &servo);
    servo_set_angle(servo, angle);  // Legacy actuator packets cannot bypass v1 authorization.
  }
}

// ════════════════════════════════════════════
// 공개 API 구현
// ════════════════════════════════════════════

// protocol_init — 수신 상태머신을 초기 상태로 리셋
// 서버 재연결 시 호출하여 잔여 수신 데이터 무효화
void protocol_init() {
  rx_stage = RX_TYPE;
  rx_len = 0;
  rx_pos = 0;
  rx_overflow = false;
  last_ping_ms = 0;
  last_peer_rx_ms = 0;
  capture_locked = false;
  capture_lock_waiting_for_playback = false;
}

// protocol_send_packet — 패킷 1개 송신
// 헤더(3B)를 단일 write로 전송, 페이로드는 재시도 루프로 완전 전송 보장.
// 전송 실패(write 반환 0) 시 연결 종료.
bool protocol_send_packet(Stream& transport, uint8_t type, const uint8_t* payload, uint16_t len) {
  if (connection_is_wired_mode() && type == PTYPE_AUDIO && payload && len > 0) {
    uint16_t encoded_len = wired_audio_encoded_length(len);
    uint8_t hdr[3] = { type, (uint8_t)(encoded_len & 0xFF), (uint8_t)((encoded_len >> 8) & 0xFF) };
    if (!stream_write_all(transport, hdr, sizeof(hdr))) {
      return false;
    }

    static uint8_t encoded_chunk[256];
    size_t chunk_len = 0;
    size_t usable = (size_t)(len - (len % 2));
    for (size_t offset = 0; offset < usable; offset += 4) {
      int16_t sample_a = (int16_t)((payload[offset + 1] << 8) | payload[offset]);
      int16_t sample_b = sample_a;
      if (offset + 3 < usable) {
        sample_b = (int16_t)((payload[offset + 3] << 8) | payload[offset + 2]);
      }
      int32_t mixed = ((int32_t)sample_a + (int32_t)sample_b) / 2;
      encoded_chunk[chunk_len++] = linear16_to_mulaw((int16_t)mixed);

      if (chunk_len == sizeof(encoded_chunk)) {
        if (!stream_write_all(transport, encoded_chunk, chunk_len)) {
          return false;
        }
        chunk_len = 0;
      }
    }

    if (chunk_len > 0 && !stream_write_all(transport, encoded_chunk, chunk_len)) {
      return false;
    }
    return true;
  }

  // 헤더: [type 1B][length_lo 1B][length_hi 1B]
  uint8_t hdr[3] = { type, (uint8_t)(len & 0xFF), (uint8_t)((len >> 8) & 0xFF) };
  if (!stream_write_all(transport, hdr, sizeof(hdr))) { return false; }

  // 페이로드: partial write 대응 재시도 루프
  if (len && payload) {
    if (!stream_write_all(transport, payload, len)) { return false; }
  }
  return true;
}

// protocol_poll — 서버에서 수신된 패킷을 폴링하여 핸들러에 디스패치
// 상태머신: RX_TYPE → RX_LEN0 → RX_LEN1 → RX_PAYLOAD → 핸들러 → RX_TYPE
// 헤더 3바이트만 1바이트씩 읽고, 페이로드는 readBytes()로 한 번에 받는다.
void protocol_poll(Stream& transport) {
  robot_status_transport = &transport;
  const uint32_t poll_started = millis();
  while (transport.available() > 0 && static_cast<uint32_t>(millis() - poll_started) < 5) {
    // ── 벌크 읽기: 모든 페이로드 (AUDIO_OUT / CMD 공통) ──
    // 바이트 단위 read()는 TTS 한 청크마다 수천 번 호출돼 재생이 끊기므로,
    // 페이로드 단계는 항상 readBytes()로 한 번에 받는다.
    if (rx_stage == RX_PAYLOAD) {
      size_t want = (size_t)(rx_len - rx_pos);
      size_t avail = (size_t)transport.available();
      if (avail == 0) break;
      if (want > avail) want = avail;
      if (want > 512) want = 512;

      size_t got;
      if (rx_overflow) {
        // 버퍼보다 큰 길이 = 손상된 헤더. 스트림에서 흘려보내고 재동기화한다.
        uint8_t sink[64];
        size_t take = (want < sizeof(sink)) ? want : sizeof(sink);
        got = transport.readBytes((char*)sink, take);
      } else {
        got = transport.readBytes((char*)(rx_buf + rx_pos), want);
      }
      if (got == 0) break;
      rx_pos += got;

      if (rx_pos >= rx_len) {
        last_peer_rx_ms = millis();
        if (!rx_overflow) {
          if (rx_type == PTYPE_CMD) handleCmdJson(rx_buf, rx_len);
          else if (rx_type == PTYPE_AUDIO_OUT) handleAudioOut(rx_buf, rx_len);
        }
        rx_overflow = false;
        rx_stage = RX_TYPE;
      }
      continue;
    }

    // ── 헤더 바이트 읽기 (1바이트씩, 3B만) ──
    int b = transport.read();
    if (b < 0) break;
    uint8_t byte = (uint8_t)b;

    switch (rx_stage) {
      case RX_TYPE:
        // 패킷 타입 바이트 수신
        rx_type = byte;
        rx_len = 0;
        rx_pos = 0;
        rx_stage = RX_LEN0;
        break;

      case RX_LEN0:
        // 길이 하위 바이트
        rx_len = (uint16_t)byte;
        rx_stage = RX_LEN1;
        break;

      case RX_LEN1:
        // 길이 상위 바이트 → 페이로드 수신 준비
        rx_len |= ((uint16_t)byte << 8);
        rx_pos = 0;
        if (rx_len == 0) {
          // 페이로드 없는 패킷 (PING, START, END 등)
          last_peer_rx_ms = millis();
          rx_stage = RX_TYPE;
        } else {
          rx_overflow = (rx_len > RX_MAX_PAYLOAD);
          if (rx_overflow) {
            DEBUG_PRINTLN("[PROTO] payload exceeds RX buffer; dropping frame");
          }
          rx_stage = RX_PAYLOAD;
        }
        break;

      case RX_PAYLOAD:
        // 위 벌크 경로가 RX_PAYLOAD를 전부 처리하므로 여기에는 도달하지 않는다.
        break;
    }
  }
}

// protocol_send_ping_if_needed — PING_INTERVAL_MS마다 keepalive 전송
// millis() 래핑(49.7일)에 안전한 unsigned 뺄셈 사용
void protocol_send_ping_if_needed(Stream& transport, uint32_t interval_ms) {
  uint32_t now = millis();
  if (now - last_ping_ms >= interval_ms) {
    if (protocol_send_packet(transport, PTYPE_PING, nullptr, 0))
      last_ping_ms = now;
  }
}

// protocol_audio_process — 링 버퍼에서 스피커로 오디오 공급
// 스피커가 idle일 때만 다음 청크를 넘겨 중복 재생/노이즈를 방지한다.
// playRaw() 실패(큐 가득 참) 시 읽은 데이터를 롤백하여 다음 사이클에 재시도한다.
void protocol_audio_process() {
  if (!audio_playing) return;

  size_t used_now = audio_ring_used();
  size_t sample_bytes = audio_output_bytes_per_sample();
  // 샘플 경계가 틀어진 상태면 1바이트 버려 복구
  if (sample_bytes > 1 && (used_now & 0x01)) {
    audio_ring_tail = (audio_ring_tail + 1) % audio_ring_size;
    used_now -= 1;
  }

  if (!M5.Speaker.isPlaying() && used_now >= sample_bytes) {
    static uint32_t last_playraw_fail_ms = 0;
    size_t chunk_size = 0;
    bool queued = false;

    if (wired_tts_mode()) {
      static uint8_t play_buffer_u8[1024];
      static int16_t play_buffer_i16[1024];
      chunk_size = audio_ring_pop(play_buffer_u8, sizeof(play_buffer_u8));
      for (size_t i = 0; i < chunk_size; ++i) {
        play_buffer_i16[i] = mulaw_to_linear16(play_buffer_u8[i]);
      }
      if (chunk_size >= 1) {
        queued = M5.Speaker.playRaw(play_buffer_i16, chunk_size, audio_output_sample_rate(), false, 1, 0);
      }
    } else {
      static uint8_t play_buffer[2048];
      chunk_size = audio_ring_pop(play_buffer, sizeof(play_buffer));
      chunk_size = (chunk_size / 2) * 2;
      if (chunk_size >= 2) {
        queued = M5.Speaker.playRaw((const int16_t*)play_buffer, chunk_size / 2, audio_output_sample_rate(), false, 1, 0);
      }
    }

    if (chunk_size >= sample_bytes) {
      if (!queued) {
        // 큐 가득 참 → 데이터 되돌리고 다음 사이클에 재시도
        audio_ring_tail = (audio_ring_tail + audio_ring_size - chunk_size) % audio_ring_size;
        uint32_t now = millis();
        if (now - last_playraw_fail_ms >= 500) {
          DEBUG_PRINTLN("[AUDIO_PROC] playRaw queue full; retry next cycle");
          last_playraw_fail_ms = now;
        }
      }
    }
  }

  // 버퍼 소진 + 재생 완료 → 재생 종료
  if (audio_ring_used() == 0 && !M5.Speaker.isPlaying()) {
    audio_playing = false;
    if (capture_locked && capture_lock_waiting_for_playback) {
      capture_locked = false;
      capture_lock_waiting_for_playback = false;
    }
  }
}

// protocol_is_audio_playing — TTS 재생 중 여부 (링 버퍼 OR 스피커 하드웨어)
bool protocol_is_audio_playing() {
  return audio_playing || M5.Speaker.isPlaying();
}

// protocol_has_audio_buffered — 링버퍼에 재생 가능한 오디오가 쌓였는지
bool protocol_has_audio_buffered() {
  return audio_ring_used() > 0;
}

// protocol_clear_audio_buffer — TTS 즉시 중단 (버튼 인터럽트용)
// 링 버퍼를 비우고 스피커 하드웨어도 정지
void protocol_clear_audio_buffer() {
  robot_bridge_set_speech_active(false);
  audio_ring_head = 0;
  audio_ring_tail = 0;
  audio_playing = false;
  capture_locked = false;
  capture_lock_waiting_for_playback = false;
  M5.Speaker.stop();
}

bool protocol_peer_is_alive() {
  if (last_peer_rx_ms == 0) return false;
  return (uint32_t)(millis() - last_peer_rx_ms) <= PROTOCOL_PEER_TIMEOUT_MS;
}

bool protocol_is_capture_locked() {
  return capture_locked;
}
