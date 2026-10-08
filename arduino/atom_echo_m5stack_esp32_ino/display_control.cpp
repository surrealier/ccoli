#include "display_control.h"
#include "config.h"
#include <string.h>

// ════════════════════════════════════════════════════════════════
// ST7789V2 Color LCD implementation (DISPLAY_TYPE == 2)
// ════════════════════════════════════════════════════════════════
#if DISPLAY_TYPE == 2

#if defined(__has_include) && __has_include(<Adafruit_ST7789.h>)
  #include <SPI.h>
  #include <Adafruit_GFX.h>
  #include <Adafruit_ST7789.h>
  #define CCOLI_HAS_ST7789 1
#else
  #define CCOLI_HAS_ST7789 0
#endif

#if CCOLI_HAS_ST7789

// ── RGB565 helper ──
#define RGB565(r,g,b) (uint16_t)(((r&0xF8)<<8)|((g&0xFC)<<3)|(b>>3))

// ── Emotion color palette ──
struct EmotionTheme { uint16_t bg; uint16_t accent; uint16_t eye; };
static const EmotionTheme THEMES[FACE_COUNT] = {
  { RGB565(12,22,16),  RGB565(111,207,138), RGB565(255,255,255) }, // neutral
  { RGB565(42,32,0),   RGB565(255,215,0),   RGB565(255,255,255) }, // happy
  { RGB565(10,20,42),  RGB565(85,136,255),  RGB565(200,220,255) }, // sad
  { RGB565(42,10,10),  RGB565(255,68,68),   RGB565(255,200,200) }, // angry
  { RGB565(26,26,40),  RGB565(200,200,255), RGB565(255,255,255) }, // surprised
  { RGB565(20,10,40),  RGB565(136,85,204),  RGB565(200,180,255) }, // sleepy
  { RGB565(42,10,22),  RGB565(255,102,153), RGB565(255,200,220) }, // love
  { RGB565(10,40,28),  RGB565(68,221,170),  RGB565(200,255,240) }, // curious
  { RGB565(42,10,42),  RGB565(255,68,204),  RGB565(255,200,240) }, // excited
  { RGB565(42,28,10),  RGB565(255,170,68),  RGB565(255,230,200) }, // confused
};

static SPIClass hspi(HSPI);
static Adafruit_ST7789 tft(&hspi, LCD_PIN_CS, LCD_PIN_DC, -1);
static bool lcd_ready = false;

static DisplayState cur_state = DS_BOOT;
static FaceType cur_face = FACE_NEUTRAL;
static char status_text[32] = "";
static char speech_text[128] = "";
static uint8_t audio_level = 0;

static unsigned long last_draw_ms = 0;
static unsigned long last_blink_ms = 0;
static unsigned long last_gaze_ms = 0;
static unsigned long last_emotion_ms = 0;
static unsigned long state_enter_ms = 0;
static bool blink_state = false;
static int gaze_x = 0, gaze_y = 0;
static DisplayState prev_state = DS_BOOT;
static FaceType prev_face = FACE_NEUTRAL;

// draw_face()/draw_speaking() open with a full-screen fill: 240x280x2 bytes over
// SPI, tens of milliseconds during which the shared main loop cannot service
// M5.Mic.record() or the socket. Those two screens are static between events, so
// they are repainted only when something visible actually changed. The remaining
// states animate off millis() and still redraw every frame.
static bool needs_redraw = true;

static const unsigned long DRAW_MS = 66; // ~15fps

// ── Screen layout constants ──
static const int EYE_Y = 100;
static const int EYE_LX = 80, EYE_RX = 160;
static const int EYE_R = 22;
static const int MOUTH_Y = 175;
static const int MOUTH_CX = 120;
static const int BUBBLE_Y = 220;

// ── Forward declarations ──
static void draw_boot();
static void draw_connecting();
static void draw_face();
static void draw_listening();
static void draw_speaking();
static void draw_processing();

