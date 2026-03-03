# LLM_Aduino

## 문서 우선순위
- 제품 요구사항/범위 기준: `docs/PRD.md`
- Codex 개발 운영 규칙: `docs/PROJECT_RULES_CODEX.md`
- 빠른 실행 가이드: `README.md`, `QUICKSTART.md`
- Docker 설치/구동/테스트 가이드: `docs/DOCKER_SETUP_AND_RUN.md`

## 개요
- M5Stack Atom Echo(ESP32)로 음성(VAD 포함) 스트리밍 → PC 서버 → Whisper STT → 간단한 동작 명령(JSON) 응답.
- ESP32는 내부 마이크로 16kHz 오디오를 서버에 보내고, 서버가 인식 결과에 따라 서보 동작 명령(예: 각도 설정)을 내려줍니다.

## 프로젝트 구조
- `arduino/atom_echo_m5stack_esp32_ino/atom_echo_m5stack_esp32_ino.ino`
  - M5Unified, WiFi, 간이 VAD, 20ms 프레임(320샘플) 전송, 200ms 프리롤, 서버 keepalive(PING), 서버의 CMD JSON 수신/로그.
- `server/stt.py`
  - TCP 서버(포트 5001), faster-whisper(`tiny`)로 한국어 STT, 음성 품질 검증/정규화, 텍스트 기반 액션 파서, ESP32에 JSON CMD 전송.
- `arduino/atom_echo_m5stack_esp32_ino/Blink.txt`
  - 참고용 단일 라인 파일.

## 준비물
- M5Stack Atom Echo(ESP32) + Arduino IDE (또는 PlatformIO)
  - 라이브러리: `M5Unified`, `WiFi`(기본), `math.h` 등 표준
- PC/서버 측
  - Python 3.9+ 권장
  - `pip install faster-whisper numpy` (CUDA 사용 시 PyTorch/CUDA 환경 필요)

## Arduino 설정 및 빌드
1) `arduino/atom_echo_m5stack_esp32_ino/atom_echo_m5stack_esp32_ino.ino`에서 Wi-Fi/서버 정보 수정
   ```cpp
   const char* SSID = "YOUR_WIFI";
   const char* PASS = "YOUR_PASS";
   const char* SERVER_IP = "PC_IP";
   const uint16_t SERVER_PORT = 5001;
   ```
2) 보드: ESP32 계열(M5Stack Atom 선택), 시리얼 모니터 115200bps.
3) 업로드 후 전원/리셋. 시리얼에서 `WiFi connected`, `server connected`를 확인합니다.

## 서버 실행(stt.py)
```bash
cd server
pip install -r requirements.txt  # 없을 경우: pip install faster-whisper numpy
python stt.py
```
- 기본 포트 `5001`, 모든 인터페이스(`0.0.0.0`) 바인드.
- 첫 연결 시 모델을 GPU(`cuda`)에 로드, 실패하면 CPU int8로 자동 폴백.
- 음성 조각 저장: `wav_logs/` (자동 생성).

## 동작 흐름
1) ESP32: VAD로 말 시작 감지 → `0x01` START + 프리롤+프레임(`0x02`) → 침묵/시간 경계에서 `0x03` END.
2) 서버: 수신 PCM을 정규화/절삭 후 Whisper STT → 텍스트→액션 파싱 → `0x11` JSON CMD 송신.
3) ESP32: 수신된 JSON을 로그로 출력(현재는 로봇/서보 동작 부분 미구현, 추후 action별 처리 추가).

## 명령 파서(예시)
- "가운데/중앙/센터": SERVO_SET angle=90 (기본)
- "왼쪽"/"오른쪽": SERVO_SET angle=30/150 (기본)
- "올려/내려": 현재 각도 ±20 (또는 텍스트 내 숫자)
- 숫자만 포함 시 해당 각도로 SERVO_SET, 범위는 0~180으로 clamp
- 인식 불확실 또는 무음: NOOP (또는 WIGGLE, `UNSURE_POLICY`로 설정)

## 네트워크/프로토콜 참고
- 패킷: 1바이트 타입 + 2바이트 길이(LE) + payload
  - ESP32→PC: `0x01` START, `0x02` AUDIO(PCM16LE mono 16k), `0x03` END, `0x10` PING
  - PC→ESP32: `0x11` JSON CMD (`{"action": "...", "angle": int?, "sid": int, "meaningful": bool, "recognized": bool}`)
- 연결 유지: ESP32가 3초마다 PING. 서버는 필요 시 PONG 전송 가능(현재 미사용).

## 자주 겪는 문제
- Wi-Fi 미연결/서버 미접속: SSID/PASS 확인, PC 방화벽에서 TCP 5001 허용, `SERVER_IP`를 같은 네트워크 IP로 설정.
- STT 속도: GPU 권장. CPU만 사용할 경우 `MODEL_SIZE`를 `tiny` 유지 또는 더 작은 모델 사용.
- 음성 감지 민감도: `VAD_ON_MUL`, `VAD_OFF_MUL`, `MIN_TALK_MS`, `SILENCE_END_MS`, `MAX_TALK_MS`를 조정.

## 다음 작업 아이디어
- ESP32 측 action 처리(서보 제어, LED 피드백 등) 구현.
- JSON schema 확장(여러 액션, 파라미터 추가) 및 에러 핸들링.
- STT 후 TTS/응답 음성 재생 파이프라인 추가.
