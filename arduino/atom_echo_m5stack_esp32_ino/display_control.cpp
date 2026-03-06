#include "display_control.h"
#include "config.h"
#include <Wire.h>

Adafruit_SSD1306 display(DISPLAY_WIDTH, DISPLAY_HEIGHT, &Wire, -1);

static FaceType current_face = FACE_NEUTRAL;
static char status_text[32] = "";
static unsigned long last_blink_ms = 0;
static bool blink_state = false;
static unsigned long blink_duration = 150;

// Idle gaze state
static int gaze_offset_x = 0;  // -4 to +4 pixel offset for eye position
static int gaze_offset_y = 0;
static unsigned long last_gaze_ms = 0;

// Emotion decay
static unsigned long last_emotion_set_ms = 0;

// Throttle display refresh to ~15fps
static unsigned long last_draw_ms = 0;
static const unsigned long DRAW_INTERVAL_MS = 66;

void display_init() {
  Wire.begin(DISPLAY_SDA_PIN, DISPLAY_SCL_PIN);
  display.begin(SSD1306_SWITCHCAPVCC, DISPLAY_I2C_ADDR);
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.display();
  last_emotion_set_ms = millis();
}

// Eye base positions + gaze offset
static int lx() { return 40 + gaze_offset_x; }
static int ly() { return 22 + gaze_offset_y; }
static int rx() { return 88 + gaze_offset_x; }
static int ry() { return 22 + gaze_offset_y; }

void draw_eyes(bool blinking) {
  if (blinking) {
    display.drawLine(lx()-8, ly(), lx()+8, ly(), SSD1306_WHITE);
    display.drawLine(rx()-8, ry(), rx()+8, ry(), SSD1306_WHITE);
    return;
  }

  switch (current_face) {
    case FACE_NEUTRAL:
    case FACE_SAD:
    case FACE_ANGRY:
      display.fillCircle(lx(), ly(), 8, SSD1306_WHITE);
      display.fillCircle(rx(), ry(), 8, SSD1306_WHITE);
      break;
    case FACE_HAPPY:
      display.drawCircle(lx(), ly()-2, 8, SSD1306_WHITE);
      display.drawLine(lx()-8, ly()-4, lx()+8, ly(), SSD1306_WHITE);
      display.drawCircle(rx(), ry()-2, 8, SSD1306_WHITE);
      display.drawLine(rx()-8, ry()-4, rx()+8, ry(), SSD1306_WHITE);
      break;
    case FACE_SURPRISED:
      display.drawCircle(lx(), ly(), 12, SSD1306_WHITE);
      display.drawCircle(rx(), ry(), 12, SSD1306_WHITE);
      break;
    case FACE_SLEEPY:
      display.drawLine(lx()-8, ly(), lx()+8, ly(), SSD1306_WHITE);
      display.drawLine(rx()-8, ry(), rx()+8, ry(), SSD1306_WHITE);
      break;
    case FACE_LOVE:
      display.fillTriangle(lx(), ly()-4, lx()-4, ly()+4, lx()+4, ly()+4, SSD1306_WHITE);
      display.fillCircle(lx()-2, ly()-2, 3, SSD1306_WHITE);
      display.fillCircle(lx()+2, ly()-2, 3, SSD1306_WHITE);
      display.fillTriangle(rx(), ry()-4, rx()-4, ry()+4, rx()+4, ry()+4, SSD1306_WHITE);
      display.fillCircle(rx()-2, ry()-2, 3, SSD1306_WHITE);
      display.fillCircle(rx()+2, ry()-2, 3, SSD1306_WHITE);
      break;
    case FACE_CURIOUS:
      display.fillCircle(lx(), ly(), 8, SSD1306_WHITE);
      display.drawCircle(rx(), ry(), 12, SSD1306_WHITE);
      break;
    case FACE_EXCITED:
      display.drawLine(lx()-8, ly(), lx()+8, ly(), SSD1306_WHITE);
      display.drawLine(lx(), ly()-8, lx(), ly()+8, SSD1306_WHITE);
      display.drawLine(lx()-6, ly()-6, lx()+6, ly()+6, SSD1306_WHITE);
      display.drawLine(lx()+6, ly()-6, lx()-6, ly()+6, SSD1306_WHITE);
      display.drawLine(rx()-8, ry(), rx()+8, ry(), SSD1306_WHITE);
      display.drawLine(rx(), ry()-8, rx(), ry()+8, SSD1306_WHITE);
      display.drawLine(rx()-6, ry()-6, rx()+6, ry()+6, SSD1306_WHITE);
      display.drawLine(rx()+6, ry()-6, rx()-6, ry()+6, SSD1306_WHITE);
      break;
    case FACE_CONFUSED:
      display.fillCircle(lx(), ly(), 8, SSD1306_WHITE);
      display.fillCircle(rx(), ry()-4, 8, SSD1306_WHITE);
      break;
    default: break;
  }
}