// ════════════════════════════════════════════════════════════════
// Boot & Connecting screens
// ════════════════════════════════════════════════════════════════
static void draw_boot() {
  unsigned long elapsed = millis() - state_enter_ms;
  tft.fillScreen(RGB565(8,16,10));
  // Logo text
  tft.setTextColor(RGB565(111,207,138));
  tft.setTextSize(4);
  tft.setCursor(48, 100);
  tft.print("ccoli");
  // Tagline
  tft.setTextColor(RGB565(80,120,90));
  tft.setTextSize(1);
  tft.setCursor(52, 150);
  tft.print("voice AI assistant");
  // Progress bar
  int bar_w = min((int)(elapsed / 10), 160);
  tft.fillRoundRect(40, 190, 160, 8, 4, RGB565(20,35,25));
  if (bar_w > 0)
    tft.fillRoundRect(40, 190, bar_w, 8, 4, RGB565(111,207,138));
}

static void draw_connecting() {
  unsigned long elapsed = millis() - state_enter_ms;
  tft.fillScreen(RGB565(8,16,10));
  // Pulsing circle
  int pulse = 20 + (int)(8.0f * sinf((float)elapsed / 400.0f));
  tft.drawCircle(120, 110, pulse, RGB565(111,207,138));
  tft.drawCircle(120, 110, pulse + 6, RGB565(50,90,60));
  // Dots animation
  tft.setTextColor(RGB565(111,207,138));
  tft.setTextSize(2);
  int dots = ((elapsed / 500) % 4);
  char buf[20] = "connecting";
  for (int i = 0; i < dots; i++) strcat(buf, ".");
  tft.setCursor(30, 170);
  tft.print(buf);
}

// ════════════════════════════════════════════════════════════════
// Emotion face drawing
// ════════════════════════════════════════════════════════════════
static void draw_eyes(const EmotionTheme& t, bool blinking) {
  int lx = EYE_LX + gaze_x, ly = EYE_Y + gaze_y;
  int rx = EYE_RX + gaze_x, ry = EYE_Y + gaze_y;

  if (blinking) {
    tft.fillRoundRect(lx - EYE_R, ly - 2, EYE_R*2, 4, 2, t.eye);
    tft.fillRoundRect(rx - EYE_R, ry - 2, EYE_R*2, 4, 2, t.eye);
    return;
  }

  switch (cur_face) {
    case FACE_HAPPY:
      // Upward arcs (happy squint)
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry, EYE_R, t.eye);
      tft.fillRect(lx - EYE_R - 2, ly, EYE_R*2 + 4, EYE_R + 4, t.bg);
      tft.fillRect(rx - EYE_R - 2, ry, EYE_R*2 + 4, EYE_R + 4, t.bg);
      break;
    case FACE_SAD:
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry, EYE_R, t.eye);
      // Droopy eyelids
      tft.fillTriangle(lx-EYE_R-2, ly-EYE_R, lx+EYE_R+2, ly-EYE_R, lx-EYE_R-2, ly-4, t.bg);
      tft.fillTriangle(rx-EYE_R-2, ry-EYE_R, rx+EYE_R+2, ry-EYE_R, rx+EYE_R+2, ry-4, t.bg);
      break;
    case FACE_ANGRY:
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry, EYE_R, t.eye);
      // Angry brows
      tft.fillTriangle(lx-EYE_R-2, ly-EYE_R, lx+EYE_R+2, ly-EYE_R, lx+EYE_R+2, ly-6, t.bg);
      tft.fillTriangle(rx-EYE_R-2, ry-EYE_R, rx+EYE_R+2, ry-EYE_R, rx-EYE_R-2, ry-6, t.bg);
      break;
    case FACE_SURPRISED:
      tft.drawCircle(lx, ly, EYE_R+4, t.eye);
      tft.drawCircle(lx, ly, EYE_R+3, t.eye);
      tft.drawCircle(rx, ry, EYE_R+4, t.eye);
      tft.drawCircle(rx, ry, EYE_R+3, t.eye);
      tft.fillCircle(lx, ly, 8, t.eye);
      tft.fillCircle(rx, ry, 8, t.eye);
      break;
    case FACE_SLEEPY:
      tft.fillRoundRect(lx-EYE_R, ly-3, EYE_R*2, 6, 3, t.eye);
      tft.fillRoundRect(rx-EYE_R, ry-3, EYE_R*2, 6, 3, t.eye);
      break;
    case FACE_LOVE:
      // Hearts
      for (int side = 0; side < 2; side++) {
        int cx = side == 0 ? lx : rx;
        int cy = side == 0 ? ly : ry;
        tft.fillCircle(cx-8, cy-6, 10, t.accent);
        tft.fillCircle(cx+8, cy-6, 10, t.accent);
        tft.fillTriangle(cx-18, cy-2, cx+18, cy-2, cx, cy+16, t.accent);
      }
      break;
    case FACE_CURIOUS:
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry, EYE_R+8, t.eye);
      tft.fillCircle(rx, ry, EYE_R+2, t.bg);
      tft.fillCircle(rx, ry, 10, t.eye);
      break;
    case FACE_EXCITED:
      // Star-like eyes
      for (int side = 0; side < 2; side++) {
        int cx = side == 0 ? lx : rx;
        int cy = side == 0 ? ly : ry;
        int s = EYE_R;
        tft.drawLine(cx-s, cy, cx+s, cy, t.accent);
        tft.drawLine(cx, cy-s, cx, cy+s, t.accent);
        tft.drawLine(cx-s*7/10, cy-s*7/10, cx+s*7/10, cy+s*7/10, t.accent);
        tft.drawLine(cx+s*7/10, cy-s*7/10, cx-s*7/10, cy+s*7/10, t.accent);
        tft.fillCircle(cx, cy, 6, t.accent);
      }
      break;
    case FACE_CONFUSED:
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry-6, EYE_R, t.eye);
      break;
    default: // NEUTRAL
      tft.fillCircle(lx, ly, EYE_R, t.eye);
      tft.fillCircle(rx, ry, EYE_R, t.eye);
      // Pupils
      tft.fillCircle(lx + gaze_x/2, ly + gaze_y/2, 10, RGB565(30,30,30));
      tft.fillCircle(rx + gaze_x/2, ry + gaze_y/2, 10, RGB565(30,30,30));
      // Highlights
      tft.fillCircle(lx + gaze_x/2 + 4, ly + gaze_y/2 - 4, 3, RGB565(255,255,255));
      tft.fillCircle(rx + gaze_x/2 + 4, ry + gaze_y/2 - 4, 3, RGB565(255,255,255));
      break;
  }
}

