// ============================================================
// protocol.h — 패킷 프로토콜 인터페이스
// ============================================================
// 역할: ESP32 ↔ PC 서버 간 바이너리 패킷 프로토콜 정의.
//       모든 패킷은 [1B 타입][2B 길이 LE][NB 페이로드] 구조.
//
// 패킷 방향:
//   ESP32 → PC:  START(0x01), AUDIO(0x02), END(0x03), PING(0x10)
//   PC → ESP32:  CMD(0x11), AUDIO_OUT(0x12), PONG(0x1F)
// ============================================================

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <Arduino.h>
#include <stdint.h>

// ── 패킷 타입 상수 ──
// ESP32 → Server
static constexpr uint8_t PTYPE_START = 0x01;  // 음성 녹음 시작 신호
static constexpr uint8_t PTYPE_AUDIO = 0x02;  // Wi-Fi: PCM16LE/16kHz, wired: mu-law/8kHz
static constexpr uint8_t PTYPE_END   = 0x03;  // 음성 녹음 종료 신호
static constexpr uint8_t PTYPE_PING  = 0x10;  // Keepalive 핑

// Server → ESP32
static constexpr uint8_t PTYPE_CMD       = 0x11;  // JSON 명령 (서보/감정/액션)
static constexpr uint8_t PTYPE_AUDIO_OUT = 0x12;  // Wi-Fi: PCM16LE/16kHz, wired: mu-law/8kHz TTS
static constexpr uint8_t PTYPE_PONG      = 0x1F;  // 핑 응답 (선택적)

// 양방향 (예약)
static constexpr uint8_t PTYPE_ROBOT_STATUS = 0x14;
static constexpr uint8_t PTYPE_BUFFER_STATUS = 0x13;  // 버퍼 상태 보고 (미구현)

// ── 공개 API ──
bool protocol_send_robot_status(const char* json);
void protocol_flush_robot_status();
void protocol_init();                          // 수신 상태머신 초기화
bool protocol_send_packet(Stream& transport,   // 패킷 송신 (헤더+페이로드)
                          uint8_t type,
                          const uint8_t* payload,
                          uint16_t len);
void protocol_poll(Stream& transport);         // 수신 패킷 폴링 및 디스패치
void protocol_send_ping_if_needed(Stream& transport, uint32_t interval_ms);  // 주기적 PING 전송
void protocol_audio_process();                 // 링 버퍼 → 스피커 재생 처리
bool protocol_is_audio_playing();              // TTS 재생 중 여부
void protocol_clear_audio_buffer();            // TTS 버퍼 즉시 비우기 (인터럽트)

bool protocol_has_audio_buffered();            // 링버퍼에 재생 가능한 오디오가 쌓였는지
bool protocol_peer_is_alive();                 // 마지막 수신 기준 peer 생존 여부
bool protocol_is_capture_locked();             // 서버가 마이크 입력을 잠근 상태인지
#endif