void draw_mouth() {
  switch (current_face) {
    case FACE_NEUTRAL:
      display.drawCircle(64, 48, 3, SSD1306_WHITE);
      break;
    case FACE_HAPPY:
    case FACE_EXCITED:
      display.drawCircle(64, 40, 12, SSD1306_WHITE);
      display.fillRect(52, 32, 24, 12, SSD1306_BLACK);
      break;
    case FACE_SAD:
      display.drawCircle(64, 56, 12, SSD1306_WHITE);
      display.fillRect(52, 48, 24, 12, SSD1306_BLACK);
      break;
    case FACE_ANGRY:
      display.drawLine(52, 48, 76, 48, SSD1306_WHITE);
      break;
    case FACE_SURPRISED:
      display.drawCircle(64, 48, 6, SSD1306_WHITE);
      break;
    case FACE_SLEEPY:
    case FACE_LOVE:
      display.drawCircle(64, 48, 3, SSD1306_WHITE);
      break;
    case FACE_CURIOUS:
      display.drawLine(62, 48, 66, 48, SSD1306_WHITE);
      break;
    case FACE_CONFUSED:
      display.drawLine(56, 46, 60, 50, SSD1306_WHITE);
      display.drawLine(60, 50, 64, 46, SSD1306_WHITE);
      display.drawLine(64, 46, 68, 50, SSD1306_WHITE);
      display.drawLine(68, 50, 72, 46, SSD1306_WHITE);
      break;
    default: break;
  }
}

void draw_extras() {
  switch (current_face) {
    case FACE_SAD:
      display.drawLine(38, 12, 42, 16, SSD1306_WHITE);
      display.drawLine(86, 12, 90, 16, SSD1306_WHITE);
      break;
    case FACE_ANGRY:
      display.drawLine(32, 12, 48, 18, SSD1306_WHITE);
      display.drawLine(96, 12, 80, 18, SSD1306_WHITE);
      break;
    case FACE_CONFUSED:
      display.drawLine(100, 20, 100, 28, SSD1306_WHITE);
      display.drawLine(98, 22, 102, 22, SSD1306_WHITE);
      display.fillCircle(100, 32, 2, SSD1306_WHITE);
      break;
    default: break;
  }
}

void display_show_face(FaceType face) {
  current_face = face;
  last_emotion_set_ms = millis();
  status_text[0] = '\0';  // clear status on new emotion
}

void display_set_status_text(const char* text) {
  strncpy(status_text, text ? text : "", sizeof(status_text) - 1);
  status_text[sizeof(status_text) - 1] = '\0';
}

void display_update() {
  unsigned long now = millis();

  // Throttle redraws
  if (now - last_draw_ms < DRAW_INTERVAL_MS) return;
  last_draw_ms = now;

  // Blink animation (3-5s random interval)
  if (now - last_blink_ms > (blink_state ? blink_duration : (unsigned long)random(IDLE_BLINK_MIN_MS, IDLE_BLINK_MAX_MS))) {
    blink_state = !blink_state;
    last_blink_ms = now;
  }

  // Idle gaze shift (only in neutral face)
  if (current_face == FACE_NEUTRAL && now - last_gaze_ms > IDLE_GAZE_INTERVAL_MS) {
    gaze_offset_x = random(-4, 5);
    gaze_offset_y = random(-2, 3);
    last_gaze_ms = now;
  }
  // Reset gaze for non-neutral faces
  if (current_face != FACE_NEUTRAL) {
    gaze_offset_x = 0;
    gaze_offset_y = 0;
  }

  // Emotion decay → neutral
  if (current_face != FACE_NEUTRAL && (now - last_emotion_set_ms > EMOTION_DECAY_INTERVAL_MS)) {
    current_face = FACE_NEUTRAL;
    status_text[0] = '\0';
  }

  display.clearDisplay();
  draw_eyes(blink_state);
  draw_mouth();
  draw_extras();

  if (status_text[0]) {
    display.setTextSize(1);
    display.setCursor(0, 56);
    display.print(status_text);
  }

  display.display();
}

void display_clear() {
  display.clearDisplay();
  display.display();
}