static void draw_mouth(const EmotionTheme& t) {
  int cx = MOUTH_CX, cy = MOUTH_Y;
  switch (cur_face) {
    case FACE_HAPPY:
    case FACE_EXCITED:
      tft.fillCircle(cx, cy-4, 18, t.accent);
      tft.fillRect(cx-20, cy-24, 40, 20, t.bg);
      break;
    case FACE_SAD:
      tft.fillCircle(cx, cy+12, 16, t.accent);
      tft.fillRect(cx-18, cy+12, 36, 18, t.bg);
      break;
    case FACE_ANGRY:
      tft.fillRect(cx-18, cy, 36, 4, t.accent);
      break;
    case FACE_SURPRISED:
      tft.drawCircle(cx, cy, 12, t.accent);
      tft.drawCircle(cx, cy, 11, t.accent);
      break;
    case FACE_LOVE:
      tft.fillCircle(cx, cy-2, 14, t.accent);
      tft.fillRect(cx-16, cy-18, 32, 16, t.bg);
      break;
    case FACE_CONFUSED:
      for (int i = 0; i < 4; i++)
        tft.drawLine(cx-18+i*12, cy+(i%2?-4:4), cx-6+i*12, cy+(i%2?4:-4), t.accent);
      break;
    default: // neutral, sleepy, curious
      tft.fillCircle(cx, cy, 6, t.accent);
      break;
  }
}

static void draw_face() {
  const EmotionTheme& t = THEMES[cur_face < FACE_COUNT ? cur_face : 0];
  tft.fillScreen(t.bg);
  draw_eyes(t, blink_state);
  draw_mouth(t);
  // Status text at bottom
  if (status_text[0]) {
    tft.setTextColor(t.accent);
    tft.setTextSize(1);
    tft.setCursor(8, LCD_HEIGHT - 16);
    tft.print(status_text);
  }
}

