#pragma once
// Shared by both ESP32 firmwares and the Docker native harness. No Arduino,
// heap allocation, network access, or unchecked motor-output path lives here.
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <ctype.h>

namespace ccoli_robot {
static const size_t MAX_FRAME = 2048;
static const uint32_t MAX_LEASE_MS = 2000;
static const char* const REVISION = "robot-control-1";

struct Calibration {
  float min_angle=20, max_angle=160, center_angle=90, max_speed_dps=45;
  bool inverted=false;
};
struct Command {
  char op[16]={0}, command_id[49]={0}, session_id[49]={0}, boot_id[49]={0};
  char mode[8]={0}, gesture_id[32]={0};
  uint32_t seq=0, valid_for_ms=0, lease_ms=0, duration_ms=0;
  int servo=-1;
  float angle=0, intensity=0.5f;
  Calibration channels[4];
  bool present[4]={false,false,false,false};
};
// Strict bounded JSON tokenization. Control strings deliberately accept only
// printable ASCII without escaping; camera frames and natural-language text
// are separate channels. Duplicate members, unknown fields, nested overflows,
// non-JSON numbers, trailing text, and non-finite values are rejected.
class Json {
 public:
  enum Type { OBJECT, ARRAY, STRING, NUMBER, BOOLEAN };
  struct Token { Type type; int start,end,next; };
  Token t[160]; int count=0; const char* data=nullptr; size_t size=0,pos=0;
  bool parse(const char* value,size_t n) {
    data=value; size=n; pos=0; count=0;
    if(!data || n==0 || n>MAX_FRAME || memchr(data,0,n)) return false;
    if(!valueAt(0)) return false;
    white(); return pos==size && t[0].type==OBJECT;
  }
  bool equal(int i,const char* value) const {
    return i>=0 && static_cast<size_t>(t[i].end-t[i].start)==strlen(value) &&
      memcmp(data+t[i].start,value,strlen(value))==0;
  }
  int field(int object,const char* key) const {
    for(int i=object+1;i<t[object].next;) {
      int value=i+1;
      if(equal(i,key)) return value;
      i=t[value].next;
    }
    return -1;
  }
  bool string(int i,char* out,size_t cap,bool identifier=false,bool empty=false) const {
    if(i<0 || t[i].type!=STRING) return false;
    int n=t[i].end-t[i].start;
    if(n<0 || static_cast<size_t>(n)>=cap || (!empty && n==0)) return false;
    for(int k=0;k<n;k++) {
      const char c=data[t[i].start+k];
      if(identifier && !(isalnum(static_cast<unsigned char>(c)) || c=='-' || c=='_' || c=='.' || c==':')) return false;
    }
    memcpy(out,data+t[i].start,n);out[n]=0;return true;
  }
  bool number(int i,float& out) const {
    if(i<0 || t[i].type!=NUMBER || t[i].end-t[i].start>=40) return false;
    char tmp[40]; const int n=t[i].end-t[i].start;
    memcpy(tmp,data+t[i].start,n);tmp[n]=0;
    char* end=nullptr; double value=strtod(tmp,&end);
    if(end!=tmp+n || !isfinite(value) || value < -1000000.0 || value>1000000.0) return false;
    out=static_cast<float>(value); return isfinite(out);
  }
  bool integer(int i,uint32_t& out) const {
    if(i<0 || t[i].type!=NUMBER || t[i].end-t[i].start>10) return false;
    uint64_t n=0;
    for(int k=t[i].start;k<t[i].end;k++) {
      char c=data[k]; if(c<'0'||c>'9') return false;
      n=n*10+static_cast<unsigned>(c-'0');if(n>0xffffffffULL)return false;
    }
    out=static_cast<uint32_t>(n);return true;
  }
  bool boolean(int i,bool& out) const {
    if(i<0 || t[i].type!=BOOLEAN)return false;
    out=equal(i,"true");return true;
  }
 private:
  void white(){while(pos<size && (data[pos]==' '||data[pos]=='\r'||data[pos]=='\n'||data[pos]=='\t'))pos++;}
  int token(Type type,int start){if(count>=160)return -1;int i=count++;t[i]={type,start,start,i+1};return i;}
  bool valueAt(int depth) {
    white();if(pos>=size || depth>4)return false;
    const char c=data[pos]; int i;
    if(c=='{'||c=='[') {
      const bool object=c=='{';i=token(object?OBJECT:ARRAY,static_cast<int>(pos++));if(i<0)return false;
      white();
      if(pos<size && data[pos]==(object?'}':']')){pos++;t[i].end=pos;t[i].next=count;return true;}
      while(pos<size) {
        if(object) {
          white();if(pos>=size || data[pos]!='"')return false;
          const int key=count;if(!stringAt())return false;
          // Compare previous direct keys in this same object only.
          for(int k=i+1;k<key;k=t[k+1].next)
            if(t[k].end-t[k].start==t[key].end-t[key].start &&
               memcmp(data+t[k].start,data+t[key].start,t[key].end-t[key].start)==0)return false;
          white();if(pos>=size || data[pos++]!=':')return false;
        }
        if(!valueAt(depth+1))return false;
        white();if(pos>=size)return false;
        const char sep=data[pos++];
        if(sep==(object?'}':']')){t[i].end=pos;t[i].next=count;return true;}
        if(sep!=',')return false;
      }
      return false;
    }
    if(c=='"')return stringAt();
    if(c=='t'||c=='f') {
      const char* lit=c=='t'?"true":"false";size_t n=strlen(lit);
      if(pos+n>size || memcmp(data+pos,lit,n)!=0)return false;
      i=token(BOOLEAN,pos);if(i<0)return false;pos+=n;t[i].end=pos;return true;
    }
    if(c=='-' || (c>='0'&&c<='9')) {
      const size_t start=pos;if(c=='-')pos++;
      if(pos>=size)return false;
      if(data[pos]=='0')pos++;
      else {
        if(data[pos]<'1'||data[pos]>'9')return false;
        while(pos<size && isdigit(static_cast<unsigned char>(data[pos])))pos++;
      }
      if(pos<size && data[pos]=='.') {
        pos++;const size_t first=pos;
        while(pos<size && isdigit(static_cast<unsigned char>(data[pos])))pos++;
        if(pos==first)return false;
      }
      if(pos<size && (data[pos]=='e'||data[pos]=='E')) {
        pos++;if(pos<size&&(data[pos]=='+'||data[pos]=='-'))pos++;
        const size_t first=pos;
        while(pos<size&&isdigit(static_cast<unsigned char>(data[pos])))pos++;
        if(pos==first)return false;
      }
      i=token(NUMBER,start);if(i<0)return false;t[i].end=pos;return true;
    }
    return false;
  }
  bool stringAt() {
    if(data[pos++]!='"')return false;
    int i=token(STRING,pos);if(i<0)return false;
    while(pos<size && data[pos]!='"') {
      const unsigned char c=data[pos++];
      if(c<32)return false;
      if(c=='\\') {
        if(pos>=size)return false;
        const char escaped=data[pos++];
        if(escaped=='u') {
          for(int k=0;k<4;k++)if(pos>=size||!isxdigit(static_cast<unsigned char>(data[pos++])))return false;
        } else if(!strchr("\"\\/bfnrt",escaped))return false;
      } else if(c>=128) {
        int continuation=c>=0xc2&&c<=0xdf?1:c>=0xe0&&c<=0xef?2:c>=0xf0&&c<=0xf4?3:-1;
        if(continuation<0||pos+continuation>size)return false;
        const unsigned char first=data[pos];
        if((c==0xe0&&first<0xa0)||(c==0xed&&first>=0xa0)||(c==0xf0&&first<0x90)||(c==0xf4&&first>=0x90))return false;
        while(continuation--)if((static_cast<unsigned char>(data[pos++])&0xc0)!=0x80)return false;
      }
    }
    if(pos>=size)return false;
    t[i].end=pos++;return true;
  }
};

inline bool parseCommand(const char* raw,size_t len,Command& c,const char*& error) {
  Json j;if(!j.parse(raw,len)){error="invalid_json";return false;}
  uint32_t version=0;
  if(!j.equal(j.field(0,"cmd"),"ROBOT_CONTROL") || !j.integer(j.field(0,"v"),version) || version!=1 ||
     !j.string(j.field(0,"op"),c.op,sizeof(c.op),true) ||
     !j.string(j.field(0,"command_id"),c.command_id,sizeof(c.command_id),true) ||
     !j.string(j.field(0,"session_id"),c.session_id,sizeof(c.session_id),true) ||
     !j.string(j.field(0,"boot_id"),c.boot_id,sizeof(c.boot_id),true,true) ||
     !j.integer(j.field(0,"seq"),c.seq) || c.seq==0 ||
     !j.integer(j.field(0,"valid_for_ms"),c.valid_for_ms) || c.valid_for_ms<1 || c.valid_for_ms>MAX_LEASE_MS ||
     !j.integer(j.field(0,"lease_ms"),c.lease_ms) || c.lease_ms<1 || c.lease_ms>MAX_LEASE_MS) {
    error="invalid_fields";return false;
  }
  const bool move=!strcmp(c.op,"move"),cal=!strcmp(c.op,"calibrate"),gesture=!strcmp(c.op,"gesture"),stop=!strcmp(c.op,"stop");
  if(!move&&!cal&&!gesture&&!stop&&strcmp(c.op,"discover")&&strcmp(c.op,"arm")&&strcmp(c.op,"heartbeat")&&strcmp(c.op,"state")){error="unknown_op";return false;}
  for(int k=1;k<j.t[0].next;k=j.t[k+1].next) {
    if(j.equal(k,"cmd")||j.equal(k,"v")||j.equal(k,"op")||j.equal(k,"command_id")||j.equal(k,"session_id")||
       j.equal(k,"boot_id")||j.equal(k,"seq")||j.equal(k,"valid_for_ms")||j.equal(k,"lease_ms"))continue;
    if(move&&(j.equal(k,"servo")||j.equal(k,"angle")||j.equal(k,"duration_ms")))continue;
    if(cal&&j.equal(k,"channels"))continue;
    if(stop&&j.equal(k,"mode"))continue;
    if(gesture&&(j.equal(k,"id")||j.equal(k,"intensity")))continue;
    error="unknown_field";return false;
  }
  if(move) {
    uint32_t servo=0;
    if(!j.integer(j.field(0,"servo"),servo)||servo>3||!j.number(j.field(0,"angle"),c.angle)||
       c.angle<0||c.angle>180||!j.integer(j.field(0,"duration_ms"),c.duration_ms)||
       c.duration_ms<1||c.duration_ms>5000){error="invalid_move";return false;}
    c.servo=servo;
  }
  if(stop) {
    const int mode=j.field(0,"mode");
    if(mode<0)strcpy(c.mode,"detach");
    else if(!j.string(mode,c.mode,sizeof(c.mode)) || (strcmp(c.mode,"detach")&&strcmp(c.mode,"hold"))){error="invalid_stop";return false;}
  }
  if(gesture) {
    if(!j.string(j.field(0,"id"),c.gesture_id,sizeof(c.gesture_id),true) ||
       !j.number(j.field(0,"intensity"),c.intensity)||c.intensity<0||c.intensity>1){error="invalid_gesture";return false;}
  }
  if(cal) {
    int a=j.field(0,"channels");
    if(a<0||j.t[a].type!=Json::ARRAY){error="invalid_calibration";return false;}
    int num=0;
    for(int o=a+1;o<j.t[a].next;o=j.t[o].next) {
      uint32_t idx=0;
      if(++num>4||j.t[o].type!=Json::OBJECT||!j.integer(j.field(o,"servo"),idx)||idx>3||c.present[idx]){error="invalid_calibration";return false;}
      Calibration& v=c.channels[idx];
      if(!j.number(j.field(o,"min_angle"),v.min_angle)||!j.number(j.field(o,"max_angle"),v.max_angle)||
         !j.number(j.field(o,"center_angle"),v.center_angle)||!j.number(j.field(o,"max_speed_dps"),v.max_speed_dps)||
         !j.boolean(j.field(o,"inverted"),v.inverted)||v.min_angle<0||v.max_angle>180||
         !(v.min_angle<v.center_angle&&v.center_angle<v.max_angle)||v.max_speed_dps<1||v.max_speed_dps>90){error="invalid_calibration";return false;}
      for(int k=o+1;k<j.t[o].next;k=j.t[k+1].next)
        if(!j.equal(k,"servo")&&!j.equal(k,"min_angle")&&!j.equal(k,"max_angle")&&!j.equal(k,"center_angle")&&!j.equal(k,"max_speed_dps")&&!j.equal(k,"inverted")){error="unknown_field";return false;}
      c.present[idx]=true;
    }
    if(!num){error="invalid_calibration";return false;}
  }
  error=nullptr;return true;
}

class Controller {
 public:
  typedef void (*Motor)(void*,uint8_t,float,bool);
  typedef void (*Status)(void*,const char*);
  Controller(uint8_t count,const char* device,const char* boot,const char* controller,const char* display,
             Motor motor,Status status,void* context):count_(count>4?4:count),device_(device),boot_(boot),
       controller_(controller),display_(display),motor_(motor),status_(status),context_(context){}
  bool armed()const{return armed_;}
  bool calibrated()const{return calibrated_;}
  bool busy()const{return moving_;}
  float angle(uint8_t i)const{return i<count_?angles_[i]:0;}
  void handle(const char* raw,size_t len,uint32_t now) {
    tick(now);Command c;const char* error=nullptr;
    if(!parseCommand(raw,len,c,error)){emit(c,"ERROR",error,false);return;}
    if(!strcmp(c.op,"stop")) {
      // Stop is allowed across boot/session/sequence boundaries, but never
      // restores a previous session or generates a recentering movement.
      const Command interrupted=moving_?move_:last_;
      const bool external=valid_ && (strcmp(c.session_id,session_) || strcmp(c.boot_id,boot_));
      stop(!strcmp(c.mode,"detach"));
      if(external && interrupted.seq)emit(interrupted,"STOPPED","external_stop",false);
      emit(c,"STOPPED",nullptr,false);return;
    }
    if(!strcmp(c.op,"discover")) {
      if(c.boot_id[0] && strcmp(c.boot_id,boot_)){emit(c,"ERROR","boot_mismatch",false);return;}
      if(valid_ && !strcmp(c.session_id,session_) && replay(c))return;
      stop(true);strcpy(session_,c.session_id);valid_=true;last_seq_=c.seq;last_=c;remember(c);
      emit(c,"DONE",nullptr,true);return;
    }
    if(strcmp(c.boot_id,boot_)){emit(c,"ERROR","boot_mismatch",false);return;}
    if(!valid_||strcmp(c.session_id,session_)){emit(c,"ERROR","session_mismatch",false);return;}
    if(replay(c))return;
    if(c.seq<=last_seq_){emit(c,"ERROR","stale_seq",false);return;}
    last_seq_=c.seq;last_=c;cached_[0]=0;remember(c);
    if(!strcmp(c.op,"calibrate")) {
      if(armed_||moving_){emit(c,"ERROR","must_disarm",false);return;}
      for(uint8_t i=count_;i<4;i++)if(c.present[i]){emit(c,"ERROR","channel_mismatch",false);return;}
      if(!count_){emit(c,"ERROR","no_servos",false);return;}
      for(uint8_t i=0;i<count_;i++){enabled_[i]=c.present[i];if(enabled_[i]){cal_[i]=c.channels[i];angles_[i]=cal_[i].center_angle;}}
      calibrated_=true;emit(c,"DONE",nullptr,false);return;
    }
    if(!strcmp(c.op,"arm")) {
      if(!calibrated_){emit(c,"ERROR","not_calibrated",false);return;}
      armed_=true;lease_started_=now;lease_ms_=c.lease_ms;emit(c,"DONE",nullptr,false);return;
    }
    if(!strcmp(c.op,"state")){emit(c,"DONE",nullptr,true);return;}
    if(!armed_){emit(c,"ERROR","not_armed",false);return;}
    if(!strcmp(c.op,"heartbeat")){lease_started_=now;lease_ms_=c.lease_ms;emit(c,"DONE",nullptr,false);return;}
    if(moving_){emit(c,"ERROR","busy",false);return;}
    if(!strcmp(c.op,"move")) {
      if(c.servo<0||c.servo>=count_||!enabled_[c.servo]){emit(c,"ERROR","channel_mismatch",false);return;}
      Calibration& v=cal_[c.servo];
      if(c.angle<v.min_angle||c.angle>v.max_angle){emit(c,"ERROR","angle_limit",false);return;}
      if(fabsf(c.angle-angles_[c.servo])*1000.0f/c.duration_ms>v.max_speed_dps+0.001f){emit(c,"ERROR","speed_limit",false);return;}
      move_=c;target_=c.angle;start_angle_=angles_[c.servo];start_=now;last_tick_=now;moving_=true;
      lease_started_=now;lease_ms_=c.lease_ms;
      emit(c,"ACK",nullptr,false);emit(c,"RUNNING",nullptr,false);return;
    }
    if(!strcmp(c.op,"gesture")) {
      if(!knownGesture(c.gesture_id)){emit(c,"ERROR","unknown_gesture",false);return;}
      if(gestureDuration(c)>5000){emit(c,"ERROR","gesture_duration_limit",false);return;}
      gesture_=true;gesture_step_=0;gesture_scale_=c.intensity;move_=c;
      lease_started_=now;lease_ms_=c.lease_ms;emit(c,"ACK",nullptr,false);emit(c,"RUNNING",nullptr,false);
      beginGestureStep(now);return;
    }
  }
  void tick(uint32_t now) {
    if(armed_ && static_cast<uint32_t>(now-lease_started_)>=lease_ms_) {
      Command failed=moving_?move_:last_;stop(true);emit(failed,"STOPPED","lease_expired",false);return;
    }
    if(!moving_)return;
    if(static_cast<uint32_t>(now-last_tick_)>250){Command failed=move_;stop(true);emit(failed,"STOPPED","scheduler_stalled",false);return;}
    const uint32_t elapsed=now-start_;
    const float p=elapsed>=move_.duration_ms?1.0f:static_cast<float>(elapsed)/move_.duration_ms;
    const uint8_t servo=static_cast<uint8_t>(move_.servo);
    const float next=start_angle_+(target_-start_angle_)*p;
    if(now!=last_tick_||p==1.0f){angles_[servo]=next;output(servo,true);last_tick_=now;}
    if(p>=1.0f) {
      moving_=false;
      if(gesture_ && ++gesture_step_<gestureSteps())beginGestureStep(now);
      else {gesture_=false;emit(move_,"DONE",nullptr,false);}
    }
  }
  void emergencyStop(const char* error="physical_stop") {
    Command c=moving_?move_:last_;stop(true);emit(c,"STOPPED",error,false);
  }
 private:
  uint8_t count_;const char *device_,*boot_,*controller_,*display_;
  Motor motor_;Status status_;void* context_;
  Calibration cal_[4];bool enabled_[4]={false,false,false,false};float angles_[4]={90,90,90,90};
  char session_[49]={0},cached_[MAX_FRAME+1]={0};
  char recent_ids_[16][49]={{0}};uint32_t recent_seq_[16]={0};uint8_t recent_next_=0;
  bool valid_=false,calibrated_=false,armed_=false,moving_=false,gesture_=false;
  uint32_t last_seq_=0,lease_started_=0,lease_ms_=0,start_=0,last_tick_=0;
  float target_=90,start_angle_=90,gesture_scale_=0.5f;
  uint8_t gesture_step_=0;
  Command last_,move_;
  void output(uint8_t i,bool enable) {
    if(motor_)motor_(context_,i,cal_[i].inverted?180.0f-angles_[i]:angles_[i],enable);
  }
  void stop(bool detach) {
    moving_=false;gesture_=false;armed_=false;calibrated_=false;valid_=false;cached_[0]=0;memset(recent_ids_,0,sizeof(recent_ids_));recent_next_=0;
    if(detach)for(uint8_t i=0;i<count_;i++)output(i,false);
  }
  bool replay(const Command& c) {
    if(c.seq==last_seq_ && !strcmp(c.command_id,last_.command_id)) {
      if(cached_[0]&&status_)status_(context_,cached_);else emit(c,"ERROR","duplicate_expired",false);
      return true;
    }
    // Bounded ID history supplements monotonic seq for altered retransmissions.
    for(uint8_t i=0;i<16;i++)if(!strcmp(c.command_id,recent_ids_[i])){emit(c,"ERROR",c.seq==recent_seq_[i]?"duplicate_command":"command_id_reused",false);return true;}
    return false;
  }
  void remember(const Command& c){strcpy(recent_ids_[recent_next_],c.command_id);recent_seq_[recent_next_]=c.seq;recent_next_=(recent_next_+1)%16;}
  void emit(const Command& c,const char* status,const char* error,bool capabilities) {
    char out[MAX_FRAME+1];char angles[100];int at=snprintf(angles,sizeof(angles),"[");
    for(uint8_t i=0;i<count_;i++)at+=snprintf(angles+at,sizeof(angles)-at,"%s%.2f",i?",":"",angles_[i]);
    snprintf(angles+at,sizeof(angles)-at,"]");
    int n=snprintf(out,sizeof(out),"{\"v\":1,\"status\":\"%s\",\"op\":\"%s\",\"command_id\":\"%s\",\"session_id\":\"%s\",\"boot_id\":\"%s\",\"seq\":%lu,\"armed\":%s,\"calibrated\":%s,\"busy\":%s,\"commanded_angles\":%s,\"feedback_kind\":\"commanded\"",
       status,c.op,c.command_id,c.session_id,boot_,static_cast<unsigned long>(c.seq),armed_?"true":"false",calibrated_?"true":"false",moving_?"true":"false",angles);
    if(error)n+=snprintf(out+n,sizeof(out)-n,",\"error\":\"%s\"",error);
    if(capabilities)n+=snprintf(out+n,sizeof(out)-n,",\"capabilities\":{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"controller\":\"%s\",\"firmware_revision\":\"%s\",\"protocol_version\":1,\"servo_count\":%u,\"display\":\"%s\",\"feedback_kind\":\"commanded\",\"sensors\":[]}",device_,boot_,controller_,REVISION,count_,display_);
    snprintf(out+n,sizeof(out)-n,"}");
    if(c.seq==last_seq_&&!strcmp(c.command_id,last_.command_id)&&!strcmp(c.session_id,session_))strcpy(cached_,out);
    if(status_)status_(context_,out);
  }
  bool knownGesture(const char* id)const {
    static const char* const ids[]={"farewell_wave","goodnight_settle","curious_tilt","happy_bounce","hurt_turnaway","idle_stretch","notification_nod","camera_scan"};
    for(size_t i=0;i<8;i++)if(!strcmp(id,ids[i]))return true;
    return false;
  }
  int gestureChannel(const char* id) const {
    int channel=0;
    if(!strcmp(id,"farewell_wave"))channel=count_>=4?3:0;
    else if(!strcmp(id,"curious_tilt")||!strcmp(id,"hurt_turnaway")||!strcmp(id,"camera_scan"))channel=count_>=2?1:0;
    else if(!strcmp(id,"idle_stretch"))channel=count_>=3?2:0;
    if(!enabled_[channel])for(uint8_t i=0;i<count_;i++)if(enabled_[i]){channel=i;break;}
    return channel;
  }
  uint32_t gestureDuration(const Command& c) const {
    const int channel=gestureChannel(c.gesture_id);
    const Calibration& v=cal_[channel];
    const float room=fminf(v.center_angle-v.min_angle,v.max_angle-v.center_angle);
    const float extent=fminf(room*0.3f,18.0f)*c.intensity;
    const bool scan=!strcmp(c.gesture_id,"camera_scan");
    static const float scans[]={-1,0,1,0,0},waves[]={-1,1,-1,0};
    float previous=angles_[channel];uint32_t total=0;
    for(uint8_t i=0;i<(scan?5:4);i++) {
      const float next=v.center_angle+(scan?scans[i]:waves[i])*extent;
      const uint32_t duration=static_cast<uint32_t>(ceilf(fabsf(next-previous)*1000.0f/v.max_speed_dps));
      total+=duration<300?300:duration;previous=next;
    }
    return total;
  }
  uint8_t gestureSteps()const{return !strcmp(move_.gesture_id,"camera_scan")?5:4;}
  void beginGestureStep(uint32_t now) {
    // Named gestures are small, calibration-relative motions. Four-servo
    // profiles add an arm for the farewell gesture; 1/2-channel profiles use
    // a head channel. No new targets can exceed the calibrated envelope.
    const int channel=gestureChannel(move_.gesture_id);

    move_.servo=channel;
    const Calibration& v=cal_[channel];
    const float room=fminf(v.center_angle-v.min_angle,v.max_angle-v.center_angle);
    const float extent=fminf(room*0.3f,18.0f)*gesture_scale_;
    static const float scan[]={-1,0,1,0,0};
    static const float wave[]={-1,1,-1,0};
    const float offset=!strcmp(move_.gesture_id,"camera_scan")?scan[gesture_step_]:wave[gesture_step_];
    target_=v.center_angle+offset*extent;start_angle_=angles_[channel];
    const uint32_t required=static_cast<uint32_t>(ceilf(fabsf(target_-start_angle_)*1000.0f/v.max_speed_dps));
    move_.duration_ms=required<300?300:required;start_=now;last_tick_=now;moving_=true;
  }
};
} // namespace ccoli_robot
