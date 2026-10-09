"""Contracts shared by Python transport and the compiled MCU controller.
Behavioral MCU tests live in docker/firmware-controller-smoke.cpp and run in the
firmware-build service with ASAN/UBSAN, not as local Python tests.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import protocol

ROOT = Path(__file__).resolve().parents[2]
ATOM = ROOT / "arduino" / "atom_echo_m5stack_esp32_ino"
LIBRARY = ROOT / "arduino" / "libraries" / "CcoliRobotControl" / "src" / "CcoliRobotControl.h"


def test_robot_status_packet_matches_python_transport() -> None:
    header = (ATOM / "protocol.h").read_text(encoding="utf-8")
    match = re.search(r"PTYPE_ROBOT_STATUS\s*=\s*(0x[0-9a-fA-F]+)", header)
    assert match is not None
    assert int(match.group(1), 16) == protocol.PTYPE_ROBOT_STATUS


def test_robot_frame_bound_matches_existing_audio_transport() -> None:
    header = LIBRARY.read_text(encoding="utf-8")
    match = re.search(r"MAX_FRAME\s*=\s*(\d+)", header)
    assert match is not None
    assert int(match.group(1)) == protocol.DEVICE_MAX_PACKET_PAYLOAD


def test_companion_pin_profile_has_no_overlap() -> None:
    sketch = (ROOT / "arduino" / "robot_companion_controller" / "robot_companion_controller.ino").read_text(encoding="utf-8")
    match = re.search(r"SERVO_PINS\[\]\s*=\s*\{([^}]+)\}", sketch)
    assert match is not None
    servos = [int(item.strip()) for item in match.group(1).split(",")]
    # Companion DevKit wiring: UART16/17, SPI18/23/5/DC21/RST22/BL19, stop27.
    uart_display_stop = {16, 17, 18, 23, 5, 21, 22, 19, 27}
    assert len(servos) == len(set(servos)) == 4
    assert not set(servos) & uart_display_stop
    # ESP32 input-only pins cannot emit PWM.
    assert not set(servos) & {34, 35, 36, 39}


def test_both_sketches_use_the_same_controller_contract() -> None:
    atom = (ATOM / "servo_control.cpp").read_text(encoding="utf-8")
    companion = (ROOT / "arduino" / "robot_companion_controller" / "robot_companion_controller.ino").read_text(encoding="utf-8")
    for source in (atom, companion):
        assert "#include <CcoliRobotControl.h>" in source
        assert "ccoli_robot::Controller" in source


def test_atom_loop_services_safety_before_disconnected_returns() -> None:
    sketch = (ATOM / "atom_echo_m5stack_esp32_ino.ino").read_text(encoding="utf-8")
    loop = sketch.split("void loop() {", 1)[1]
    assert loop.index("connection_service_safety(") < loop.index("connection_manage(")
    assert "connection_cooperative_wait(" in loop
    assert "connection_set_safety_callback(service_device_safety)" in sketch


def test_connection_loss_and_retries_service_actual_native_controller(tmp_path: Path) -> None:
    import subprocess

    (tmp_path / "Arduino.h").write_text("""
#pragma once
#include <cstdint>
#include <cstddef>
class Stream { public: virtual ~Stream(){}; virtual size_t write(const uint8_t*,size_t count){return count;} };
class SerialClass : public Stream { public: int availableForWrite(){return 64;} };
extern SerialClass Serial;
unsigned long millis();
void delay(unsigned long);
class IPAddress { public: bool fromString(const char* value); };
""", encoding="utf-8")
    (tmp_path / "WiFi.h").write_text("""
#pragma once
#include "Arduino.h"
constexpr int WIFI_STA=1, WL_CONNECTED=3;
class WiFiClass { public:
 int current=WL_CONNECTED; void mode(int){}; void begin(const char*,const char*);
 void disconnect(bool); int status(){return current;}
};
extern WiFiClass WiFi;
class WiFiClient : public Stream { public:
 bool online=false; bool connected(){return online;}
 bool connect(IPAddress, uint16_t, int32_t timeout);
 bool connect(const char*,uint16_t);
 void setNoDelay(bool){}; int descriptor=-1; int fd(){return descriptor;} void stop(){online=false;};
};
""", encoding="utf-8")
    (tmp_path / "M5Unified.h").write_text("""
