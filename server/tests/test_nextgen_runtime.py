import json

import pytest

from fastapi.testclient import TestClient

from config_loader import Config
from src.agent_mode import AgentMode
from web.app import create_app
from web.auth import configure


class Model:
    def __init__(self, replies):
        self.replies = replies
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append(messages)
        return self.replies.pop(0)


def test_agent_uses_personal_tools_without_shared_memory_extraction(tmp_path):
    llm = Model([
        '{"tool":"memory.remember","arguments":{"text":"디카페인"}}',
        '{"answer":"기억했어요."}',
        '{"tool":"memory.recall","arguments":{}}',
        '{"answer":"저장된 기억이 없어요."}',
    ])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.memory.after_turn = lambda _: (_ for _ in ()).throw(AssertionError('shared extraction'))
    assert agent.generate_response('기억해', speaker_id='alice') == ('확인된 실행 결과: 기억 저장 ID 1: 디카페인.', 'none')
    agent.generate_response('내 기억', speaker_id='bob')
    assert '디카페인' not in json.dumps(llm.requests[-1], ensure_ascii=False)
    assert agent.conversation_count == 2
    assert len(agent.user_histories['alice']) == 2


def test_nextgen_environment_configuration(monkeypatch):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('AGENT_STATE_PATH', '/state/personal.sqlite3')
    cfg = Config(config_file='missing.yaml')
    assert cfg.get('agent', 'enabled') is True
    assert cfg.get('agent', 'state_path') == '/state/personal.sqlite3'


def test_agent_api_requires_auth_and_reports_tools(tmp_path):
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    client = TestClient(create_app(lambda: agent, lambda: None, lambda: 'agent'))
    configure('test-only-token')
    try:
        assert client.get('/api/agent/').status_code == 401
        response = client.get('/api/agent/', headers={'X-Auth-Token': 'test-only-token'})
        assert response.status_code == 200
        data = response.json()
        assert data['enabled'] is True
        assert 'memory.remember' in [tool['name'] for tool in data['tools']]
        assert data['recent_runs'] == []
    finally:
        configure('')


def test_disabled_agent_api_reports_disabled(tmp_path):
    agent = AgentMode(Model([]), memory_dir=str(tmp_path))
    client = TestClient(create_app(lambda: agent, lambda: None, lambda: 'agent'))
    configure('')
    response = client.get('/api/agent/')
    assert response.status_code == 200
    assert response.json() == {'enabled': False, 'tools': [], 'recent_runs': []}


def test_runtime_injects_only_soul_and_connects_read_registry(tmp_path):
    (tmp_path / 'Soul.md').write_text('CUSTOM_SOUL', encoding='utf-8')
    (tmp_path / 'User.md').write_text('PRIVATE_OTHER_USER', encoding='utf-8')
    (tmp_path / 'Relation.md').write_text('PRIVATE_RELATION', encoding='utf-8')
    llm = Model(['{"answer":"응답"}'])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.generate_response('안녕', speaker_id='alice')
    prompt = llm.requests[0][0]['content']
    assert 'CUSTOM_SOUL' in prompt
    assert 'PRIVATE_OTHER_USER' not in prompt and 'PRIVATE_RELATION' not in prompt
    assert agent.tool_agent.integrations is agent.integrations


def test_runtime_initializes_home_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME_ASSISTANT_URL', 'http://home.local:8123')
    monkeypatch.setenv('HOME_ASSISTANT_TOKEN', 'test-token')
    monkeypatch.setenv('HOME_ASSISTANT_ALLOWED_ENTITIES', 'light.study, switch.fan')
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.tool_agent.home.is_configured()
    assert 'home.control' in {item['name'] for item in agent.tool_agent.catalog()}


def test_invalid_home_configuration_keeps_personal_tools_and_sanitizes_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('HOME_ASSISTANT_URL', 'http://secret:private@home.local')
    monkeypatch.setenv('HOME_ASSISTANT_TOKEN', 'sensitive-token')
    monkeypatch.setenv('HOME_ASSISTANT_ALLOWED_ENTITIES', 'light.study')
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.tool_agent.home is None
    assert 'memory.remember' in {item['name'] for item in agent.tool_agent.catalog()}
    assert 'Home Assistant' in caplog.text
    assert 'sensitive-token' not in caplog.text and 'secret:private' not in caplog.text


