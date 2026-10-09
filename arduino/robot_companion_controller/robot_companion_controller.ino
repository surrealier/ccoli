#include <Arduino.h>
#include <ESP32Servo.h>
#include <CcoliRobotControl.h>
#include <SPI.h>
#ifndef COMPANION_DISPLAY_ENABLED
#define COMPANION_DISPLAY_ENABLED 1
#endif
#if COMPANION_DISPLAY_ENABLED
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
static Adafruit_ST7789 lcd(&SPI,5,21,22);
#endif
// ESP32 DevKit companion pin map. Never use this map on an Atom Echo.
static constexpr int SERVO_PINS[]={13,14,25,26};
static constexpr int STOP_PIN=27; // external normally-open button to GND
static constexpr int LCD_BL_PIN=19;
static HardwareSerial BridgeSerial(1);
static Servo servos[4];
static bool attached[4]={false,false,false,false};
static char device_id[32],boot_id[32];
static ccoli_robot::Controller* controller=nullptr;
static char incoming[ccoli_robot::MAX_FRAME+1];
static size_t incoming_size=0;
static bool dropping=false,button_down=false;
static uint32_t partial_started=0;
static char face[24]="neutral";
static bool sleeping=false,talking=false;
static uint32_t talking_until=0,next_blink=0,blink_until=0,next_gaze=0,last_render=0;
static float gaze=0,target_gaze=0,eye_open=1,target_eye_open=1;

