# ccoli Quick Start

## 1. Install

```bash
pip install -r server/requirements.txt
pip install -e .
```

## 2. Configure project (official command)

```bash
ccoli config wifi <WiFi Name> password <password> port <port>
```

Example:

```bash
ccoli config wifi MyHomeWiFi password MySecretPass port 5001
```

Alias (`colli`) is also supported:

```bash
colli config wifi MyHomeWiFi password MySecretPass port 5001
```

After running, check `arduino/atom_echo_m5stack_esp32_ino/device_secrets.h` and set:
- `SERVER_IP` to your PC/server LAN IP

## 3. Start server

```bash
ccoli start
```

Optional temporary port override:

```bash
ccoli start --port 5002
```

## 4. Upload firmware

Open and upload:
- `arduino/atom_echo_m5stack_esp32_ino/atom_echo_m5stack_esp32_ino.ino`

Required file before build:
- `arduino/atom_echo_m5stack_esp32_ino/device_secrets.h`

## 5. Current mode support

- Agent mode: available
- Robot mode: not available yet (Servo + Display integration in progress)



## References

- Product requirements: `docs/PRD.md`
- Execution planning: `docs/AGENT_FEATURE_PLANNING.md`
