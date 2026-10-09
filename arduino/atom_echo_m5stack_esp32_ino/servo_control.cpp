#include "servo_control.h"
#include "config.h"
#include "protocol.h"
#include <CcoliRobotControl.h>
#include <M5Unified.h>
#include <Esp.h>

static Servo motors[2];
static bool attached[2]={false,false};
static char device_id[32];
static char boot_id[32];
static ccoli_robot::Controller* controller=nullptr;

static void motor_output(void*,uint8_t index,float angle,bool enable) {
  if(index>=2 || !LOCAL_SERVO_ENABLED)return;
  if(!enable) { if(attached[index])motors[index].detach(); attached[index]=false; return; }
  const int pin=index==0?SERVO_PIN_PITCH:SERVO_PIN_TILT;
  if(!attached[index]) { motors[index].setPeriodHertz(50);motors[index].attach(pin,500,2400);attached[index]=true; }
  motors[index].write(static_cast<int>(lroundf(angle)));
}
static void report_status(void*,const char* json) { protocol_send_robot_status(json); }
void servo_init() {
  snprintf(device_id,sizeof(device_id),"atom-%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
  snprintf(boot_id,sizeof(boot_id),"%08lx-%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
  const char* display=DISPLAY_TYPE==1?"ssd1306":DISPLAY_TYPE==2?"st7789v2_240x280":"none";
  static ccoli_robot::Controller instance(LOCAL_SERVO_ENABLED?2:0,device_id,boot_id,"legacy_direct",display,motor_output,report_status,nullptr);
  controller=&instance;
  // No attach/write at boot. Calibration and an explicit armed session are required.
}
bool servo_handle_control_json(const char* json,size_t length) {
  if(!controller)return false;
  if(M5.BtnA.isPressed()){controller->emergencyStop("physical_stop");return true;}
  controller->handle(json,length,millis());return true;
}
void servo_update(bool link_available) {
  if(!controller)return;
  if(M5.BtnA.isPressed() && controller->armed())controller->emergencyStop("physical_stop");
  else if(controller->armed() && (!link_available || !protocol_peer_is_alive()))controller->emergencyStop("peer_lost");
  controller->tick(millis());
}
bool servo_is_busy(){return controller&&controller->busy();}
void servo_stop(){if(controller)controller->emergencyStop("legacy_stop");}
// Older unscoped LLM packets are display-only. They cannot bypass the v1
// calibration/session/sequence/lease contract. Use ROBOT_CONTROL move/gesture.
void servo_set_angle(int servo_idx,int angle){(void)servo_idx;(void)angle;}
void servo_set_angle(int angle){servo_set_angle(0,angle);}
void servo_play_action(ServoAction action){(void)action;}
void servo_wiggle(){servo_play_action(ACTION_WIGGLE);}
void servo_rotate(){servo_play_action(ACTION_DANCE);}
