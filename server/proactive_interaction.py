# ============================================================
# proactive_interaction.py — 프로액티브 상호작용 시스템
# ============================================================
# 역할: 사용자가 말을 걸지 않아도 AI가 먼저 대화를 시작.
#       시간대별 인사, 침묵 후 관심 표현, 활동 제안, 기분 체크.
#
# 트리거 조건: 마지막 상호작용 후 interval 경과 + 활동 시간대
# 수면 모드: 사용자 요청 시 다음날 아침까지 비활성화
# 메시지 반복 방지: recent_messages 트래킹
# ============================================================
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional, List

log = logging.getLogger("proactive")

class ProactiveInteraction:
    """
    프로액티브 상호작용 시스템
    사용자와의 상호작용 없이 자발적으로 말을 거는 기능
    """
    
    # 시간대별 인사말 (24시간 형식)
    TIME_GREETINGS = {
        (5, 9): ["좋은 아침이에요!", "안녕하세요! 잘 주무셨나요?", "상쾌한 아침이네요!"],
        (9, 12): ["좋은 오전이에요!", "오전 시간 잘 보내고 계세요?"],
        (12, 14): ["점심 시간이네요!", "맛있는 점심 드셨나요?", "점심은 드셨어요?"],
        (14, 18): ["오후 시간이에요!", "오후도 활기차게 보내세요!"],
        (18, 21): ["저녁 시간이네요!", "저녁은 드셨나요?", "하루 어떠셨어요?"],
        (21, 24): ["밤 시간이에요!", "오늘 하루 수고하셨어요!", "편안한 밤 되세요!"],
        (0, 5): ["늦은 밤이네요!", "아직 안 주무셨어요?", "일찍 주무시는 게 좋아요!"]
    }
    
    # 침묵 시간대별 멘트
    IDLE_MESSAGES = [
        "심심해요. 뭐 하세요?",
        "저 여기 있어요!",
        "궁금한 거 있으면 물어보세요!",
        "오늘 날씨 궁금하지 않으세요?",
        "뭔가 도와드릴 일 없나요?",
        "이야기하고 싶어요!",
        "제가 할 수 있는 게 많아요!",
        "혹시 필요한 게 있으신가요?"
    ]
    
    # 활동 제안
    ACTIVITY_SUGGESTIONS = [
        "날씨가 좋은데 산책은 어때요?",
        "스트레칭 한 번 하시는 건 어떨까요?",
        "잠깐 휴식 시간을 가져보세요!",
        "물 한 잔 마시는 건 어떨까요?",
        "음악 들으시는 건 어때요?",
        "창문 열고 환기해보시는 건 어떨까요?"
    ]
    
    # 기분 체크
    MOOD_CHECKS = [
        "기분이 어떠세요?",
        "오늘 컨디션은 괜찮으세요?",
        "즐거운 하루 보내고 계세요?",
        "혹시 힘든 일 있으세요?",
        "무슨 일 있으세요?"
    ]
    
    def __init__(self, enabled: bool = True, interval: int = 1800):
        """
        Args:
            enabled: 프로액티브 기능 활성화 여부
            interval: 메시지 간격 (초)
        """
        self.enabled = enabled
        self.interval = interval  # seconds
        self.last_interaction = time.time()
        self.last_proactive = time.time()
        self.proactive_count = 0
        
        # 이미 말한 메시지 트래킹 (반복 방지)
        self.recent_messages = []
        self.max_recent = 5
        
        # 수면 모드 설정
        self.sleep_mode = False
        self.sleep_until = None  # 다음날 아침까지 잠
        self.active_hours = (11, 23)  # 오전 11시 ~ 밤 11시
    
    def update_interaction(self):
        """사용자 상호작용 시간 업데이트"""
        self.last_interaction = time.time()
    
    def should_trigger(self) -> bool:
        """프로액티브 메시지를 보내야 하는지 확인"""
        if not self.enabled:
            return False
        
        # 수면 모드 확인
        if self.sleep_mode:
            # 다음날 아침이 되면 자동으로 깨어남
            if self.sleep_until and datetime.now() >= self.sleep_until:
                log.info("☀️ 수면 모드 해제 - 아침이 되었습니다")
                self.sleep_mode = False
                self.sleep_until = None
            else:
                return False
        
        # 활동 시간 확인 (오전 11시 ~ 밤 11시)
        current_hour = datetime.now().hour
        start_hour, end_hour = self.active_hours
        if not (start_hour <= current_hour < end_hour):
            return False
        
        now = time.time()
        time_since_last_interaction = now - self.last_interaction
        time_since_last_proactive = now - self.last_proactive
        
        # 마지막 상호작용 이후 interval 시간이 지났고,
        # 마지막 프로액티브 메시지 이후 최소 interval/2 시간이 지났으면 트리거
        if (time_since_last_interaction >= self.interval and 
            time_since_last_proactive >= self.interval / 2):
            return True
        
        return False
    
    def get_proactive_message(self, current_emotion: str = "neutral", 
                              important_memories: List[str] = None) -> Optional[str]:
        """
        프로액티브 메시지 생성
        Returns: message string or None
        """
        if not self.should_trigger():
            return None
        
        # 현재 시간 확인
        current_hour = datetime.now().hour
        
        # 메시지 타입 선택 (가중치)
        message_types = []
        weights = []
        
        # 시간대별 인사말 (30%)
        time_greeting = self._get_time_greeting(current_hour)
        if time_greeting:
            message_types.append(("time_greeting", time_greeting))
            weights.append(30)
        
        # 침묵 메시지 (30%)
        message_types.append(("idle", self.IDLE_MESSAGES))
        weights.append(30)
        
        # 활동 제안 (20%)
        message_types.append(("activity", self.ACTIVITY_SUGGESTIONS))
        weights.append(20)
        
        # 기분 체크 (20%)
        message_types.append(("mood", self.MOOD_CHECKS))
        weights.append(20)
        
        # 가중치 기반 랜덤 선택
        total = sum(weights)
        rand = random.uniform(0, total)
        cumulative = 0
        
        selected_type = None
        selected_messages = None
        
        for (msg_type, messages), weight in zip(message_types, weights):
            cumulative += weight
            if rand <= cumulative:
                selected_type = msg_type
                selected_messages = messages
                break
        
        if not selected_messages:
            return None
        
        # 최근에 사용하지 않은 메시지 선택
        available_messages = [msg for msg in selected_messages 
                              if msg not in self.recent_messages]
        
        if not available_messages:
            # 모두 사용했으면 최근 메시지 초기화
            self.recent_messages = []
            available_messages = selected_messages
        
        message = random.choice(available_messages)
        
        # 메시지 기록
        self.recent_messages.append(message)
        if len(self.recent_messages) > self.max_recent:
            self.recent_messages.pop(0)
        
        # 프로액티브 카운터 업데이트
        self.last_proactive = time.time()
        self.proactive_count += 1
        
        log.info(f"Proactive message triggered (type: {selected_type}): {message}")
        return message
    
    def _get_time_greeting(self, hour: int) -> Optional[List[str]]:
        """현재 시간에 맞는 인사말 목록 반환"""
        for (start, end), greetings in self.TIME_GREETINGS.items():
            if start <= hour < end:
                return greetings
        return None
    
    def check_birthday_reminder(self, important_memories: List[str]) -> Optional[str]:
        """
        생일/기념일 리마인더 확인
        important_memories에서 날짜 관련 정보 추출
        """
        # 간단한 구현: 메모리에서 "생일", "기념일" 키워드 찾기
        today = datetime.now()
        today_str = today.strftime("%m월 %d일")
        
        for memory in important_memories or []:
            if "생일" in memory and today_str in memory:
                return f"오늘은 특별한 날이네요! {memory}"
            elif "기념일" in memory and today_str in memory:
                return f"기념일을 잊지 마세요! {memory}"
        
        return None
    
    def enable(self):
        """프로액티브 기능 활성화"""
        self.enabled = True
        log.info("Proactive interaction enabled")
    
    def disable(self):
        """프로액티브 기능 비활성화"""
        self.enabled = False
        log.info("Proactive interaction disabled")
    
    def set_interval(self, seconds: int):
        """프로액티브 메시지 간격 설정"""
        self.interval = seconds
        log.info(f"Proactive interval set to {seconds} seconds")
    
    def enter_sleep_mode(self) -> str:
        """수면 모드 진입"""
        self.sleep_mode = True
        # 다음날 아침 11시로 설정
        tomorrow = datetime.now() + timedelta(days=1)
        self.sleep_until = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        
        log.info(f"😴 수면 모드 진입 - {self.sleep_until.strftime('%Y-%m-%d %H:%M')}까지")
        return f"알겠습니다. {self.sleep_until.strftime('%내일 오전 %H시')}까지 조용히 있을게요. 편안한 밤 되세요!"
    
    def pause_temporarily(self, hours: int = 1) -> str:
        """일시적으로 멈춤 (지정 시간 동안)"""
        self.sleep_mode = True
        self.sleep_until = datetime.now() + timedelta(hours=hours)
        
        log.info(f"⏸️ 일시 정지 - {self.sleep_until.strftime('%Y-%m-%d %H:%M')}까지")
        return f"알겠습니다. {hours}시간 동안 조용히 있을게요."
    
    def wake_up(self) -> str:
        """수면 모드 해제"""
        if not self.sleep_mode:
            return "이미 깨어있어요!"
        
        self.sleep_mode = False
        self.sleep_until = None
        log.info("☀️ 수면 모드 해제 - 사용자 요청")
        return "일어났어요! 다시 활동할게요!"
    
    def get_stats(self) -> dict:
        """프로액티브 통계 반환"""
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "proactive_count": self.proactive_count,
            "time_since_last_interaction": time.time() - self.last_interaction,
            "time_since_last_proactive": time.time() - self.last_proactive,
            "sleep_mode": self.sleep_mode,
            "sleep_until": self.sleep_until.isoformat() if self.sleep_until else None,
            "active_hours": self.active_hours
        }
