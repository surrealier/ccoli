// ============================================================
// connection.h — WiFi/서버 연결 관리 인터페이스
// ============================================================
// 역할: WiFi STA 모드 연결 및 TCP 서버 연결의 상태 추적.
//       연결 끊김 시 자동 재연결 로직 제공.
//
// 상태 머신:
//   WiFi 미연결 → WiFi 연결 → 서버 미연결 → 서버 연결(정상)
//   어느 단계에서든 끊기면 해당 단계부터 재시도
// ============================================================

#ifndef CONNECTION_H
#define CONNECTION_H

#include <Arduino.h>
#include <WiFi.h>

// 연결 상태 구조체
struct ConnectionState {
  unsigned long last_connect_attempt;  // 마지막 연결 시도 시각 (millis)
  bool wifi_connected;                 // WiFi AP 연결 여부
  bool server_connected;               // TCP 서버 연결 여부
  bool wired_mode;                     // USB serial wired 모드 여부
};

// 초기화: WiFi STA 모드 설정 및 첫 연결 시도
void connection_init(ConnectionState* state, const char* ssid, const char* pass);

// Single-loop-owner safety callback. A false link immediately invalidates motion.
void connection_set_safety_callback(void (*callback)(bool link_available));
void connection_service_safety(bool link_available);
void connection_cooperative_wait(uint32_t duration_ms, bool link_available);
size_t connection_write(Stream& transport, const uint8_t* data, size_t length);

// 매 loop()에서 호출: WiFi/서버 상태 확인 및 재연결
void connection_manage(ConnectionState* state, WiFiClient& client);

// 서버 연결 상태 조회
bool connection_is_server_connected(const ConnectionState* state);
bool connection_transport_ready(const ConnectionState* state);
bool connection_is_wired_mode();
bool connection_debug_logging_enabled();
uint32_t connection_ping_interval_ms();
Stream& connection_stream(WiFiClient& client);

#endif
