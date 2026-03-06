#ifndef DISPLAY_CONTROL_H
#define DISPLAY_CONTROL_H

#include <Adafruit_SSD1306.h>

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

void display_init();
void display_show_face(FaceType face);
void display_set_status_text(const char* text);
void display_update();
void display_clear();

#endif