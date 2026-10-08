#ifndef DISPLAY_CONTROL_H
#define DISPLAY_CONTROL_H

// display_control.cpp includes this header first, so it cannot rely on
// Arduino.h having already pulled in the fixed-width integer types.
#include <stdint.h>

enum FaceType {
  FACE_NEUTRAL,
  FACE_HAPPY,
  FACE_SAD,
  FACE_ANGRY,
  FACE_SURPRISED,
  FACE_SLEEPY,
  FACE_LOVE,
  FACE_CURIOUS,
  FACE_EXCITED,
  FACE_CONFUSED,
  FACE_COUNT
};

enum DisplayState {
  DS_BOOT,
  DS_CONNECTING,
  DS_IDLE,
  DS_LISTENING,
  DS_PROCESSING,
  DS_SPEAKING
};

void display_init();
void display_set_state(DisplayState state);
void display_show_face(FaceType face);
void display_set_status_text(const char* text);
void display_set_speech_text(const char* text);
void display_set_audio_level(uint8_t level);  // 0-255
void display_update();
void display_clear();

#endif
