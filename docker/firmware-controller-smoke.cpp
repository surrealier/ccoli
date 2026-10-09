#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include <chrono>
#include <sys/select.h>
#include <unistd.h>
#include "CcoliRobotControl.h"
using namespace ccoli_robot;
struct Fake {
  struct Write { int servo; float angle; bool enable; };
  std::vector<Write> writes;
  std::vector<std::string> states;
  static void motor(void* ctx, uint8_t servo, float angle, bool enable) {
    static_cast<Fake*>(ctx)->writes.push_back({servo,angle,enable});
  }
  static void status(void* ctx, const char* json) { static_cast<Fake*>(ctx)->states.emplace_back(json); }
};
std::string frame(const char* op, unsigned seq, const std::string& fields="",const char* session="owner") {
 return std::string("{\"cmd\":\"ROBOT_CONTROL\",\"v\":1,\"op\":\"")+op+"\",\"command_id\":\"c"+std::to_string(seq)+"\",\"session_id\":\""+session+"\",\"boot_id\":\"boot\",\"seq\":"+std::to_string(seq)+",\"valid_for_ms\":2000,\"lease_ms\":2000"+fields+"}";
}
static void wire_status(void*,const char* json){std::cout<<json<<std::endl;}
static void wire_motor(void*,uint8_t,float,bool){}
static int wire_simulator() {
 Controller core(4,"companion-native","boot","companion_uart","st7789v2_240x280",wire_motor,wire_status,nullptr);
 const auto start=std::chrono::steady_clock::now();
 std::string line;bool dropping=false;
 while(true) {
   const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
   core.tick(static_cast<uint32_t>(elapsed));
   fd_set read_set;FD_ZERO(&read_set);FD_SET(STDIN_FILENO,&read_set);
   timeval timeout={0,5000};
   const int ready=select(STDIN_FILENO+1,&read_set,nullptr,nullptr,&timeout);
   if(ready<0)return 1;
   if(!ready)continue;
   char c;
   if(read(STDIN_FILENO,&c,1)<=0)return 0;
   if(c=='\n') {
     if(!dropping&&!line.empty())core.handle(line.data(),line.size(),static_cast<uint32_t>(elapsed));
     line.clear();dropping=false;
   } else if(c!='\r') {
     if(c==0||line.size()>=MAX_FRAME){dropping=true;line.clear();}
     if(!dropping)line.push_back(c);
   }
 }
}
int main(int argc,char** argv) {
 if(argc==2&&!strcmp(argv[1],"--wire"))return wire_simulator();
 Fake fake;
 Controller c(2,"atom","boot","legacy_direct","none",Fake::motor,Fake::status,&fake);
 assert(!c.armed() && fake.writes.empty());
 auto move=frame("move",1,",\"servo\":1,\"angle\":110,\"duration_ms\":1000");
 c.handle(move.c_str(),move.size(),0);
 assert(fake.writes.empty() && fake.states.back().find("session_mismatch")!=std::string::npos);
 auto discover=frame("discover",1);
 c.handle(discover.c_str(),discover.size(),0);
 assert(fake.states.back().find("\"capabilities\"")!=std::string::npos);
 fake.writes.clear();
 auto calibrate=frame("calibrate",2,",\"channels\":[{\"servo\":0,\"min_angle\":20,\"max_angle\":160,\"center_angle\":90,\"max_speed_dps\":45,\"inverted\":false},{\"servo\":1,\"min_angle\":20,\"max_angle\":160,\"center_angle\":90,\"max_speed_dps\":45,\"inverted\":true}]");
 c.handle(calibrate.c_str(),calibrate.size(),0);
 assert(c.calibrated() && fake.writes.empty());
 auto arm=frame("arm",3);
 c.handle(arm.c_str(),arm.size(),0);
 assert(c.armed() && fake.writes.empty()); // arming must not recenter/move.
 move=frame("move",4,",\"servo\":1,\"angle\":110,\"duration_ms\":1000");
 c.handle(move.c_str(),move.size(),0);
 c.tick(100);
 assert(!fake.writes.empty() && fake.writes.back().servo==1);
 assert(fake.writes.back().angle<90); // inverted physical direction.
 assert(c.angle(1)>90 && c.angle(0)==90);
 const size_t before=fake.writes.size();
 c.handle(move.c_str(),move.size(),100);
 assert(fake.writes.size()==before); // duplicate never actuates again.
 for(unsigned ms=150;ms<=1000;ms+=50)c.tick(ms);
 assert(!c.busy() && std::fabs(c.angle(1)-110)<0.01);
 assert(fake.states.back().find("\"status\":\"DONE\"")!=std::string::npos);
 auto too_fast=frame("move",5,",\"servo\":0,\"angle\":160,\"duration_ms\":1");
 c.handle(too_fast.c_str(),too_fast.size(),1000);
 assert(fake.states.back().find("speed_limit")!=std::string::npos && !c.busy());
 auto dup=frame("move",6,",\"servo\":0,\"angle\":100,\"angle\":101,\"duration_ms\":1000");
 const auto count=fake.writes.size();
 c.handle(dup.c_str(),dup.size(),1000);
 assert(fake.writes.size()==count && fake.states.back().find("invalid_json")!=std::string::npos);
 auto nonfinite=frame("move",6,",\"servo\":0,\"angle\":1e999,\"duration_ms\":1000");
 c.handle(nonfinite.c_str(),nonfinite.size(),1000);
 assert(fake.writes.size()==count);
 c.tick(2001);
 assert(!c.armed() && !c.busy());
 assert(fake.states.back().find("lease_expired")!=std::string::npos);
 assert(!fake.writes.back().enable);
 auto stale=frame("arm",3);
 c.handle(stale.c_str(),stale.size(),2002);
 assert(!c.armed());
 auto stop=frame("stop",99,",\"mode\":\"detach\"","other");
 c.handle(stop.c_str(),stop.size(),2003);
 assert(fake.states.back().find("STOPPED")!=std::string::npos && !c.armed());
 auto new_session=frame("discover",1,"","new");
 c.handle(new_session.c_str(),new_session.size(),2004);
 assert(!c.calibrated() && !c.armed());

 // All malformed fixtures are rejected without a new enabled output.
 const std::vector<std::string> malformed = {
   frame("move",2,",\"servo\":true,\"angle\":100,\"duration_ms\":1000","new"),
   frame("move",2,",\"servo\":0,\"angle\":100,\"duration_ms\":1.0","new"),
   frame("move",2,",\"servo\":0,\"angle\":100,\"duration_ms\":1000,\"extra\":1","new"),
   frame("arm",2,"","new")+"trailing",
   frame("arm",2,",\"v\":1","new"),
   std::string(2049,' '),
   std::string("{\"cmd\":\"ROBOT_CONTROL\",\"nested\":[[[[[[]]]]]]}"),
   std::string("{\"cmd\":\"ROBOT_CONTROL\",\"op\":\"arm\\q\"}")
 };
 for(const auto& bad:malformed) {
   const size_t previous=fake.writes.size();
   c.handle(bad.c_str(),bad.size(),2005);
   assert(fake.writes.size()==previous);
   assert(fake.states.back().find("\"status\":\"ERROR\"")!=std::string::npos);
 }
 auto one=frame("calibrate",2,",\"channels\":[{\"servo\":0,\"min_angle\":20,\"max_angle\":160,\"center_angle\":90,\"max_speed_dps\":45,\"inverted\":false}]","new");
 c.handle(one.c_str(),one.size(),2006);
 assert(c.calibrated());
 auto new_arm=frame("arm",3,"","new");c.handle(new_arm.c_str(),new_arm.size(),2006);
 auto disabled=frame("move",4,",\"servo\":1,\"angle\":100,\"duration_ms\":1000","new");
 c.handle(disabled.c_str(),disabled.size(),2006);
 assert(fake.states.back().find("channel_mismatch")!=std::string::npos);
 auto reused=frame("state",5,"","new");reused.replace(reused.find("c5"),2,"c3");
 c.handle(reused.c_str(),reused.size(),2006);
 assert(fake.states.back().find("command_id_reused")!=std::string::npos);
 auto gesture=frame("gesture",5,",\"id\":\"camera_scan\",\"intensity\":0.5","new");
 c.handle(gesture.c_str(),gesture.size(),2006);
 for(unsigned ms=2056;ms<=3606;ms+=50)c.tick(ms);
 assert(!c.busy());
 for(const auto& write:fake.writes)if(write.enable)assert(write.servo<2&&write.angle>=20&&write.angle<=160);
 auto after_stop=frame("stop",6,",\"mode\":\"hold\"","new");
 const size_t hold_writes=fake.writes.size();const float held=c.angle(0);
 c.handle(after_stop.c_str(),after_stop.size(),3607);
 assert(!c.armed()&&!c.calibrated()&&fake.writes.size()==hold_writes&&c.angle(0)==held);
 c.handle(new_arm.c_str(),new_arm.size(),3608);
 assert(!c.armed()&&fake.states.back().find("session_mismatch")!=std::string::npos);
 // Generic JSON display transport supports real multilingual speech but still
 // rejects malformed UTF8/escapes, while control IDs remain ASCII identifiers.
 Json display;
 const std::string translated="{\"action\":\"ROBOT_STATE\",\"speech\":{\"text\":\"안녕 中文 日本語\"}}";
 assert(display.parse(translated.data(),translated.size()));
 const std::string malformed_utf8="{\"x\":\""+std::string("\xc0\xaf",2)+"\"}";
 assert(!display.parse(malformed_utf8.data(),malformed_utf8.size()));
 unsigned rng=1234;
 for(int n=0;n<2000;n++) {
   std::string bytes;
   for(int k=0;k<n%256;k++){rng=rng*1664525u+1013904223u;bytes.push_back(static_cast<char>(rng>>24));}
   Json parser;(void)parser.parse(bytes.data(),bytes.size());
 }

 // uint32 wrap-safe watchdog.
 Fake wrap;
 Controller w(2,"atom","boot","legacy_direct","none",Fake::motor,Fake::status,&wrap);
 w.handle(discover.c_str(),discover.size(),0xfffffc00u);
 w.handle(calibrate.c_str(),calibrate.size(),0xfffffc00u);
 w.handle(arm.c_str(),arm.size(),0xfffffc00u);
 w.tick(1000);
 assert(!w.armed());
 std::cout << "firmware controller native smoke passed\n";
}