// ════════════════════════════════════════════════════════════════
// Listening animation (waveform bars)
// ════════════════════════════════════════════════════════════════
static void draw_listening() {
  const EmotionTheme& t = THEMES[0]; // neutral theme
  tft.fillScreen(t.bg);

  // Title
  tft.setTextColor(t.accent);
  tft.setTextSize(2);
  tft.setCursor(50, 30);
  tft.print("Listening");

  // Waveform bars
  unsigned long now = millis();
  int bars = 10;
  int bar_w = 14, gap = 4;
  int total_w = bars * (bar_w + gap) - gap;
  int start_x = (LCD_WIDTH - total_w) / 2;
  int base_y = 160;
  int max_h = 80;

  for (int i = 0; i < bars; i++) {
    float phase = (float)now / 300.0f + i * 0.7f;
    float wave = (sinf(phase) + 1.0f) / 2.0f;
    int h = 8 + (int)(wave * (float)audio_level / 255.0f * (float)max_h);
    int x = start_x + i * (bar_w + gap);
    // Gradient: brighter bars in center
    int brightness = 180 + (int)(75.0f * (1.0f - fabsf(i - 4.5f) / 4.5f));
    uint16_t color = RGB565(0, brightness, brightness / 2);
    tft.fillRoundRect(x, base_y - h, bar_w, h, 3, color);
  }
}

// ════════════════════════════════════════════════════════════════
// Processing (thinking dots)
// ════════════════════════════════════════════════════════════════
static void draw_processing() {
  const EmotionTheme& t = THEMES[0];
  tft.fillScreen(t.bg);
  unsigned long elapsed = millis() - state_enter_ms;
  int active = (elapsed / 400) % 3;
  for (int i = 0; i < 3; i++) {
    int r = (i == active) ? 14 : 8;
    uint16_t c = (i == active) ? t.accent : RGB565(40,70,50);
    tft.fillCircle(80 + i * 40, 130, r, c);
  }
}

// ════════════════════════════════════════════════════════════════
// Speaking (face + speech bubble)
// ════════════════════════════════════════════════════════════════
static void draw_speaking() {
  const EmotionTheme& t = THEMES[cur_face < FACE_COUNT ? cur_face : 0];
  tft.fillScreen(t.bg);

  // Draw smaller face in upper area
  draw_eyes(t, blink_state);
  draw_mouth(t);

  // Speech bubble
  if (speech_text[0]) {
    // Bubble background
    tft.fillRoundRect(10, BUBBLE_Y, LCD_WIDTH - 20, 52, 10, RGB565(240,245,240));
    // Triangle pointer
    tft.fillTriangle(100, BUBBLE_Y, 120, BUBBLE_Y - 10, 140, BUBBLE_Y, RGB565(240,245,240));
    // Text
    tft.setTextColor(RGB565(20,30,20));
    tft.setTextSize(1);
    tft.setTextWrap(true);
    tft.setCursor(18, BUBBLE_Y + 8);
    // Wrap text manually to fit bubble width (~35 chars per line)
    int len = strlen(speech_text);
    int pos = 0;
    int line = 0;
    while (pos < len && line < 3) {
      int chunk = min(35, len - pos);
      tft.setCursor(18, BUBBLE_Y + 8 + line * 14);
      char tmp[36];
      strncpy(tmp, speech_text + pos, chunk);
      tmp[chunk] = '\0';
      tft.print(tmp);
      pos += chunk;
      line++;
    }
  }
}

// ════════════════════════════════════════════════════════════════
// Public API
// ════════════════════════════════════════════════════════════════
void display_init() {
  hspi.begin(LCD_PIN_CLK, -1, LCD_PIN_DIN, LCD_PIN_CS);
  tft.init(LCD_WIDTH, LCD_HEIGHT, SPI_MODE0);
  tft.setRotation(0);
  tft.setSPISpeed(40000000);
  tft.fillScreen(RGB565(8,16,10));
  lcd_ready = true;
  state_enter_ms = millis();
  last_emotion_ms = millis();
  needs_redraw = true;
}

void display_set_state(DisplayState state) {
  if (state != cur_state) {
    prev_state = cur_state;
    cur_state = state;
    state_enter_ms = millis();
    needs_redraw = true;
  }
}