def test_explicit_schedule_request_uses_existing_household_scheduler(tmp_path):
    from scheduler import Scheduler
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.scheduler = Scheduler(str(tmp_path / 'schedules.json'))
    response, intent = agent.generate_response('내일 오후 3시 회의 일정 추가', speaker_id='alice')
    assert '등록' in response and intent == 'none'
    assert len(agent.scheduler.schedules) == 1
    assert len(agent.user_histories['alice']) == 2


def test_schedule_parser_errors_return_safe_failure(tmp_path):
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    response, _ = agent.generate_response('내일 99시 회의 일정 추가', speaker_id='alice')
    assert '확인' in response


def test_tool_runtime_preserves_sleep_intent_and_effects(tmp_path):
    llm = Model(['{"answer":"[INTENT:sleep] 잠시 쉴게요."}'])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('자러 가', speaker_id='alice') == ('잠시 쉴게요.', 'sleep')
    assert agent.proactive.sleep_mode is True
    assert agent.proactive.sleep_until.hour == 8


def test_tool_runtime_preserves_robot_intent(tmp_path):
    llm = Model(['{"answer":"[INTENT:mode_robot] 로봇 모드로 바꿀게요."}'])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('로봇 모드', speaker_id='alice') == ('로봇 모드로 바꿀게요.', 'mode_robot')


def test_today_schedule_query_does_not_create_schedule(tmp_path):
    from scheduler import Scheduler
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.scheduler = Scheduler(str(tmp_path / 'schedules.json'))
    response, _ = agent.generate_response('오늘 일정 알려줘', speaker_id='alice')
    assert '없습니다' in response
    assert agent.scheduler.schedules == []


def test_schedule_save_failure_does_not_claim_success_or_keep_phantom(tmp_path):
    from scheduler import Scheduler
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.scheduler = Scheduler(str(tmp_path / 'missing-parent' / 'schedules.json'))
    response, _ = agent.generate_response('내일 오후 3시 회의 일정 추가', speaker_id='alice')
    assert '처리하지 못했어요' in response
    assert agent.scheduler.schedules == []


def test_negative_schedule_request_does_not_create_schedule(tmp_path):
    from scheduler import Scheduler
    llm = Model(['{"answer":"추가하지 않을게요."}'])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.scheduler = Scheduler(str(tmp_path / 'schedules.json'))
    agent.generate_response('내일 오후 3시 회의 일정 추가하지 마', speaker_id='alice')
    assert agent.scheduler.schedules == []


def test_identical_schedule_request_is_not_repeated(tmp_path):
    from scheduler import Scheduler
    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.scheduler = Scheduler(str(tmp_path / 'schedules.json'))
    request = '내일 오후 3시 회의 일정 추가'
    agent.generate_response(request, speaker_id='alice')
    response, _ = agent.generate_response(request, speaker_id='alice')
    assert '이미' in response
    assert len(agent.scheduler.schedules) == 1


