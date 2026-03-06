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
#include "config.h"
#include "led_control.h"
#include "servo_control.h"
#include "display_control.h"
#include <M5Unified.h>
#include <ctype.h>
#include <string.h>
#include <stdlib.h>

// ── 버퍼 크기 상수 ──
static constexpr size_t RX_MAX_PAYLOAD = 2048;  // CMD 등 일반 패킷 최대 크기

#ifndef AUDIO_RING_BUFFER_SIZE
#define AUDIO_RING_BUFFER_SIZE 32768
#endif
static constexpr size_t AUDIO_PLAY_BUFFER_SIZE = AUDIO_RING_BUFFER_SIZE;

#ifndef RX_AUDIO_MAX_ALLOC
#define RX_AUDIO_MAX_ALLOC 16384  // 대형 오디오 패킷 동적 할당 상한
#endif

// ── 수신 상태머신 ──
// 패킷 구조: [1B type][2B length LE][length B payload]
// 상태: TYPE → LEN0 → LEN1 → PAYLOAD → (핸들러 호출) → TYPE
enum RxStage { RX_TYPE, RX_LEN0, RX_LEN1, RX_PAYLOAD };
static RxStage rx_stage = RX_TYPE;
static uint8_t rx_type = 0;       // 현재 수신 중인 패킷 타입
static uint16_t rx_len = 0;       // 현재 패킷의 페이로드 길이
static uint16_t rx_pos = 0;       // 현재까지 수신한 페이로드 바이트 수
static uint8_t rx_buf[RX_MAX_PAYLOAD];  // 일반 패킷 수신 버퍼 (정적)

// 대형 오디오 패킷용 동적 버퍼 (RX_MAX_PAYLOAD 초과 시 사용)
static uint8_t* rx_audio_buf = nullptr;
static size_t rx_audio_buf_size = 0;

// ── TTS 오디오 링 버퍼 ──
// 서버에서 스트리밍되는 TTS PCM 데이터를 저장하고
// 비블로킹으로 스피커에 공급하는 원형 버퍼
static uint8_t* audio_ring_buffer = nullptr;  // 첫 AUDIO_OUT 수신 시 malloc
static size_t audio_ring_head = 0;   // 쓰기 위치
static size_t audio_ring_tail = 0;   // 읽기 위치
static size_t audio_ring_size = AUDIO_PLAY_BUFFER_SIZE;
static bool audio_playing = false;

