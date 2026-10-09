#include "robot_bridge.h"
#include "config.h"
#include "protocol.h"
#include <CcoliRobotControl.h>
#include <M5Unified.h>
#include <string.h>
#if ROBOT_BRIDGE_ENABLED
#include <HardwareSerial.h>
static HardwareSerial bridge(ROBOT_BRIDGE_UART_PORT);
static bool started=false,peer_known=false,dropping=false;
static uint32_t last_peer_ms=0;
static char line[ccoli_robot::MAX_FRAME+1];
static size_t position=0;
static void forward_stop() {
  const char* stop="{\"cmd\":\"ROBOT_CONTROL\",\"v\":1,\"op\":\"stop\",\"command_id\":\"atom-local-stop\",\"session_id\":\"local-stop\",\"boot_id\":\"\",\"seq\":1,\"valid_for_ms\":2000,\"lease_ms\":2000,\"mode\":\"detach\"}";
  bridge.println(stop);
}
void robot_bridge_init() {
  bridge.begin(ROBOT_BRIDGE_BAUD,SERIAL_8N1,ROBOT_BRIDGE_RX_PIN,ROBOT_BRIDGE_TX_PIN);
  started=true;peer_known=false;position=0;dropping=false;
}
bool robot_bridge_ready(){return started&&peer_known&&static_cast<uint32_t>(millis()-last_peer_ms)<3000;}
bool robot_bridge_enabled(){return started;}
bool robot_bridge_forward_json(const char* json) {
  if(!started||!json)return false;
  if(M5.BtnA.isPressed()){forward_stop();return false;}
  const size_t len=strlen(json);
  if(!len||len>ccoli_robot::MAX_FRAME||strchr(json,'\n')||strchr(json,'\r'))return false;
  return bridge.write(reinterpret_cast<const uint8_t*>(json),len)==len && bridge.write('\n')==1;
}
void robot_bridge_set_speech_active(bool active) {
  robot_bridge_forward_json(active?"{\"action\":\"ROBOT_DISPLAY\",\"tts_active\":true}":"{\"action\":\"ROBOT_DISPLAY\",\"tts_active\":false}");
}
void robot_bridge_update(bool link_available) {
  if(!started)return;
  if(M5.BtnA.wasPressed())forward_stop();
  if(peer_known&&(!link_available||!protocol_peer_is_alive())){forward_stop();peer_known=false;}
  // Bounded per-loop receive work preserves audio and local stop scheduling.
  size_t budget=256;
  while(budget--&&bridge.available()>0) {
    const char c=static_cast<char>(bridge.read());
    if(c=='\r')continue;
    if(c=='\n') {
      if(!dropping&&position) {
        line[position]=0;ccoli_robot::Json json;
        if(json.parse(line,position)&&json.equal(json.field(0,"v"),"1")) {
          const int status=json.field(0,"status");
          if(json.equal(status,"ACK")||json.equal(status,"RUNNING")||json.equal(status,"DONE")||json.equal(status,"ERROR")||json.equal(status,"STOPPED")) {
            last_peer_ms=millis();peer_known=true;protocol_send_robot_status(line);
          }
        }
      }
      position=0;dropping=false;continue;
    }
    if(c==0||position>=ccoli_robot::MAX_FRAME){dropping=true;position=0;}
    if(!dropping)line[position++]=c;
  }
}
#else
void robot_bridge_init(){}
void robot_bridge_update(bool){}
bool robot_bridge_ready(){return false;}
bool robot_bridge_enabled(){return false;}
bool robot_bridge_forward_json(const char*){return false;}
void robot_bridge_set_speech_active(bool){}
#endif
