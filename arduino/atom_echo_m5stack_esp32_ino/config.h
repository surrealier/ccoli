// Shared firmware configuration for ccoli.
// Credential values (SSID/PASS/SERVER_IP/SERVER_PORT) are defined in
// `device_secrets.h` and declared here as extern symbols.

#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

// Credentials / server target from device_secrets.h
extern const char* SSID;
extern const char* PASS;
extern const char* SERVER_IP;
extern const uint16_t SERVER_PORT;

// ── Pin assignments (Atom Echo) ──
// Predefined (DO NOT REUSE): G19, G22 (I2S SPK), G23, G33 (PDM MIC)
// Internal: G27 (RGB LED), G39 (Button), G12 (IR TX)

// OLED Display (SSD1306 I2C) — right-side header pins
#define DISPLAY_SDA_PIN 25
#define DISPLAY_SCL_PIN 21
#define DISPLAY_WIDTH   128
#define DISPLAY_HEIGHT  64
#define DISPLAY_I2C_ADDR 0x3C

// Servo motors — Grove HY2.0-4P port
#define SERVO_PIN_PITCH 26   // Servo #1: nod (up/down)
#define SERVO_PIN_TILT  32   // Servo #2: tilt (left/right)
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
#define AUDIO_RING_BUFFER_SIZE 81920
#define ENABLE_BUTTON_INTERRUPT 1

// Connection settings
#define WIFI_RECONNECT_INTERVAL_MS 5000
#define PING_INTERVAL_MS 3000

// LED colors (RGB)
#define LED_COLOR_CONNECTING_R 255
#define LED_COLOR_CONNECTING_G 0
#define LED_COLOR_CONNECTING_B 0

#define LED_COLOR_IDLE_R 0
#define LED_COLOR_IDLE_G 0
#define LED_COLOR_IDLE_B 255

#define LED_COLOR_RECORDING_R 0
#define LED_COLOR_RECORDING_G 255
#define LED_COLOR_RECORDING_B 0

#define LED_COLOR_PLAYING_R 255
#define LED_COLOR_PLAYING_G 255
#define LED_COLOR_PLAYING_B 0

// Protocol receive safety cap (bytes)
#define RX_AUDIO_MAX_ALLOC 16384

// Idle animation settings
#define IDLE_BLINK_MIN_MS 3000
#define IDLE_BLINK_MAX_MS 5000
#define IDLE_GAZE_INTERVAL_MS 8000

// Emotion decay
#define EMOTION_DECAY_INTERVAL_MS 30000

#endif  // CONFIG_H
