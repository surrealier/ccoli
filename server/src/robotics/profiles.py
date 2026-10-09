"""Capability-bound, button-friendly setup recipes; no implicit motor activation."""
from __future__ import annotations
import copy
from .models import Capabilities, RoboticsError

PROFILES = {
    'voice_only': dict(name='음성만 사용', controller=None, servo_count=0, display=None,
        need_parts=['Atom Echo', 'USB 데이터 케이블'], wiring=['PC와 USB로 연결'],
        power=['USB 전원'], setup_steps=['연결', '대화 시작']),
    'direct_1': dict(name='작은 모터 1개', controller='legacy_direct', servo_count=1, display='none',
        need_parts=['SG90 1개', '외부 5V 전원', '연결선'],
        wiring=['서보 0 신호 → G26', '서보 전원 → 외부 5V', '서보 GND ↔ Atom GND'],
        power=['모터는 외부 5V로 공급', 'USB 전원에 모터 전원을 묶지 않기'],
        setup_steps=['보드 발견', '배선 확인', '범위 설정', 'arm', '작은 움직임 시험']),
    'direct_2': dict(name='작은 모터 2개', controller='legacy_direct', servo_count=2, display='none',
        need_parts=['SG90 2개', '외부 5V 전원', '연결선'],
        wiring=['서보 0 신호 → G26', '서보 1 신호 → G32', '외부 5V 공급 + 공통 GND'],
        power=['모터는 외부 5V로 공급'],
        setup_steps=['보드 발견', '배선 확인', '각 채널 범위 설정', 'arm', '채널별 작은 시험']),
    'direct_2_oled': dict(name='모터 2개와 작은 화면', controller='legacy_direct', servo_count=2,
        display='ssd1306', need_parts=['SG90 2개', 'SSD1306 OLED', '외부 5V 전원'],
        wiring=['OLED SDA → G25, SCL → G21', '서보 신호 → G26/G32', '공통 GND'],
        power=['OLED 전압은 제품 사양 확인', '모터는 외부 5V'],
        setup_steps=['보드 발견', 'OLED 펌웨어 확인', '배선', '범위 설정', '작은 시험']),
    'companion_4_lcd': dict(name='모터 최대 4개와 컬러 화면', controller='companion_uart',
        servo_count=4, display='st7789v2_240x280',
        need_parts=['보조 ESP32 컨트롤러', 'SG90 최대 4개', 'Waveshare LCD', '외부 5V 전원'],
        wiring=['Atom G26 → 보조보드 RX', 'Atom G32 → 보조보드 TX', '보드 간 공통 GND',
                'LCD/모터는 보조보드 연결 안내 따라 배선'],
        power=['LCD 3.3V 전원과 3.3V 로직', '모터 외부 5V 2~3A'],
        setup_steps=['보조보드 펌웨어', '보드 발견', '배선 확인', '각 채널 범위 설정', '작은 시험']),
    'camera': dict(name='카메라 관측', controller=None, servo_count=0, display=None,
        need_parts=['USB 카메라 또는 지원 카메라'], wiring=['카메라를 PC에 연결'],
        power=['카메라 제품 사양 확인'], setup_steps=['카메라 선택', '미리보기', '관측 확인']),
    'sensor': dict(name='센서로 상태 확인', controller=None, servo_count=0, display=None,
        need_parts=['지원 센서와 연결 어댑터'], wiring=['센서 제품 연결 안내 확인'],
        power=['센서 전압 확인'], setup_steps=['센서 선택', '현재 값 확인', '조건 작업 설정']),
    'so101': dict(name='SO-101 소형 로봇 팔', controller='so101', servo_count=6, display='none',
        need_parts=['SO-101 follower', '공식 전원/USB 어댑터', '카메라', '작업 공간'],
        wiring=['공식 SO-101 조립·연결 가이드 사용'], power=['공식 로봇 전원 사용'],
        setup_steps=['선택 SDK 설치', '팔 발견', '공식 캘리브레이션', '저속 teleop',
                     '카메라 관측', '검증된 작업 policy 선택']),
}

def public_profiles() -> list[dict]:
    results = []
    for key, profile in PROFILES.items():
        result = copy.deepcopy(profile)
        result['id'] = key
        result['capability'] = {k: result[k] for k in ('controller', 'servo_count', 'display')}
        result['motion_enabled_by_selection'] = False
        results.append(result)
    return results

def validate_profile(profile_id: str, capabilities: Capabilities) -> dict:
    if not isinstance(profile_id, str) or profile_id not in PROFILES:
        raise RoboticsError('unknown_profile')
    profile = PROFILES[profile_id]
    if profile['controller'] and profile['controller'] != capabilities.controller:
        raise RoboticsError('profile_controller_mismatch')
    if profile_id == 'so101' and (capabilities.feedback_kind != 'measured' or capabilities.servo_count != 6 or not capabilities.joint_order):
        raise RoboticsError('required_capability_missing')
    if profile['servo_count'] > capabilities.servo_count:
        raise RoboticsError('profile_servo_mismatch')
    if profile['display'] and profile['display'] != capabilities.display:
        raise RoboticsError('profile_display_mismatch')
    return copy.deepcopy(profile)