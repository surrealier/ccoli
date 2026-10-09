"""Detected language survives STT, reply generation and ordered TTS fallback."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_server_main import srv


@pytest.mark.parametrize('language,text', [('en','Cats purr.'),('zh','今天天气很好'),('ja','天気がいいですね'),('es','Los gatos ronronean.')])
def test_transcription_keeps_detected_turn_language(language, text):
    stt = Mock()
    stt.safe_transcribe.return_value = ([SimpleNamespace(text=text)], SimpleNamespace(language=language))
    agent = Mock()
    agent.describe_dialogue.return_value = {'language':'auto'}
    assert srv._transcribe_turn(stt, [0.1], agent) == (text, language)
    stt.safe_transcribe.assert_called_once_with([0.1])


def test_fixed_language_overrides_stt_detection_and_missing_info_falls_back():
    stt = Mock()
    stt.safe_transcribe.return_value = ([SimpleNamespace(text='hello')], SimpleNamespace(language='en'))
    agent = Mock()
    agent.describe_dialogue.return_value = {'language':'ja'}
    assert srv._transcribe_turn(stt, [], agent) == ('hello','ja')
    agent.describe_dialogue.return_value = {'language':'auto'}
    stt.safe_transcribe.return_value = ([SimpleNamespace(text='Hola')], None)
    assert srv._transcribe_turn(stt, [], agent) == ('Hola','es')


@pytest.mark.parametrize('language', ['ko','en','zh','ja','es'])
@pytest.mark.parametrize('chunks', [1,3])
def test_every_tts_chunk_uses_same_turn_language(language, chunks):
    calls = []
    class Agent:
        def prepare_tts_chunks(self, _text, max_chunks=3):
            return ['one','two','three'][:chunks]
        def text_to_audio(self, text, trim_pad_ms, language=None):
            calls.append((text, language))
            return text.encode()
        def merge_audio_chunks(self, audio, **_kwargs):
            return b''.join(audio)
    assert srv._build_tts_audio_payloads(Agent(), 'reply', language=language) == [b'one' if chunks==1 else b'onetwothree']
    assert sorted(calls) == sorted((text,language) for text in ['one','two','three'][:chunks])


def test_full_text_tts_retry_keeps_turn_language():
    calls = []
    class Agent:
        def prepare_tts_chunks(self, _text, max_chunks=3):
            return ['one','two']
        def text_to_audio(self, text, trim_pad_ms, language=None):
            calls.append((text,language))
            return b'' if text=='two' else text.encode()
        def merge_audio_chunks(self, *_args, **_kwargs):
            raise AssertionError('partial output must not play')
    assert srv._build_tts_audio_payloads(Agent(), 'reply', language='es') == [b'one two']
    assert sorted(calls) == [('one','es'),('one two','es'),('two','es')]


@pytest.mark.parametrize('text', ['Cats purr.', '你好', '今日はいい天気ですね', 'Hola'])
def test_robot_mode_normal_conversation_uses_one_dialogue_call(text):
    agent = Mock()
    agent.generate_response.return_value = ('brief reply','none')
    robot = Mock()
    robot.handle_text.return_value = None
    assert srv._generate_device_response(agent, robot, text, 'es', 'speaker') == ('brief reply','none')
    agent.generate_response.assert_called_once_with(text,speaker_id='speaker',language='es')


def test_explicit_motor_request_uses_controller_without_model_and_errors_match_language():
    from src.robotics.models import RoboticsError
    agent = Mock()
    robot = Mock()
    robot.handle_text.return_value = {'status':'pending','command_id':'synthetic'}
    reply, intent = srv._generate_device_response(agent, robot, 'wave please', 'en', 'speaker')
    assert 'request' in reply.lower()
    assert intent == 'robot_action'
    agent.generate_response.assert_not_called()
    robot.handle_text.side_effect = RoboticsError('device_not_armed')
    reply, intent = srv._generate_device_response(agent, robot, 'asiente', 'es', 'speaker')
    assert 'configur' in reply.casefold()
    assert intent == 'robot_setup_required'
    agent.generate_response.assert_not_called()


@pytest.mark.parametrize('mode', ['agent','robot'])
@pytest.mark.parametrize('language,text', [('ko','오늘 날씨 어때요'),('en','Cats purr.'),('zh','今天天气很好'),('ja','天気がいいですね'),('es','Los gatos ronronean.')])
def test_real_socket_voice_worker_and_robot_status_roundtrip(monkeypatch, mode, language, text):
    import json
    import socket
    import struct
    import threading
    import numpy as np
    from src.robotics.runtime import RobotRuntime
    from src.protocol import PTYPE_CMD, PTYPE_ROBOT_STATUS, PTYPE_AUDIO_OUT
    runtime = RobotRuntime()
    class Agent:
        robotics_runtime = runtime
        calls = []
        voices = []
        def describe_dialogue(self): return {'language':'auto'}
        def generate_response(self, incoming, speaker_id=None, language=None):
            self.calls.append((incoming,language))
            return text, 'none'
        def prepare_tts_chunks(self, reply, max_chunks=3): return [reply]
        def text_to_audio(self, reply, trim_pad_ms=180, language=None):
            self.voices.append((reply,language))
            return b'\x00\x01'*160
    agent = Agent()
    stt = Mock()
    stt.safe_transcribe.return_value = ([SimpleNamespace(text=text)],SimpleNamespace(language=language))
    config = srv._FakeConfig if hasattr(srv,'_FakeConfig') else None
    class Config:
        def get(self,*_keys,default=None): return default
    client, server = socket.socketpair()
    client.settimeout(3)
    monkeypatch.setattr(srv,'agent_handler',agent)
    monkeypatch.setattr(srv,'current_mode',mode)
    thread = threading.Thread(target=srv.handle_connection,args=(server,('test',5001),stt,Config()),daemon=True)
    def frame(kind, payload=b''):
        client.sendall(struct.pack('<BH',kind,len(payload))+payload)
    def read_exact(count):
        result = b''
        while len(result)<count:
            chunk = client.recv(count-len(result))
            assert chunk
            result += chunk
        return result
    def read_frame():
        kind,size = struct.unpack('<BH',read_exact(3))
        return kind,read_exact(size)
    try:
        thread.start()
        frame(srv.PTYPE_START)
        kind,raw = read_frame()
        assert kind == PTYPE_CMD
        command = json.loads(raw)
        assert command['op'] == 'discover'
        status = {key:command[key] for key in ('v','op','command_id','session_id','seq')}
        status.update(status='DONE',boot_id='physical-test-boot',armed=False,commanded_angles=[90,90],feedback_kind='commanded',
                      capabilities={'device_id':'physical-test','boot_id':'physical-test-boot','controller':'legacy_direct',
                                    'servo_count':2,'display':'none','feedback_kind':'commanded','sensors':[],
                                    'firmware_revision':'robot-control-1'})
        frame(PTYPE_ROBOT_STATUS,json.dumps(status).encode())
        samples = np.sin(np.arange(12800)*.08)*8000
        audio = samples.astype('<i2').tobytes()
        for start in range(0,len(audio),1024):
            frame(srv.PTYPE_AUDIO,audio[start:start+1024])
        frame(srv.PTYPE_END)
        for _ in range(4):
            kind,raw = read_frame()
            if kind == PTYPE_AUDIO_OUT:
                assert raw
                break
        else:
            raise AssertionError('no speech output frame')
        assert agent.calls == [(text,language)]
        assert agent.voices == [(text,language)]
        assert runtime.snapshot()['controller']['capabilities']['device_id'] == 'physical-test'
    finally:
        client.close()
        thread.join(2)
        server.close()
        runtime.close()
    assert not thread.is_alive()
    assert runtime.snapshot()['physical_connected'] is False