#pragma once
struct SpeakerClass { void stop(){}; };
struct M5Class { SpeakerClass Speaker; };
extern M5Class M5;
""", encoding="utf-8")
    harness = tmp_path / "main.cpp"
    harness.write_text(r'''
#include "connection.h"
#include "config.h"
#include <CcoliRobotControl.h>
#include <M5Unified.h>
#include <cassert>
#include <cstring>
#include <sys/socket.h>
#include <unistd.h>
SerialClass Serial; WiFiClass WiFi; M5Class M5;
const char* CONNECTION_MODE="wifi"; const char* SSID="test-network";
const char* PASS="test-not-a-real-secret"; const char* SERVER_IP="192.0.2.1";
extern const uint16_t SERVER_PORT=5001;
static unsigned long clock_ms=6000;
static int pump_count=0, detach_count=0, bounded_connects=0;
static bool pwm=false, retry_started=false;
static ccoli_robot::Controller* control=nullptr;
unsigned long millis(){return clock_ms;}
void delay(unsigned long ms){assert(ms<=5);clock_ms+=ms;}
bool IPAddress::fromString(const char* value){return !strcmp(value,"192.0.2.1");}
void WiFiClass::disconnect(bool){assert(!pwm);retry_started=true;}
void WiFiClass::begin(const char*,const char*){assert(!pwm);}
bool WiFiClient::connect(IPAddress,uint16_t,int32_t timeout){
 assert(!pwm);assert(timeout==100);++bounded_connects;clock_ms+=timeout;return false;
}
bool WiFiClient::connect(const char*,uint16_t){assert(false && "unbounded DNS connect");return false;}
void led_show_connected(){};void led_show_connecting(){};
bool protocol_peer_is_alive(){return true;}void protocol_init(){};
void output(void*,uint8_t,float,bool attached){pwm=attached;if(!attached)++detach_count;}
void report(void*,const char*){}
void pump(bool available){++pump_count;if(!available&&control->armed())control->emergencyStop("peer_lost");control->tick(millis());}
void command(const char* op,int seq,const char* extra=""){
 char json[1500];snprintf(json,sizeof(json),"{\"cmd\":\"ROBOT_CONTROL\",\"v\":1,\"op\":\"%s\",\"command_id\":\"command%d\",\"session_id\":\"session\",\"boot_id\":\"boot\",\"seq\":%d,\"valid_for_ms\":2000,\"lease_ms\":2000%s}",op,seq,seq,extra);control->handle(json,strlen(json),millis());
}
void arm_and_move(){
 command("discover",1);
 command("calibrate",2,",\"channels\":[{\"servo\":0,\"min_angle\":60,\"center_angle\":90,\"max_angle\":120,\"max_speed_dps\":90,\"inverted\":false}]");
 command("arm",3);command("move",4,",\"servo\":0,\"angle\":100,\"duration_ms\":1000");
 clock_ms+=20;control->tick(millis());assert(pwm&&control->armed());
}
int main(){
 ccoli_robot::Controller instance(1,"device","boot","legacy_direct","none",output,report,nullptr);control=&instance;
 connection_set_safety_callback(pump);
 ConnectionState state{};WiFiClient client;connection_init(&state,SSID,PASS);
 state.wifi_connected=true;state.server_connected=true;
 arm_and_move();connection_manage(&state,client);
 assert(!pwm&&!control->armed()&&detach_count>0&&bounded_connects==1);
 clock_ms+=6000;state.last_connect_attempt=0;WiFi.current=0;arm_and_move();
 int before=pump_count;connection_manage(&state,client);
 assert(retry_started&&!pwm&&pump_count-before>=11);
 before=pump_count;connection_cooperative_wait(100,false);assert(pump_count-before>=20);
 // Fill an actual native socket send buffer. The production writer must pump
 // safety and stop within its 20ms budget rather than call WiFiClient::write.
 int descriptors[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,descriptors)==0);
 client.descriptor=descriptors[0];client.online=true;WiFi.current=WL_CONNECTED;
 char fill[4096]={0};while(send(descriptors[0],fill,sizeof(fill),MSG_DONTWAIT)>0){}
 clock_ms+=6000;arm_and_move();before=pump_count;
 uint8_t bytes[3]={1,2,3};assert(connection_write(client,bytes,sizeof(bytes))==0);
 assert(!pwm&&!control->armed()&&!client.online&&pump_count-before>=20);
 close(descriptors[0]);close(descriptors[1]);
 CONNECTION_MODE="wired";client.online=false;connection_service_safety(false);assert(!pwm);
 uint8_t audio[640]={0};assert(connection_write(Serial,audio,sizeof(audio))>0);
}
''', encoding="utf-8")
    executable = tmp_path / "safety-smoke"
    subprocess.run([
        "g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
        f"-I{tmp_path}", f"-I{ATOM}", f"-I{LIBRARY.parent}",
        str(ATOM / "connection.cpp"), str(harness), "-o", str(executable),
    ], check=True, capture_output=False, text=True)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)