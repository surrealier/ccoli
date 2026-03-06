#ifndef SERVO_CONTROL_H
#define SERVO_CONTROL_H

#include <ESP32Servo.h>

enum ServoAction {
  ACTION_NONE,
  ACTION_NOD_YES,
  ACTION_NOD_NO,
  ACTION_TILT_CURIOUS,
  ACTION_BOUNCE_HAPPY,
  ACTION_DROOP_SAD,
  ACTION_SHAKE_ANGRY,
  ACTION_STARTLE,
  ACTION_DANCE,
  ACTION_SLEEP_DRIFT,
  ACTION_WIGGLE
};

void servo_init();
void servo_set_angle(int servo_idx, int angle);
void servo_play_action(ServoAction action);
void servo_stop();
void servo_update();
bool servo_is_busy();

// Backward compatibility
void servo_wiggle();
void servo_rotate();

#endif