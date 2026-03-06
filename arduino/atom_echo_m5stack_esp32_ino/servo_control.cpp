#include "servo_control.h"
#include "config.h"

struct ActionStep {
  uint8_t servo;
  uint8_t angle;
  uint16_t delay_after_ms;
};

struct ServoState {
  int current_angle;
  unsigned long next_step_time;
  int step_index;
  const ActionStep* current_action;
  bool busy;
};

static Servo servos[2];
static ServoState servo_states[2];

static int clamp_angle(int angle) {
  if (angle < SERVO_MIN_ANGLE) return SERVO_MIN_ANGLE;
  if (angle > SERVO_MAX_ANGLE) return SERVO_MAX_ANGLE;
  return angle;
}

// Action presets
static const ActionStep action_nod_yes[] = {
  {0, 70, 150}, {0, 90, 150}, {0, 70, 150}, {0, 90, 150}, {0, 90, 0}
};

static const ActionStep action_nod_no[] = {
  {1, 60, 200}, {1, 120, 200}, {1, 90, 200}, {1, 90, 0}
};

static const ActionStep action_tilt_curious[] = {
  {1, 65, 1000}, {1, 90, 0}
};

static const ActionStep action_bounce_happy[] = {
  {0, 75, 100}, {0, 90, 100}, {0, 75, 100}, {0, 90, 100}, {0, 75, 100}, {0, 90, 100},
  {1, 80, 150}, {1, 100, 150}, {1, 90, 0}
};

static const ActionStep action_droop_sad[] = {
  {0, 110, 2000}, {0, 90, 0}
};

static const ActionStep action_shake_angry[] = {
  {0, 85, 60}, {0, 95, 60}, {0, 85, 60}, {0, 95, 60}, {0, 85, 60}, {0, 95, 60}, 
  {0, 85, 60}, {0, 95, 60}, {0, 85, 60}, {0, 90, 0}
};

static const ActionStep action_startle[] = {
  {0, 60, 200}, {0, 90, 0}
};

static const ActionStep action_dance[] = {
  {0, 70, 250}, {1, 60, 0}, {0, 110, 250}, {1, 120, 0}, 
  {0, 70, 250}, {1, 60, 0}, {0, 110, 250}, {1, 120, 0},
  {0, 70, 250}, {1, 60, 0}, {0, 110, 250}, {1, 120, 0},
  {0, 70, 250}, {1, 60, 0}, {0, 90, 0}, {1, 90, 0}
};

static const ActionStep action_sleep_drift[] = {
  {0, 105, 1500}, {1, 80, 1500}, {0, 90, 0}, {1, 90, 0}
};

static const ActionStep action_wiggle[] = {
  {1, 75, 150}, {1, 105, 150}, {1, 75, 150}, {1, 105, 150}, 
  {1, 75, 150}, {1, 90, 0}
};

void servo_init() {
  servos[0].setPeriodHertz(50);
  servos[0].attach(SERVO_PIN_PITCH, 500, 2400);
  servos[1].setPeriodHertz(50);
  servos[1].attach(SERVO_PIN_TILT, 500, 2400);
  
  servo_states[0] = {SERVO_CENTER_ANGLE, 0, 0, nullptr, false};
  servo_states[1] = {SERVO_CENTER_ANGLE, 0, 0, nullptr, false};
  
  servos[0].write(SERVO_CENTER_ANGLE);
  servos[1].write(SERVO_CENTER_ANGLE);
}

void servo_set_angle(int servo_idx, int angle) {
  if (servo_idx < 0 || servo_idx > 1) return;
  angle = clamp_angle(angle);
  servos[servo_idx].write(angle);
  servo_states[servo_idx].current_angle = angle;
}

void servo_play_action(ServoAction action) {
  const ActionStep* steps = nullptr;
  
  switch (action) {
    case ACTION_NOD_YES: steps = action_nod_yes; break;
    case ACTION_NOD_NO: steps = action_nod_no; break;
    case ACTION_TILT_CURIOUS: steps = action_tilt_curious; break;
    case ACTION_BOUNCE_HAPPY: steps = action_bounce_happy; break;
    case ACTION_DROOP_SAD: steps = action_droop_sad; break;
    case ACTION_SHAKE_ANGRY: steps = action_shake_angry; break;
    case ACTION_STARTLE: steps = action_startle; break;
    case ACTION_DANCE: steps = action_dance; break;
    case ACTION_SLEEP_DRIFT: steps = action_sleep_drift; break;
    case ACTION_WIGGLE: steps = action_wiggle; break;
    default: return;
  }
  
  servo_states[0].current_action = steps;
  servo_states[0].step_index = 0;
  servo_states[0].next_step_time = millis();
  servo_states[0].busy = true;
  servo_states[1].busy = true;
}

void servo_stop() {
  servo_states[0].busy = false;
  servo_states[1].busy = false;
  servo_states[0].current_action = nullptr;
  servo_states[1].current_action = nullptr;
  servos[0].write(SERVO_CENTER_ANGLE);
  servos[1].write(SERVO_CENTER_ANGLE);
}

void servo_update() {
  if (!servo_states[0].busy || !servo_states[0].current_action) return;
  
  unsigned long now = millis();
  if (now >= servo_states[0].next_step_time) {
    const ActionStep& step = servo_states[0].current_action[servo_states[0].step_index];
    servo_set_angle(step.servo, step.angle);
    
    if (step.delay_after_ms == 0) {
      servo_states[0].busy = false;
      servo_states[1].busy = false;
      servo_states[0].current_action = nullptr;
      return;
    }
    
    servo_states[0].next_step_time = now + step.delay_after_ms;
    servo_states[0].step_index++;
  }
}

bool servo_is_busy() {
  return servo_states[0].busy || servo_states[1].busy;
}

// Backward compatibility
void servo_wiggle() {
  servo_play_action(ACTION_WIGGLE);
}

void servo_rotate() {
  servo_play_action(ACTION_DANCE);
}