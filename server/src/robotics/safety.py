"""Current-turn intent and complete numeric validation, independent of model output."""
from __future__ import annotations
import re
from typing import Any
from .models import RoboticsError

# Exact whole-turn forms intentionally exclude arbitrary numbers, quoted text,
# questions, negation, multi-command text, and instructions in a camera image.
_INTENTS = {
    'stop': ['로봇 정지', '로봇 멈춰', '정지', 'stop robot', 'stop the robot',
             '停止机器人', '机器人停止', 'ロボットを停止', 'ロボット停止',
             'detén el robot', 'deten el robot', 'para el robot'],
    'notification_nod': ['고개 끄덕여', '고개 끄덕여줘', 'nod', 'nod please',
                         '点头', '点一下头', 'うなずいて', 'asiente'],
    'farewell_wave': ['손 흔들어', '손 흔들어줘', 'wave', 'wave please', '挥手',
                      '手を振って', 'saluda con la mano'],
    'curious_tilt': ['고개 기울여', 'tilt your head', '歪头', '首をかしげて', 'inclina la cabeza'],
}

def parse_robot_intent(text: Any) -> dict | None:
    if not isinstance(text, str) or len(text) > 160:
        return None
    value = re.sub(r'\s+', ' ', text.strip()).casefold().rstrip('.!。！')
    for op, forms in _INTENTS.items():
        if value in forms:
            return {'op': 'stop'} if op == 'stop' else {'op': 'gesture', 'id': op, 'intensity': .3}
    return None

def require_authorized(value: Any) -> None:
    if value is not True:
        raise RoboticsError('explicit_authorization_required')