void display_show_face(FaceType face) {
  if (face != cur_face) needs_redraw = true;
  cur_face = face;
  last_emotion_ms = millis();
  if (cur_state == DS_IDLE || cur_state == DS_SPEAKING)
    return; // face will be drawn in next update
  cur_state = DS_IDLE;
  state_enter_ms = millis();
  needs_redraw = true;
}

void display_set_status_text(const char* text) {
  const char* incoming = text ? text : "";
  if (strncmp(status_text, incoming, sizeof(status_text) - 1) != 0) needs_redraw = true;
  strncpy(status_text, incoming, sizeof(status_text) - 1);
  status_text[sizeof(status_text) - 1] = '\0';
}

void display_set_speech_text(const char* text) {
  const char* incoming = text ? text : "";
  if (strncmp(speech_text, incoming, sizeof(speech_text) - 1) != 0) needs_redraw = true;
  strncpy(speech_text, incoming, sizeof(speech_text) - 1);
  speech_text[sizeof(speech_text) - 1] = '\0';
}

void display_set_audio_level(uint8_t level) {
  audio_level = level;
}

void display_update() {
  if (!lcd_ready) return;
  unsigned long now = millis();
  if (now - last_draw_ms < DRAW_MS) return;
  last_draw_ms = now;

  // Blink timer
  unsigned long blink_interval = blink_state ? 150 : (unsigned long)random(IDLE_BLINK_MIN_MS, IDLE_BLINK_MAX_MS);
  if (now - last_blink_ms > blink_interval) {
    blink_state = !blink_state;
    last_blink_ms = now;
    needs_redraw = true;
  }

  // Gaze shift (idle/speaking only)
  if ((cur_state == DS_IDLE || cur_state == DS_SPEAKING) && cur_face == FACE_NEUTRAL) {
    if (now - last_gaze_ms > IDLE_GAZE_INTERVAL_MS) {
      gaze_x = random(-6, 7);
      gaze_y = random(-3, 4);
      last_gaze_ms = now;
      needs_redraw = true;
    }
  } else if (gaze_x != 0 || gaze_y != 0) {
    gaze_x = 0; gaze_y = 0;
    needs_redraw = true;
  }

  // Emotion decay
  if (cur_state == DS_IDLE && cur_face != FACE_NEUTRAL && (now - last_emotion_ms > EMOTION_DECAY_INTERVAL_MS)) {
    cur_face = FACE_NEUTRAL;
    status_text[0] = '\0';
    needs_redraw = true;
  }

  switch (cur_state) {
    // millis()-driven animations: every frame differs, so always repaint.
    case DS_BOOT:       draw_boot(); break;
    case DS_CONNECTING: draw_connecting(); break;
    case DS_LISTENING:  draw_listening(); break;
    case DS_PROCESSING: draw_processing(); break;
    // Event-driven screens: repaint only on a real change.
    case DS_IDLE:       if (needs_redraw) draw_face(); break;
    case DS_SPEAKING:   if (needs_redraw) draw_speaking(); break;
  }
  needs_redraw = false;
}

void display_clear() {
  if (!lcd_ready) return;
  tft.fillScreen(0);
  needs_redraw = true;
}

#else // CCOLI_HAS_ST7789 == 0 (library not installed)

void display_init() {}
void display_set_state(DisplayState) {}
void display_show_face(FaceType) {}
void display_set_status_text(const char*) {}
void display_set_speech_text(const char*) {}
void display_set_audio_level(uint8_t) {}
void display_update() {}
void display_clear() {}

#endif // CCOLI_HAS_ST7789

// ════════════════════════════════════════════════════════════════
// SSD1306 OLED implementation (DISPLAY_TYPE == 1)
// ════════════════════════════════════════════════════════════════
#elif DISPLAY_TYPE == 1

#if defined(__has_include) && __has_include(<Adafruit_SSD1306.h>)
  #include <Wire.h>
  #include <Adafruit_SSD1306.h>
  #define CCOLI_HAS_SSD1306 1
#else
  #define CCOLI_HAS_SSD1306 0
#endif

#if CCOLI_HAS_SSD1306

