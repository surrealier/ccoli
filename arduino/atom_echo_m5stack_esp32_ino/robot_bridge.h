#ifndef ROBOT_BRIDGE_H
#define ROBOT_BRIDGE_H
#include <Arduino.h>
void robot_bridge_init();
void robot_bridge_update(bool link_available = true);
bool robot_bridge_ready();
bool robot_bridge_enabled();
bool robot_bridge_forward_json(const char* json);
void robot_bridge_set_speech_active(bool active);
#endif
