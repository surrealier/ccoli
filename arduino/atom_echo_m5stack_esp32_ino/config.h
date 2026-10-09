// Shared firmware configuration for ccoli.
// Credential values (CONNECTION_MODE/SSID/PASS/SERVER_IP/SERVER_PORT) come
// from `device_secrets.h` when present, otherwise the sketch falls back to
// default wired-mode values.

#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

// Credentials / server target from device_secrets.h
extern const char* CONNECTION_MODE;
extern const char* SSID;
extern const char* PASS;
extern const char* SERVER_IP;
extern const uint16_t SERVER_PORT;

// USB serial transport defaults
// Keep wired USB at 115200 for CP210x stability; wired audio is transcoded to fit.
#define SERIAL_BAUD_RATE 115200
#define WIRED_PING_INTERVAL_MS 1000
#define PROTOCOL_PEER_TIMEOUT_MS 5000
#define WIRED_TTS_SAMPLE_RATE 8000

// ── Pin assignments (Atom Echo) ──
// Predefined (DO NOT REUSE): G19, G22 (I2S SPK), G23, G33 (PDM MIC)
// Internal: G27 (RGB LED), G39 (Button), G12 (IR TX)
//
// Only G21/G25 (side header) and G26/G32 (Grove) are free for peripherals, so
// every optional add-on competes for the same four pins:
//
//   DISPLAY_TYPE 0 (none)         G21/G25/G26/G32 free -> local servos on G26/G32
//   DISPLAY_TYPE 1 (SSD1306 I2C)  G25=SDA G21=SCL      -> local servos on G26/G32
//   DISPLAY_TYPE 2 (ST7789V2 SPI) G25/G21/G26/G32      -> no pins left for servos
//   ROBOT_BRIDGE_ENABLED          G26=TX G32=RX        -> servos live on companion
//
// docs/ROBOT_MODE_WAVESHARE_PRD.md puts the ST7789V2 panel and the SG90s on a
// companion controller, so the Atom Echo build defaults to no local display and
// keeps the Grove pins available for the two-servo direct build.
// Display type: 0=none, 1=SSD1306 OLED (I2C), 2=ST7789V2 color LCD (SPI)
// Overridable from the build so CI can compile every peripheral combination:
//   arduino-cli compile --build-property build.extra_flags=-DDISPLAY_TYPE=1
#ifndef DISPLAY_TYPE
  #define DISPLAY_TYPE 0
#endif

// SSD1306 OLED (I2C) — only when DISPLAY_TYPE == 1
#define DISPLAY_SDA_PIN 25
#define DISPLAY_SCL_PIN 21
#define DISPLAY_WIDTH   128
#define DISPLAY_HEIGHT  64
#define DISPLAY_I2C_ADDR 0x3C

// ST7789V2 Color LCD (SPI) — only when DISPLAY_TYPE == 2
// Waveshare 1.69" 240x280: DIN=G25 CLK=G21 CS=G26 DC=G32 RST=3V3 BL=3V3
#define LCD_PIN_DIN  25
#define LCD_PIN_CLK  21
#define LCD_PIN_CS   26
#define LCD_PIN_DC   32
#define LCD_WIDTH    240
#define LCD_HEIGHT   280

// Leased robot-control v1 companion bridge
// Disabled by default; both direct and companion outputs require explicit arm.
// When enabled, the Grove pins are reassigned as UART TX/RX for a companion
// controller and local servo outputs are disabled.
#ifndef ROBOT_BRIDGE_ENABLED
  #define ROBOT_BRIDGE_ENABLED 0
#endif
#define ROBOT_BRIDGE_UART_PORT 1
#define ROBOT_BRIDGE_BAUD 115200
#define ROBOT_BRIDGE_TX_PIN 26
#define ROBOT_BRIDGE_RX_PIN 32

// The SPI panel needs all four free pins, so it cannot share a board with the
// companion UART bridge. Fail the build instead of letting two drivers fight
// over G26/G32 at runtime.
#if ROBOT_BRIDGE_ENABLED && (DISPLAY_TYPE == 2)
  #error "ROBOT_BRIDGE_ENABLED and DISPLAY_TYPE==2 both drive G26/G32. Keep the ST7789V2 panel on the companion controller."
#endif

// Servo motors — Grove HY2.0-4P port.
// Available only while nothing else has claimed G26/G32.
#if ROBOT_BRIDGE_ENABLED || (DISPLAY_TYPE == 2)
  #define LOCAL_SERVO_ENABLED 0
  #define SERVO_PIN_PITCH -1
  #define SERVO_PIN_TILT  -1
#else
  #define LOCAL_SERVO_ENABLED 1
  #define SERVO_PIN_PITCH 26   // Servo #1: nod (up/down)
  #define SERVO_PIN_TILT  32   // Servo #2: tilt (left/right)
#endif
#define SERVO_MIN_ANGLE 0
#define SERVO_MAX_ANGLE 180
#define SERVO_CENTER_ANGLE 90

// Backward compat alias
#define SERVO_PIN SERVO_PIN_PITCH

// VAD (Voice Activity Detection) settings
#define VAD_NOISE_ALPHA 0.995f
#define VAD_ON_MULTIPLIER 3.0f
#define VAD_OFF_MULTIPLIER 1.8f
#define VAD_MIN_TALK_MS 500
#define VAD_SILENCE_END_MS 350
#define VAD_MAX_TALK_MS 8000
#define VAD_INITIAL_NOISE_FLOOR 120.0f

// Audio settings
#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_FRAME_SIZE 320
#define PREROLL_MS 200
#define AUDIO_RING_BUFFER_SIZE 16384
#define ENABLE_BUTTON_INTERRUPT 1

// Connection settings
#define WIFI_RECONNECT_INTERVAL_MS 5000
#define PING_INTERVAL_MS 3000

// LED colors (RGB)
#define LED_COLOR_CONNECTING_R 255
#define LED_COLOR_CONNECTING_G 0
#define LED_COLOR_CONNECTING_B 0

#define LED_COLOR_IDLE_R 100
#define LED_COLOR_IDLE_G 255
#define LED_COLOR_IDLE_B 100

#define LED_COLOR_RECORDING_R 0
#define LED_COLOR_RECORDING_G 255
#define LED_COLOR_RECORDING_B 0

#define LED_COLOR_PLAYING_R 255
#define LED_COLOR_PLAYING_G 255
#define LED_COLOR_PLAYING_B 0

// Largest payload the device accepts in one frame (bytes).
// Must be >= the server's DEVICE_MAX_PACKET_PAYLOAD in server/src/protocol.py.
// Longer frames are treated as serial noise and dropped during resync.
#define RX_MAX_PACKET_PAYLOAD 2048

// Idle animation settings
#define IDLE_BLINK_MIN_MS 3000
#define IDLE_BLINK_MAX_MS 5000
#define IDLE_GAZE_INTERVAL_MS 8000

// Emotion decay
#define EMOTION_DECAY_INTERVAL_MS 30000

#endif  // CONFIG_H