Adafruit_SSD1306 display(DISPLAY_WIDTH, DISPLAY_HEIGHT, &Wire, -1);
static bool display_ready = false;
static FaceType current_face = FACE_NEUTRAL;
static char status_text_oled[32] = "";
static unsigned long last_blink_ms_oled = 0;
static bool blink_state_oled = false;
static int gaze_ox = 0, gaze_oy = 0;
static unsigned long last_gaze_ms_oled = 0;
static unsigned long last_emotion_ms_oled = 0;
static unsigned long last_draw_ms_oled = 0;

static int olx() { return 40 + gaze_ox; }
static int oly() { return 22 + gaze_oy; }
static int orx() { return 88 + gaze_ox; }
static int ory() { return 22 + gaze_oy; }

void display_init() {
  Wire.begin(DISPLAY_SDA_PIN, DISPLAY_SCL_PIN);
  display_ready = display.begin(SSD1306_SWITCHCAPVCC, DISPLAY_I2C_ADDR);
  if (display_ready) { display.clearDisplay(); display.setTextColor(SSD1306_WHITE); display.display(); }
  last_emotion_ms_oled = millis();
}

void display_set_state(DisplayState) {} // no-op for OLED

void display_show_face(FaceType face) {
  current_face = face;
  last_emotion_ms_oled = millis();
  status_text_oled[0] = '\0';
}

void display_set_status_text(const char* text) {
  strncpy(status_text_oled, text ? text : "", sizeof(status_text_oled) - 1);
  status_text_oled[sizeof(status_text_oled) - 1] = '\0';
}

void display_set_speech_text(const char*) {} // no-op
void display_set_audio_level(uint8_t) {} // no-op

void display_update() {
  if (!display_ready) return;
  unsigned long now = millis();
  if (now - last_draw_ms_oled < 66) return;
  last_draw_ms_oled = now;

  if (now - last_blink_ms_oled > (blink_state_oled ? 150UL : (unsigned long)random(3000,5000))) {
    blink_state_oled = !blink_state_oled;
    last_blink_ms_oled = now;
  }
  if (current_face == FACE_NEUTRAL && now - last_gaze_ms_oled > 8000) {
    gaze_ox = random(-4,5); gaze_oy = random(-2,3); last_gaze_ms_oled = now;
  }
  if (current_face != FACE_NEUTRAL) { gaze_ox = 0; gaze_oy = 0; }
  if (current_face != FACE_NEUTRAL && (now - last_emotion_ms_oled > EMOTION_DECAY_INTERVAL_MS)) {
    current_face = FACE_NEUTRAL; status_text_oled[0] = '\0';
  }

  display.clearDisplay();
  // Simple eyes
  if (blink_state_oled) {
    display.drawLine(olx()-8,oly(),olx()+8,oly(),SSD1306_WHITE);
    display.drawLine(orx()-8,ory(),orx()+8,ory(),SSD1306_WHITE);
  } else {
    display.fillCircle(olx(),oly(),8,SSD1306_WHITE);
    display.fillCircle(orx(),ory(),8,SSD1306_WHITE);
  }
  // Simple mouth
  display.drawCircle(64,48,3,SSD1306_WHITE);
  if (status_text_oled[0]) {
    display.setTextSize(1); display.setCursor(0,56); display.print(status_text_oled);
  }
  display.display();
}

void display_clear() { if (display_ready) { display.clearDisplay(); display.display(); } }

#else // no SSD1306 library
void display_init() {}
void display_set_state(DisplayState) {}
void display_show_face(FaceType) {}
void display_set_status_text(const char*) {}
void display_set_speech_text(const char*) {}
void display_set_audio_level(uint8_t) {}
void display_update() {}
void display_clear() {}
#endif

// ════════════════════════════════════════════════════════════════
// No display (DISPLAY_TYPE == 0)
// ════════════════════════════════════════════════════════════════
#else

void display_init() {}
void display_set_state(DisplayState) {}
void display_show_face(FaceType) {}
void display_set_status_text(const char*) {}
void display_set_speech_text(const char*) {}
void display_set_audio_level(uint8_t) {}
void display_update() {}
void display_clear() {}

#endif
