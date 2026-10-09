// ============================================================
// connection.cpp — WiFi/서버 연결 관리 구현
// ============================================================
// 역할: WiFi AP 연결 및 TCP 서버 연결을 관리.
//       끊김 감지 시 WIFI_RECONNECT_INTERVAL_MS 간격으로 재시도.
//
// 주요 설계 결정:
//   - WiFi.reconnect() 대신 WiFi.begin(ssid, pass) 사용
//     (일부 ESP32 Arduino 코어에서 reconnect() 불안정)
//   - server_connected를 client.connected()와 매 루프 동기화
//     (TCP 연결이 조용히 끊겨도 즉시 감지)
// ============================================================

#include "connection.h"
#include "config.h"
#include "led_control.h"
#include "protocol.h"
#include <M5Unified.h>
#include <string.h>
#include <sys/socket.h>
#include <errno.h>
#include <algorithm>

static void (*s_safety_callback)(bool)=nullptr;
void connection_set_safety_callback(void (*callback)(bool)){s_safety_callback=callback;}
void connection_service_safety(bool link_available){if(s_safety_callback)s_safety_callback(link_available);}
void connection_cooperative_wait(uint32_t duration_ms,bool link_available){
  const uint32_t started=millis();
  do {
    connection_service_safety(link_available);
    const uint32_t elapsed=static_cast<uint32_t>(millis()-started);
    if(elapsed>=duration_ms)return;
    delay(std::min<uint32_t>(5,duration_ms-elapsed));
  } while(true);
}
// Never call WiFiClient::write: its internal select/retry can stall for seconds.
// Controller status callbacks enqueue only, so pumping here cannot reenter a
// controller invocation through recursive network status transmission.
size_t connection_write(Stream& transport,const uint8_t* data,size_t length){
  if(!data||!length)return 0;
  const uint32_t started=millis();
  size_t sent=0;
  while(sent<length){
    connection_service_safety(true);
    if(static_cast<uint32_t>(millis()-started)>=20)break;
    if(connection_is_wired_mode()){
      const int available=Serial.availableForWrite();
      if(available>0){
        const size_t count=std::min<size_t>(length-sent,std::min<int>(available,64));
        const size_t written=transport.write(data+sent,count);
        if(!written)break;
        sent+=written;
      }else delay(1);
    }else{
      WiFiClient& socket=static_cast<WiFiClient&>(transport);
      if(!socket.connected()||socket.fd()<0)break;
      const int written=send(socket.fd(),data+sent,length-sent,MSG_DONTWAIT);
      if(written>0)sent+=static_cast<size_t>(written);
      else if(written<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))delay(1);
      else break;
    }
  }
  if(sent<length && (!connection_is_wired_mode() || sent==0)){
    connection_service_safety(false);
    if(!connection_is_wired_mode())static_cast<WiFiClient&>(transport).stop();
  }
  return sent;
}

// WiFi 자격증명 캐시 (재연결 시 WiFi.begin()에 전달)
static const char* s_ssid = nullptr;
static const char* s_pass = nullptr;

bool connection_is_wired_mode() {
  if (!CONNECTION_MODE) return true;
  if (strcmp(CONNECTION_MODE, "wired") == 0) return true;
  if (strcmp(CONNECTION_MODE, "auto") == 0) return !SSID || strlen(SSID) == 0;
  return false;
}

bool connection_debug_logging_enabled() {
  return !connection_is_wired_mode();
}

uint32_t connection_ping_interval_ms() {
  return connection_is_wired_mode() ? WIRED_PING_INTERVAL_MS : PING_INTERVAL_MS;
}

Stream& connection_stream(WiFiClient& client) {
  if (connection_is_wired_mode()) return Serial;
  return client;
}

// connection_init — WiFi STA 모드 설정 및 첫 연결 시도
void connection_init(ConnectionState* state, const char* ssid, const char* pass) {
  state->last_connect_attempt = 0;
  state->wifi_connected = false;
  state->server_connected = false;
  state->wired_mode = connection_is_wired_mode();
  s_ssid = ssid;
  s_pass = pass;

  if (state->wired_mode) {
    return;
  }

  WiFi.mode(WIFI_STA);          // Station 모드 (AP가 아닌 클라이언트)
  WiFi.begin(ssid, pass);       // 비동기 연결 시작
  led_show_connecting();
}

// connection_manage — 매 loop()에서 호출하여 연결 상태 관리
// 처리 순서: WiFi 확인 → WiFi 재연결 → 서버 확인 → 서버 재연결
void connection_manage(ConnectionState* state, WiFiClient& client) {
  if (connection_is_wired_mode()) {
    state->wired_mode = true;
    state->wifi_connected = true;
    state->server_connected = protocol_peer_is_alive();
    if (state->server_connected) {
      led_show_connected();
    } else {
      led_show_connecting();
    }
    return;
  }

  unsigned long now = millis();

  // ── 1단계: WiFi AP 연결 확인 ──
  if (WiFi.status() != WL_CONNECTED) {
    connection_service_safety(false);
    if (state->wifi_connected) {
      // WiFi가 끊김 → 서버도 끊긴 것으로 처리
      state->wifi_connected = false;
      state->server_connected = false;
    }
    // 재연결 간격 체크 후 WiFi.begin() 재시도
    if (now - state->last_connect_attempt > WIFI_RECONNECT_INTERVAL_MS) {
      WiFi.disconnect(true);     // 이전 연결 정리 (auto-reconnect 비활성화)
      connection_cooperative_wait(50, false);  // Button/watchdog stay live.
      WiFi.begin(s_ssid, s_pass);
      state->last_connect_attempt = now;
      led_show_connecting();
    }
    return;  // WiFi 미연결 시 서버 연결 시도하지 않음
  }

  // WiFi 연결 성공 감지
  if (!state->wifi_connected) {
    state->wifi_connected = true;
  }

  // ── 2단계: TCP 서버 연결 상태 동기화 ──
  // server_connected 플래그와 실제 소켓 상태를 매 루프 동기화
  // (TCP RST 없이 조용히 끊긴 경우 대응)
  if (state->server_connected && !client.connected()) {
    state->server_connected = false;
  }

  // ── 3단계: TCP 서버 재연결 ──
  if (!client.connected()) {
    state->server_connected = false;
    connection_service_safety(false);
    if (now - state->last_connect_attempt > WIFI_RECONNECT_INTERVAL_MS) {
      IPAddress numeric_server;
      // DNS is deliberately excluded from the safety-critical loop. The setup
      // contract names this setting SERVER_IP; use the PC's numeric LAN address.
      if (numeric_server.fromString(SERVER_IP) && client.connect(numeric_server, SERVER_PORT, 100)) {
        client.setNoDelay(true);   // Nagle 알고리즘 비활성화 (저지연)
        state->server_connected = true;
        protocol_init();           // 수신 상태머신 리셋 (잔여 데이터 무효화)
        M5.Speaker.stop();         // 이전 재생 중단
        led_show_connected();
      } else {
        led_show_connecting();
      }
      state->last_connect_attempt = now;
    }
  }
}

// connection_is_server_connected — 서버 연결 상태 조회
bool connection_is_server_connected(const ConnectionState* state) {
  return state->server_connected;
}

bool connection_transport_ready(const ConnectionState* state) {
  return state->wired_mode || state->server_connected;
}