// PING 타이밍
static uint32_t last_ping_ms = 0;

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
  // PCM16 샘플 경계 유지: tail이 홀수 바이트면 1바이트 버려 정렬 복구
  if (audio_ring_tail & 0x01) {
    audio_ring_tail = (audio_ring_tail + 1) % audio_ring_size;
  }

  if (audio_ring_available() < len) {
    // 오버플로 방지: 오래된 데이터 드롭
    size_t to_drop = len - audio_ring_available() + 1024;
    // 샘플 경계(2바이트) 보존
    to_drop = (to_drop + 1) & ~((size_t)1);
    size_t used = audio_ring_used();
    used &= ~((size_t)1);
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
// 서버에서 스트리밍되는 TTS PCM 데이터를 링 버퍼에 저장.
// 1KB 이상 축적되면 재생 시작 (짧은 응답 지연 최소화)
static void handleAudioOut(const uint8_t* payload, uint16_t len) {
  // 16-bit PCM alignment (1 sample = 2 bytes)
  if (len & 0x01) len -= 1;
  if (len < 2) return;  // 최소 1샘플(2B) 필요

  // 링 버퍼 최초 할당 (lazy initialization, 메모리 절약)
  if (audio_ring_buffer == nullptr) {
    audio_ring_buffer = (uint8_t*)malloc(audio_ring_size);
    if (!audio_ring_buffer) {
      Serial.println("[AUDIO_OUT] Ring buffer alloc failed!");
      return;
    }
    audio_ring_head = 0;
    audio_ring_tail = 0;
  }

  if (!audio_ring_push(payload, len)) return;

  // 충분한 데이터가 모이면 재생 시작 (1KB = ~32ms @16kHz)
  if (!audio_playing && audio_ring_used() >= 4096) {
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

  // ── ROBOT_EMOTION: display face + servo action + LED ──
  if (has_action && strcmp(action, "ROBOT_EMOTION") == 0) {
    char face[32] = {0};
    char display_text[32] = {0};
    json_get_string(json, "face", face, sizeof(face));
    json_get_string(json, "servo_action", servo_action, sizeof(servo_action));
    json_get_string(json, "display_text", display_text, sizeof(display_text));
    
    display_show_face(face_from_string(face));
    if (display_text[0]) display_set_status_text(display_text);
    
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
    servo_set_angle(angle);  // clamp_angle()이 내부에서 0-180 범위 보장
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
}

// protocol_send_packet — 패킷 1개 송신
// 헤더(3B)를 단일 write로 전송, 페이로드는 재시도 루프로 완전 전송 보장.
// 전송 실패(write 반환 0) 시 연결 종료.
bool protocol_send_packet(WiFiClient& client, uint8_t type, const uint8_t* payload, uint16_t len) {
  if (!client.connected()) return false;

  // 헤더: [type 1B][length_lo 1B][length_hi 1B]
  uint8_t hdr[3] = { type, (uint8_t)(len & 0xFF), (uint8_t)((len >> 8) & 0xFF) };
  size_t written = client.write(hdr, 3);
  if (written != 3) { client.stop(); return false; }

  // 페이로드: partial write 대응 재시도 루프
  if (len && payload) {
    const uint8_t* p = payload;
    uint16_t remaining = len;
    while (remaining > 0) {
      size_t w = client.write(p, remaining);
      if (w == 0) { client.stop(); return false; }  // 전송 불가 → 연결 종료
      p += w;
      remaining -= w;
    }
  }
  return true;
}

// protocol_poll — 서버에서 수신된 패킷을 폴링하여 핸들러에 디스패치
// 상태머신: RX_TYPE → RX_LEN0 → RX_LEN1 → RX_PAYLOAD → 핸들러 → RX_TYPE
// 페이로드 단계에서는 벌크 읽기(client.read(buf, n))로 성능 최적화
void protocol_poll(WiFiClient& client) {
  if (!client.connected()) return;

  while (client.available() > 0) {
    // ── 벌크 읽기: 대형 오디오 패킷 (AUDIO_OUT, >2KB) ──
    if (rx_stage == RX_PAYLOAD && rx_type == PTYPE_AUDIO_OUT && rx_len > RX_MAX_PAYLOAD) {
      if (rx_audio_buf && rx_pos < rx_len) {
        size_t want = rx_len - rx_pos;
        int avail = client.available();
        if ((size_t)avail < want) want = avail;
        int got = client.read(rx_audio_buf + rx_pos, want);
        if (got <= 0) break;
        rx_pos += got;
        if (rx_pos >= rx_len) {
          handleAudioOut(rx_audio_buf, rx_len);
          rx_stage = RX_TYPE;
        }
        continue;
      }
    }

    // ── 벌크 읽기: 일반 패킷 (CMD 등, ≤2KB) ──
    if (rx_stage == RX_PAYLOAD && rx_type != PTYPE_AUDIO_OUT) {
      size_t want = rx_len - rx_pos;
      if (want > RX_MAX_PAYLOAD - rx_pos) want = RX_MAX_PAYLOAD - rx_pos;
      int avail = client.available();
      if ((size_t)avail < want) want = avail;
      if (want > 0) {
        int got = client.read(rx_buf + rx_pos, want);
        if (got <= 0) break;
        rx_pos += got;
        if (rx_pos >= rx_len) {
          if (rx_type == PTYPE_CMD) handleCmdJson(rx_buf, rx_len);
          rx_stage = RX_TYPE;
        }
        continue;
      }
    }

    // ── 헤더 바이트 읽기 (1바이트씩, 3B만) ──
    int b = client.read();
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
          rx_stage = RX_TYPE;
        } else {
          rx_stage = RX_PAYLOAD;
          // 대형 오디오 패킷: 동적 버퍼 할당 (상한 RX_AUDIO_MAX_ALLOC)
          if (rx_type == PTYPE_AUDIO_OUT && rx_len > RX_MAX_PAYLOAD) {
            size_t alloc_sz = (rx_len > RX_AUDIO_MAX_ALLOC) ? RX_AUDIO_MAX_ALLOC : rx_len;
            if (!rx_audio_buf || rx_audio_buf_size < alloc_sz) {
              if (rx_audio_buf) free(rx_audio_buf);
              rx_audio_buf = (uint8_t*)malloc(alloc_sz);
              rx_audio_buf_size = rx_audio_buf ? alloc_sz : 0;
            }
            if (!rx_audio_buf) {
              rx_stage = RX_TYPE;  // 할당 실패 → 패킷 스킵
            }
          }
        }
        break;

      case RX_PAYLOAD:
        // 단일 바이트 fallthrough (벌크 읽기에서 처리 안 된 잔여)
        if (rx_type == PTYPE_AUDIO_OUT && rx_len > RX_MAX_PAYLOAD) {
          if (rx_audio_buf && rx_pos < rx_audio_buf_size) {
            rx_audio_buf[rx_pos] = byte;
          }
        } else {
          if (rx_pos < RX_MAX_PAYLOAD) rx_buf[rx_pos] = byte;
        }
        rx_pos++;
        if (rx_pos >= rx_len) {
          // 페이로드 수신 완료 → 핸들러 디스패치
          if (rx_type == PTYPE_CMD) handleCmdJson(rx_buf, rx_len);
          else if (rx_type == PTYPE_AUDIO_OUT) {
            if (rx_len > RX_MAX_PAYLOAD) handleAudioOut(rx_audio_buf, rx_len);
            else handleAudioOut(rx_buf, rx_len);
          }
          rx_stage = RX_TYPE;
        }
        break;
    }
  }
}

// protocol_send_ping_if_needed — PING_INTERVAL_MS마다 keepalive 전송
// millis() 래핑(49.7일)에 안전한 unsigned 뺄셈 사용
void protocol_send_ping_if_needed(WiFiClient& client) {
  uint32_t now = millis();
  if (now - last_ping_ms >= PING_INTERVAL_MS) {
    if (protocol_send_packet(client, PTYPE_PING, nullptr, 0))
      last_ping_ms = now;
  }
}

// protocol_audio_process — 링 버퍼에서 스피커로 오디오 공급
// 스피커가 idle일 때만 다음 청크를 넘겨 중복 재생/노이즈를 방지한다.
// playRaw() 실패(큐 가득 참) 시 읽은 데이터를 롤백하여 다음 사이클에 재시도한다.
void protocol_audio_process() {
  if (!audio_playing) return;

  size_t used_now = audio_ring_used();
  // 샘플 경계가 틀어진 상태면 1바이트 버려 복구
  if (used_now & 0x01) {
    audio_ring_tail = (audio_ring_tail + 1) % audio_ring_size;
    used_now -= 1;
  }

  if (!M5.Speaker.isPlaying() && used_now >= 2) {
    static uint8_t play_buffer[2048];
    static uint32_t last_playraw_fail_ms = 0;
    size_t chunk_size = audio_ring_pop(play_buffer, sizeof(play_buffer));
    chunk_size = (chunk_size / 2) * 2;
    if (chunk_size >= 2) {
      bool queued = M5.Speaker.playRaw((const int16_t*)play_buffer, chunk_size / 2, 16000, false, 1, 0);
      if (!queued) {
        // 큐 가득 참 → 데이터 되돌리고 다음 사이클에 재시도
        audio_ring_tail = (audio_ring_tail + audio_ring_size - chunk_size) % audio_ring_size;
        uint32_t now = millis();
        if (now - last_playraw_fail_ms >= 500) {
          Serial.println("[AUDIO_PROC] playRaw queue full; retry next cycle");
          last_playraw_fail_ms = now;
        }
      }
    }
  }

  // 버퍼 소진 + 재생 완료 → 재생 종료
  if (audio_ring_used() == 0 && !M5.Speaker.isPlaying()) {
    audio_playing = false;
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
  if (audio_ring_buffer) {
    audio_ring_head = 0;
    audio_ring_tail = 0;
    audio_playing = false;
    M5.Speaker.stop();
  }
}
