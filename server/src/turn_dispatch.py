"""Use one dialogue call; dispatch explicit motor intent through the verified core."""
from .dialogue_policy import phrase, resolve_language
from .robotics.models import RoboticsError


def generate_turn_response(agent, robotics, text: str, language: str | None = None,
                           speaker_id: str | None = None) -> tuple[str, str]:
    if robotics is not None:
        chosen = language or resolve_language(text, configured=agent.describe_dialogue().get('language','auto'))
        try:
            result = robotics.handle_text(text)
        except RoboticsError:
            return phrase(chosen,
                '장치 연결과 동작 범위를 설정하고 동작 허용을 눌러 주세요.',
                'Connect the device, set its movement range, and enable movement.',
                '请连接设备、设置运动范围，然后允许运动。',
                '機器を接続し、動作範囲を設定して動作を許可してください。',
                'Conecta el dispositivo, configura su rango y habilita el movimiento.'), 'robot_setup_required'
        if result is not None:
            return phrase(chosen,
                '동작 요청을 보냈어요. 장치 결과를 확인할게요.',
                'I sent the action request. Check the device result.',
                '已发送动作请求。请查看设备结果。',
                '動作を要求しました。機器の結果を確認してください。',
                'Envié la solicitud. Comprueba el resultado del dispositivo.'), 'robot_action'
    options = {'language':language} if language is not None else {}
    return agent.generate_response(text, speaker_id=speaker_id, **options)