static void motor_output(void*,uint8_t channel,float angle,bool enable) {
  if(channel>=4)return;
  if(!enable) {if(attached[channel])servos[channel].detach();attached[channel]=false;return;}
  if(!attached[channel]){servos[channel].setPeriodHertz(50);servos[channel].attach(SERVO_PINS[channel],500,2400);attached[channel]=true;}
  servos[channel].write(static_cast<int>(lroundf(angle)));
}
static void status_output(void*,const char* json) {
  BridgeSerial.println(json);
  // Avoid duplicating status frames on USB: a blocked diagnostic consumer must not stall control.
}
static bool known_face(const char* value) {
  static const char* const faces[]={"neutral","happy","sad","angry","surprised","sleepy","love","curious","excited","confused","sulky"};
  for(size_t i=0;i<11;i++)if(!strcmp(value,faces[i]))return true;
  return false;
}
static void receive_line(uint32_t now) {
  incoming[incoming_size]=0;
  ccoli_robot::Json json;
  if(json.parse(incoming,incoming_size)&&(json.equal(json.field(0,"action"),"ROBOT_STATE")||json.equal(json.field(0,"action"),"ROBOT_DISPLAY"))) {
    // Legacy robot state is display-only; no model emotion can drive motors.
    char value[24];
    int f=json.field(0,"face");if(f<0)f=json.field(0,"emotion");
    if(json.string(f,value,sizeof(value))&&known_face(value))strcpy(face,value);
    if(json.string(json.field(0,"mode"),value,sizeof(value)))sleeping=!strcmp(value,"sleep")||!strcmp(value,"sleeping");
    const int speech=json.field(0,"speech");
    if(speech>=0&&json.t[speech].type==ccoli_robot::Json::OBJECT) {
      bool active=false;
      if(json.boolean(json.field(speech,"tts_active"),active)){talking=active;talking_until=now+30000;}
    }
    bool active=false;
    if(json.boolean(json.field(0,"tts_active"),active)){talking=active;talking_until=now+30000;}
    return;
  }
  if(digitalRead(STOP_PIN)==LOW){controller->emergencyStop("physical_stop");return;}
  controller->handle(incoming,incoming_size,now);
}
static void update_display(uint32_t now) {
#if COMPANION_DISPLAY_ENABLED
  if(static_cast<uint32_t>(now-last_render)<50)return;
  last_render=now;
  if(!next_blink)next_blink=now+random(3000,7001);
  if(!sleeping&&static_cast<int32_t>(now-next_blink)>=0){blink_until=now+160;next_blink=now+random(3000,7001);}
  if(!next_gaze||static_cast<int32_t>(now-next_gaze)>=0){target_gaze=random(-12,13);next_gaze=now+random(5000,12001);}
  target_eye_open=sleeping?0.08f:!strcmp(face,"sleepy")?0.4f:0.95f;
  if(static_cast<int32_t>(blink_until-now)>0)target_eye_open=0.08f;
  eye_open+=(target_eye_open-eye_open)*0.25f;gaze+=(target_gaze-gaze)*0.25f;
  if(talking&&static_cast<int32_t>(now-talking_until)>=0)talking=false;
  const uint16_t bg=0x0823,fg=0x77D6;
  // Clear only the animated face area; hardware SPI keeps the control loop free.
  lcd.fillRect(35,70,170,150,bg);
  const int h=static_cast<int>(34*eye_open)+2;
  lcd.fillRoundRect(60+static_cast<int>(gaze),100-h/2,35,h,8,fg);
  lcd.fillRoundRect(145+static_cast<int>(gaze),100-h/2,35,h,8,fg);
  if(!strcmp(face,"angry")||!strcmp(face,"sulky")) {
    lcd.drawLine(57,72,98,85,fg);lcd.drawLine(142,85,183,72,fg);
  }
  if(!strcmp(face,"sad")){lcd.drawLine(57,85,98,72,fg);lcd.drawLine(142,72,183,85,fg);}
  if(talking)lcd.fillRoundRect(103,155,34,8+static_cast<int>((now/100)%3)*7,7,fg);
  else if(!sleeping && !strcmp(face,"sleepy") && (now/5000)%4==0)lcd.drawCircle(120,170,14,fg);
  else if(!strcmp(face,"happy")||!strcmp(face,"love")||!strcmp(face,"excited"))lcd.drawRoundRect(104,160,32,14,7,fg);
  else lcd.drawFastHLine(107,170,26,fg);
  lcd.fillRect(0,248,240,32,bg);
  lcd.setCursor(12,255);lcd.setTextSize(1);lcd.setTextColor(fg,bg);
  lcd.print(controller->armed()?"ARMED - button stops":"DISARMED");lcd.print(sleeping?" / sleep":"");
#else
  (void)now;
#endif
}
void setup() {
  Serial.begin(115200);
  BridgeSerial.begin(115200,SERIAL_8N1,16,17);
  pinMode(STOP_PIN,INPUT_PULLUP);
  snprintf(device_id,sizeof(device_id),"companion-%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
  snprintf(boot_id,sizeof(boot_id),"%08lx-%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
  const char* display=COMPANION_DISPLAY_ENABLED?"st7789v2_240x280":"none";
  static ccoli_robot::Controller instance(4,device_id,boot_id,"companion_uart",display,motor_output,status_output,nullptr);
  controller=&instance;
#if COMPANION_DISPLAY_ENABLED
  SPI.begin(18,-1,23,5);
  lcd.init(240,280);lcd.setRotation(0);lcd.fillScreen(0x0823);
  pinMode(LCD_BL_PIN,OUTPUT);digitalWrite(LCD_BL_PIN,HIGH);
#endif
  // Servo power may be present, but no PWM is attached at boot.
}
void loop() {
  const uint32_t now=millis();
  const bool pressed=digitalRead(STOP_PIN)==LOW;
  if(pressed&&!button_down)controller->emergencyStop("physical_stop");
  button_down=pressed;
  controller->tick(now);
  // Partial frames expire and an overflow discards through newline. Neither can
  // block the watchdog, button, audio bridge, or start a malformed command.
  if(incoming_size && static_cast<uint32_t>(now-partial_started)>250){incoming_size=0;dropping=true;}
  size_t budget=256;
  while(budget--&&BridgeSerial.available()>0) {
    const char c=static_cast<char>(BridgeSerial.read());
    if(c=='\r')continue;
    if(c=='\n') {
      if(!dropping&&incoming_size)receive_line(now);
      incoming_size=0;dropping=false;continue;
    }
    if(!incoming_size)partial_started=now;
    if(c==0||incoming_size>=ccoli_robot::MAX_FRAME){dropping=true;incoming_size=0;}
    if(!dropping)incoming[incoming_size++]=c;
  }
  controller->tick(millis()); // account for display/SPI time too.
  update_display(millis());
  delay(1);
}