def test_soul_cache_updates_apply_on_next_tool_turn(tmp_path):
    llm = Model(['{"answer":"응답"}'])
    agent = AgentMode(llm, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.memory._cache['Soul.md'] = 'UPDATED_SOUL_FOR_NEXT_TURN'
    agent.memory._cache['User.md'] = 'PRIVATE_USER_MUST_STAY_OUT'
    agent.generate_response('안녕', speaker_id='alice')
    prompt = llm.requests[0][0]['content']
    assert 'UPDATED_SOUL_FOR_NEXT_TURN' in prompt
    assert 'PRIVATE_USER_MUST_STAY_OUT' not in prompt


def test_fast_personal_read_does_not_wait_for_another_owner_model(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    fast_done = threading.Event()

    class SlowModel:
        def __init__(self):
            self.requests = []
        def chat(self, messages, **_kwargs):
            self.requests.append(messages)
            entered.set()
            assert release.wait(3), 'test release missing'
            return '{"answer":"합성 웹 응답"}'

    model = SlowModel()
    agent = AgentMode(model, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.tool_agent.store.add_task('bob', '다른 화자의 합성 할 일')
    def fast_read():
        result = agent.generate_response('내 할 일 보여줘', speaker_id='bob')
        fast_done.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(agent.generate_response, '합성 느린 질문', speaker_id='alice')
        assert entered.wait(1)
        fast = pool.submit(fast_read)
        try:
            assert fast_done.wait(0.5), 'other-owner direct read waited for the model'
        finally:
            release.set()
        assert '합성 할 일' in fast.result(timeout=2)[0]
        assert slow.result(timeout=2)[0] == '합성 웹 응답'
    assert agent.conversation_count == 2
    assert len(agent.user_histories['alice']) == len(agent.user_histories['bob']) == 2
    assert '다른 화자' not in json.dumps(model.requests, ensure_ascii=False)


def test_same_owner_direct_read_keeps_model_turn_order(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    fast_done = threading.Event()
    class SlowModel:
        def chat(self, _messages, **_kwargs):
            entered.set()
            assert release.wait(3), 'test release missing'
            return '{"answer":"첫 합성 응답"}'

    agent = AgentMode(SlowModel(), memory_dir=str(tmp_path), agent_config={'enabled': True})
    def fast_read():
        result = agent.generate_response('내 할 일 보여줘', speaker_id='alice')
        fast_done.set()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(agent.generate_response, '첫 합성 질문', speaker_id='alice')
        assert entered.wait(1)
        fast = pool.submit(fast_read)
        try:
            assert not fast_done.wait(0.2), 'same owner interleaved the unfinished turn'
        finally:
            release.set()
        assert slow.result(timeout=2)[0] == '첫 합성 응답'
        assert '없습니다' in fast.result(timeout=2)[0]
    assert [item['content'] for item in agent.user_histories['alice'][:3]] == [
        '첫 합성 질문', '첫 합성 응답', '내 할 일 보여줘',
    ]


def test_unrelated_model_request_does_not_wait_for_home_control(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    other_done = threading.Event()
    class Home:
        allowed_entities = ['light.study']
        def is_configured(self):
            return True
        def control(self, entity_id, action):
            entered.set()
            assert release.wait(3), 'test release missing'
            return {'entity_id': entity_id, 'confirmed': True, 'state': 'on'}

    agent = AgentMode(Model(['{"answer":"다른 합성 응답"}']), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.tool_agent.home = Home()
    def other_request():
        result = agent.generate_response('다른 합성 질문', speaker_id='bob')
        other_done.set()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        home = pool.submit(agent.generate_response, 'light.study 켜줘', speaker_id='alice')
        assert entered.wait(1)
        other = pool.submit(other_request)
        try:
            assert other_done.wait(0.5), 'unrelated request waited for home control'
        finally:
            release.set()
        assert '켜짐' in home.result(timeout=2)[0]
        assert other.result(timeout=2)[0] == '다른 합성 응답'


def test_home_sequences_remain_serial_between_owners(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    second_done = threading.Event()
    class Home:
        allowed_entities = ['light.study']
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def control(self, entity_id, action):
            self.actions.append(action)
            if len(self.actions) == 1:
                entered.set()
                assert release.wait(3), 'test release missing'
            return {'entity_id': entity_id, 'confirmed': True, 'state': 'on' if action == 'turn_on' else 'off'}

    agent = AgentMode(Model([]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.tool_agent.home = Home()
    def second_sequence():
        result = agent.generate_response('light.study 꺼줘', speaker_id='bob')
        second_done.set()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(agent.generate_response, 'light.study 켜고 껐다가 다시 켜줘', speaker_id='alice')
        assert entered.wait(1)
        second = pool.submit(second_sequence)
        try:
            assert not second_done.wait(0.2)
            assert agent.tool_agent.home.actions == ['turn_on']
        finally:
            release.set()
        first.result(timeout=2)
        second.result(timeout=2)
    assert agent.tool_agent.home.actions == ['turn_on', 'turn_off', 'turn_on', 'turn_off']


def test_nonproactive_model_turns_still_serialize_provider_state(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    first_entered = threading.Event()
    second_entered = threading.Event()
    release = threading.Event()
    class ModelWithSharedState:
        def __init__(self):
            self.calls = 0
        def chat(self, _messages, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                first_entered.set()
                assert release.wait(3), 'test release missing'
            else:
                second_entered.set()
            return '{"answer":"합성 모델 응답"}'

    agent = AgentMode(ModelWithSharedState(), memory_dir=str(tmp_path), agent_config={'enabled': True})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(agent.generate_response, '첫 합성 질문', speaker_id='alice')
        assert first_entered.wait(1)
        second = pool.submit(agent.generate_response, '둘째 합성 질문', speaker_id='bob')
        try:
            assert not second_entered.wait(0.2), 'shared provider state was entered concurrently'
        finally:
            release.set()
        assert first.result(timeout=2)[0] == second.result(timeout=2)[0] == '합성 모델 응답'
    assert second_entered.is_set()


@pytest.mark.parametrize('speaker', [None, 'alice'])
def test_proactive_agent_uses_ephemeral_public_context_without_personal_extraction(tmp_path, speaker):
    (tmp_path / 'Soul.md').write_text('PUBLIC_SOUL', encoding='utf-8')
    for filename in ('User.md', 'Relation.md', 'Longterm_Memory.md', 'Shortterm_Memory.md'):
        (tmp_path / filename).write_text('PRIVATE_DOCUMENT_' + filename, encoding='utf-8')
    model = Model(['잠깐 쉬어볼까요?'])
    agent = AgentMode(model, memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.conversation_history = [{'role': 'user', 'content': 'PRIVATE_DEVICE_HISTORY'}]
    agent.user_histories['alice'] = [{'role': 'user', 'content': 'PRIVATE_ALICE_HISTORY'}]
    before_device = list(agent.conversation_history)
    before_alice = list(agent.user_histories['alice'])
    extractions = []
    agent.memory.after_turn = lambda history: extractions.append(list(history))
    response, intent = agent.generate_response('간단히 휴식을 제안해줘', is_proactive=True, speaker_id=speaker)
    assert response == '잠깐 쉬어볼까요?' and intent == 'none'
    prompt = json.dumps(model.requests, ensure_ascii=False)
    assert 'PUBLIC_SOUL' in prompt and '간단히 휴식을 제안해줘' in prompt
    assert 'PRIVATE_' not in prompt
    assert extractions == []
    assert agent.conversation_history == before_device
    assert agent.user_histories['alice'] == before_alice
    assert agent.conversation_count == 1
    assert agent.tool_agent.recent_runs() == []


@pytest.mark.parametrize('tag', ['sleep', 'mode_robot'])
def test_proactive_reply_cannot_change_device_intent_or_sleep_state(tmp_path, tag):
    agent = AgentMode(Model([f'[INTENT:{tag}] 잠깐 쉬어볼까요?']), memory_dir=str(tmp_path), agent_config={'enabled': True})
    response, intent = agent.generate_response('간단히 인사해줘', is_proactive=True)
    assert response == '잠깐 쉬어볼까요?' and intent == 'none'
    assert agent.proactive.sleep_mode is False
    assert agent.proactive.sleep_until is None
    assert agent.tool_agent.recent_runs() == []


def test_busy_user_model_skips_proactive_generation_without_waiting(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    class BusyModel:
        def __init__(self):
            self.calls = 0
        def chat(self, _messages, **_kwargs):
            self.calls += 1
            if self.calls > 1:
                return '선제 대화가 실행되면 안 됩니다'
            entered.set()
            assert release.wait(3), 'test release missing'
            return '{"answer":"사용자 합성 응답"}'

    model = BusyModel()
    agent = AgentMode(model, memory_dir=str(tmp_path), agent_config={'enabled': True})
    with ThreadPoolExecutor(max_workers=2) as pool:
        user = pool.submit(agent.generate_response, '합성 질문', speaker_id='alice')
        assert entered.wait(1)
        emotion_before = (agent.emotion_system.current_emotion, len(agent.emotion_system.emotion_history))
        proactive_before = (agent.proactive.last_interaction, agent.proactive.last_proactive, agent.proactive.proactive_count, agent.proactive.sleep_mode)
        proactive = pool.submit(agent.generate_response, '인사해줘', is_proactive=True)
        try:
            assert proactive.result(timeout=0.5) == ('', 'none')
            assert model.calls == 1
            assert (agent.emotion_system.current_emotion, len(agent.emotion_system.emotion_history)) == emotion_before
            assert (agent.proactive.last_interaction, agent.proactive.last_proactive, agent.proactive.proactive_count, agent.proactive.sleep_mode) == proactive_before
        finally:
            release.set()
        assert user.result(timeout=2)[0] == '사용자 합성 응답'
    assert agent.conversation_count == 1


def test_proactive_errors_do_not_log_raw_private_exception(tmp_path, caplog):
    class BrokenModel:
        def chat(self, _messages, **_kwargs):
            raise RuntimeError('SYNTHETIC_PRIVATE_REQUEST_AND_KEY')

    agent = AgentMode(BrokenModel(), memory_dir=str(tmp_path), agent_config={'enabled': True})
    response, intent = agent.generate_response('인사해줘', is_proactive=True)
    assert intent == 'none'
    assert 'SYNTHETIC_PRIVATE_REQUEST_AND_KEY' not in response + caplog.text
    assert agent.conversation_history == []


def test_proactive_tool_proposal_is_not_executed_or_spoken(tmp_path):
    agent = AgentMode(Model(['{"tool":"memory.recall","arguments":{}}']), memory_dir=str(tmp_path), agent_config={'enabled': True})
    agent.tool_agent.store.recall = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('private store accessed'))
    assert agent.generate_response('간단히 인사해줘', is_proactive=True) == ('', 'none')
    assert agent.tool_agent.recent_runs() == []
    assert agent.conversation_count == 0


def test_proactive_removes_all_device_intent_tags(tmp_path):
    agent = AgentMode(Model(['[INTENT:sleep] 잠깐 [INTENT:mode_robot] 쉬어볼까요?']), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('간단히 인사해줘', is_proactive=True) == ('잠깐 쉬어볼까요?', 'none')
    assert agent.proactive.sleep_mode is False


def test_proactive_accepts_answer_json_without_tool_execution(tmp_path):
    agent = AgentMode(Model(['{"answer":"[INTENT:sleep] 잠깐 쉬어볼까요?"}']), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('간단히 인사해줘', is_proactive=True) == ('잠깐 쉬어볼까요?', 'none')
    assert agent.proactive.sleep_mode is False
    assert agent.tool_agent.recent_runs() == []


def test_proactive_skip_also_applies_inside_current_model_callback(tmp_path):
    class CallbackModel:
        def __init__(self):
            self.calls = 0
            self.agent = None
        def chat(self, _messages, **_kwargs):
            self.calls += 1
            if self.calls > 1:
                return '선제 생성이 재진입했어요'
            assert self.agent.generate_response('인사해줘', is_proactive=True) == ('', 'none')
            return '{"answer":"사용자 합성 응답"}'

    model = CallbackModel()
    agent = AgentMode(model, memory_dir=str(tmp_path), agent_config={'enabled': True})
    model.agent = agent
    assert agent.generate_response('합성 질문', speaker_id='alice') == ('사용자 합성 응답', 'none')
    assert model.calls == 1
    assert agent.conversation_history == []


@pytest.mark.parametrize('raw', [
    '[INTENT:sleep] {"tool":"memory.recall","arguments":{}}',
    json.dumps({'answer': '{"tool":"memory.recall","arguments":{}}'}),
    json.dumps({'answer': '```json\n{"tool":"memory.recall","arguments":{}}\n```'}),
])
def test_proactive_does_not_speak_tagged_or_nested_tool_payloads(tmp_path, raw):
    agent = AgentMode(Model([raw]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('간단히 인사해줘', is_proactive=True) == ('', 'none')
    assert agent.tool_agent.recent_runs() == []
    assert agent.conversation_count == 0


@pytest.mark.parametrize('raw', [
    '잠시 확인할게요: {"tool":"memory.recall","arguments":{}}',
    '잠시 확인할게요: ```json\n{"tool":"memory.recall","arguments":{}}\n```',
    '잠깐 쉬어볼까요? ```python\nprint(1)\n```',
])
def test_proactive_suppresses_prefixed_json_and_code_fences(tmp_path, raw):
    agent = AgentMode(Model([raw]), memory_dir=str(tmp_path), agent_config={'enabled': True})
    assert agent.generate_response('간단히 인사해줘', is_proactive=True) == ('', 'none')
    assert agent.tool_agent.recent_runs() == []
    assert agent.conversation_count == 0
