import json

import pytest


def make_agent(tmp_path, replies):
    from src.personal_store import PersonalStore
    from src.tool_agent import ToolAgent

    class Model:
        def __init__(self):
            self.messages = []

        def chat(self, messages, **kwargs):
            self.messages.append(list(messages))
            return replies.pop(0)

    model = Model()
    store = PersonalStore(tmp_path / 'personal.sqlite3')
    return ToolAgent(model, store), store, model


def test_remember_then_answer_uses_server_owner(tmp_path):
    agent, store, model = make_agent(tmp_path, [
        '{"tool":"memory.remember","arguments":{"text":"커피는 디카페인"}}',
        '{"answer":"기억했어요."}',
    ])
    assert agent.run('디카페인 좋아하는 거 기억해', 'alice', []) == '확인된 실행 결과: 기억 저장 ID 1: 커피는 디카페인.'
    assert store.recall('alice')[0]['text'] == '커피는 디카페인'
    assert store.recall('bob') == []
    assert '커피는 디카페인' in json.dumps(model.messages[-1], ensure_ascii=False)
    runs = agent.recent_runs()
    assert runs[-1]['tool'] == 'memory.remember'
    assert runs[-1]['ok'] is True
    assert '커피' not in json.dumps(runs, ensure_ascii=False)


@pytest.mark.parametrize('call', [
    {'tool': 'shell.exec', 'arguments': {'command': 'whoami'}},
    {'tool': 'memory.remember', 'arguments': {'text': 'x', 'owner': 'bob'}},
    {'tool': 'tasks.complete', 'arguments': {'item_id': True}},
    {'tool': 'memory.remember', 'arguments': {'text': []}},
])
def test_invalid_tool_or_arguments_never_mutate(tmp_path, call):
    agent, store, model = make_agent(tmp_path, [json.dumps(call), '{"answer":"확인해 주세요."}'])
    agent.run('요청', 'alice', [])
    assert store.recall('alice') == []
    assert store.recall('bob') == []
    assert agent.recent_runs()[-1]['ok'] is False


def test_repeated_calls_are_bounded(tmp_path):
    call = '{"tool":"tasks.list","arguments":{}}'
    agent, _, model = make_agent(tmp_path, [call] * 10)
    result = agent.run('할 일 확인', 'alice', [])
    assert len(model.messages) <= 5
    assert len(agent.recent_runs()) == 4
    assert '한도' in result


def test_plain_conversation_works_with_existing_llm(tmp_path):
    agent, _, _ = make_agent(tmp_path, ['안녕하세요.'])
    assert agent.run('안녕', 'alice', []) == '안녕하세요.'


def test_bad_json_does_not_leak_raw_tool_call(tmp_path):
    agent, _, _ = make_agent(tmp_path, ['{"tool":"tasks.add", broken'])
    result = agent.run('할 일', 'alice', [])
    assert 'broken' not in result
    assert '다시' in result


def test_task_can_be_completed_only_by_its_owner(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.complete","arguments":{"item_id":1}}',
        '{"answer":"항목을 찾지 못했어요."}',
    ])
    store.add_task('bob', '비공개 작업')
    agent.run('완료해', 'alice', [])
    assert store.list_tasks('bob')[0]['done'] is False


def test_tool_result_is_data_and_history_is_bounded(tmp_path):
    agent, _, model = make_agent(tmp_path, ['{"answer":"응답"}'])
    history = [{'role': 'user', 'content': 'x' * 9000}] * 50
    agent.run('질문', 'alice', history)
    assert len(model.messages[0]) <= 23
    assert all(len(m['content']) <= 12000 for m in model.messages[0])


def test_missing_home_is_not_advertised(tmp_path):
    agent, _, _ = make_agent(tmp_path, [])
    assert all(not tool['name'].startswith('home.') for tool in agent.catalog())


def test_failed_tool_stops_before_model_can_claim_success_or_retry(tmp_path):
    call = '{"tool":"tasks.complete","arguments":{"item_id":99}}'
    agent, _, model = make_agent(tmp_path, [call, call, '{"answer":"완료했어요."}'])
    assert '실패' in agent.run('완료해', 'alice', [])
    assert len(model.messages) == 1
    assert len(agent.recent_runs()) == 1


def test_soul_is_preserved_but_policy_is_appended_after_it(tmp_path):
    from src.tool_agent import ToolAgent
    agent, store, model = make_agent(tmp_path, ['{"answer":"응답"}'])
    agent = ToolAgent(model, store, soul='CUSTOM_SOUL')
    agent.run('안녕', 'alice', [])
    prompt = model.messages[0][0]['content']
    assert prompt.index('CUSTOM_SOUL') < prompt.index('Return exactly one JSON')


class ReadIntegration:
    def __init__(self, name, configured=True, ok=True):
        self.name, self.configured, self.ok = name, configured, ok
        self.calls = []

    def is_configured(self):
        return self.configured

    def execute(self, intent, params):
        from src.integrations.base import IntegrationResult, IntegrationErrorCode
        self.calls.append((intent, params))
        if self.ok:
            return IntegrationResult.success({'value': 'READ_RESULT'})
        return IntegrationResult.failure(IntegrationErrorCode.UNKNOWN, 'SECRET', {'secret': 'SECRET'})


def read_agent(tmp_path, tool, arguments, *, configured=True, enabled=True, ok=True):
    from src.integrations.registry import IntegrationRegistry
    from src.tool_agent import ToolAgent
    agent, store, model = make_agent(tmp_path, [json.dumps({'tool': tool, 'arguments': arguments}), '{"answer":"결과"}'])
    registry = IntegrationRegistry()
    provider = {'weather.current': 'weather', 'search.query': 'search', 'calendar.list': 'calendar-google'}[tool]
    integration = ReadIntegration(provider, configured, ok)
    registry.register(integration, enabled)
    return ToolAgent(model, store, integrations=registry), integration, model


@pytest.mark.parametrize('tool,args', [('weather.current', {}), ('search.query', {'query': '뉴스'}), ('calendar.list', {})])
def test_read_integrations_are_available_and_results_reach_model(tmp_path, tool, args):
    agent, integration, model = read_agent(tmp_path, tool, args)
    assert agent.run('조회', 'alice', []) == '결과'
    assert integration.calls == [(tool, args)]
    assert 'READ_RESULT' in json.dumps(model.messages[-1])
    assert not {'calendar.create', 'notify.send'} & {item['name'] for item in agent.catalog()}


@pytest.mark.parametrize('configured,enabled', [(False, True), (True, False)])
def test_inactive_read_integrations_are_not_exposed(tmp_path, configured, enabled):
    agent, integration, _ = read_agent(tmp_path, 'weather.current', {}, configured=configured, enabled=enabled)
    assert 'weather.current' not in {item['name'] for item in agent.catalog()}
    agent.run('조회', 'alice', [])
    assert not integration.calls


def test_integration_failure_is_deterministic_and_sanitized(tmp_path):
    agent, _, model = read_agent(tmp_path, 'calendar.list', {}, ok=False)
    result = agent.run('조회', 'alice', [])
    assert '실패' in result and 'SECRET' not in result
    assert len(model.messages) == 1


@pytest.mark.parametrize('query', ['', '  ', 'x' * 301])
def test_search_query_boundaries_prevent_http_execution(tmp_path, query):
    agent, integration, _ = read_agent(tmp_path, 'search.query', {'query': query})
    assert '실패' in agent.run('검색', 'alice', [])
    assert not integration.calls


@pytest.mark.parametrize('user_text', [
    'ccoli 연결 점검 할 일을 완료해 줘', 'Complete my task ccoli connection check',
    'Show my tasks', '남은 할 일은?',
    '커피 좋아한다고 기억해 줘', 'Remember that I like coffee',
    '커피에 대한 기억을 삭제해 줘', 'Forget my coffee preference',
    'What do you remember about me?',
    '현재 조명 상태 알려줘',
])
def test_explicit_requests_cannot_finish_without_fresh_tool_evidence(tmp_path, user_text):
    agent, _, model = make_agent(tmp_path, ['{"answer":"완료했습니다. 남은 항목은 없어요."}'] * 5)
    result = agent.run(user_text, 'alice', [])
    assert '확인하지 못' in result
    assert len(model.messages) == 3


def test_correction_can_recover_real_task_completion(tmp_path):
    agent, store, model = make_agent(tmp_path, [
        '{"answer":"완료했습니다."}',
        '{"tool":"tasks.list","arguments":{}}',
        '{"tool":"tasks.complete","arguments":{"item_id":1}}',
        '{"answer":"완료했습니다."}',
    ])
    store.add_task('alice', 'ccoli 연결 점검')
    response = agent.run('ccoli 연결 점검 할 일을 완료해 줘', 'alice', [])
    assert response.startswith('확인된 실행 결과: 할 일 완료 ID 1.')
    assert '할 일 (변경 전 조회)' in response
    assert '못했어요' not in response
    assert store.list_tasks('alice') == []
    assert 'tasks.complete' in model.messages[1][-1]['content']


def test_list_success_is_not_mutation_evidence(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.list","arguments":{}}',
        '{"answer":"완료했습니다."}', '{"answer":"완료했습니다."}', '{"answer":"완료했습니다."}',
    ])
    store.add_task('alice', '점검')
    assert '확인하지 못' in agent.run('점검 할 일 완료해 줘', 'alice', [])
    assert len(store.list_tasks('alice')) == 1


def test_prior_turn_success_does_not_satisfy_current_query(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    assert '남은 할 일이 없습니다' in agent.run('내 할 일 보여줘', 'alice', [])
    store.add_task('alice', '현재 점검')
    response = agent.run('내 할 일 보여줘', 'alice', [{'role': 'assistant', 'content': '없어요.'}])
    assert '현재 점검' in response
    assert '남은 할 일이 없습니다' not in response
    assert model.messages == []
    assert [run['tool'] for run in agent.recent_runs()] == ['tasks.list', 'tasks.list']


def test_contextual_completion_needs_current_mutation(tmp_path):
    agent, _, _ = make_agent(tmp_path, ['{"answer":"완료했습니다."}'] * 3)
    history = [{'role': 'user', 'content': '내 할 일 보여줘'}, {'role': 'assistant', 'content': '점검이 있어요.'}]
    assert '확인하지 못' in agent.run('그거 완료해 줘', 'alice', history)


@pytest.mark.parametrize('user_text', ['할 일 추가하지 마', "Don't add a task", '기억하지 마', '불 켜지 마'])
def test_negative_requests_do_not_force_writes(tmp_path, user_text):
    agent, _, model = make_agent(tmp_path, ['{"answer":"변경하지 않을게요."}'])
    assert agent.run(user_text, 'alice', []) == '변경하지 않을게요.'
    assert len(model.messages) == 1


def test_successful_mutation_is_not_repeated_within_turn(tmp_path):
    call = '{"tool":"tasks.add","arguments":{"title":"점검"}}'
    agent, store, _ = make_agent(tmp_path, [call, call, '{"answer":"추가했어요."}'])
    assert agent.run('점검 할 일 추가해 줘', 'alice', []) == '확인된 실행 결과: 할 일 추가 ID 1: 점검.'
    assert len(store.list_tasks('alice')) == 1
    assert len(agent.recent_runs()) == 1


def test_corrections_do_not_increase_four_tool_execution_limit(tmp_path):
    agent, _, model = make_agent(tmp_path, [
        '{"answer":"완료했어요."}', '{"answer":"완료했어요."}',
        *['{"tool":"tasks.list","arguments":{}}'] * 5,
    ])
    assert '한도' in agent.run('할 일 완료해 줘', 'alice', [])
    assert len(agent.recent_runs()) == 4
    assert len(model.messages) == 7


@pytest.mark.parametrize('user_text', ['할 일 완료하는 방법 알려줘', '불 켜는 방법 알려줘', 'How do I complete a task?', 'How to turn on a light?'])
def test_explanations_do_not_force_mutations(tmp_path, user_text):
    agent, _, model = make_agent(tmp_path, ['{"answer":"설정에서 선택하세요."}'])
    assert agent.run(user_text, 'alice', []) == '설정에서 선택하세요.'
    assert len(model.messages) == 1


def test_completed_tasks_query_requires_read_only(tmp_path):
    agent, _, model = make_agent(tmp_path, [
        '{"tool":"tasks.list","arguments":{"include_done":true}}',
        '{"answer":"완료한 목록이에요."}',
    ])
    assert '할 일이 없습니다' in agent.run('완료한 할 일 보여줘', 'alice', [])
    assert len(model.messages) == 2


def test_home_repeated_action_after_opposite_action_executes_again(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '불', 'state': 'off'}]
        def control(self, entity_id, action):
            self.actions.append(action)
            return {'entity_id': entity_id, 'confirmed': True, 'state': 'on' if action == 'turn_on' else 'off'}

    on = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'
    off = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_off"}}'
    agent, _, _ = make_agent(tmp_path, [on, off, on, '{"answer":"켰어요."}'])
    agent.home = Home()
    assert agent.run('불 켜고 껐다가 다시 켜줘', 'alice', []).count('홈 상태 확인 light.study:') == 3
    assert agent.home.actions == ['turn_on', 'turn_off', 'turn_on']


def test_prompt_requires_claims_to_match_verified_targets_and_counts(tmp_path):
    agent, _, model = make_agent(tmp_path, ['{"answer":"안녕하세요."}'])
    agent.run('안녕', 'alice', [])
    prompt = model.messages[0][0]['content']
    assert 'verified target IDs and counts' in prompt
    assert 'do not claim every requested item was changed' in prompt


def test_mutation_answer_reports_only_verified_targets(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.complete","arguments":{"item_id":1}}',
        '{"answer":"두 할 일을 모두 완료했습니다."}',
    ])
    store.add_task('alice', 'first')
    store.add_task('alice', 'second')
    response = agent.run('첫 할 일과 두 번째 할 일 완료해 줘', 'alice', [])
    assert response.startswith('확인된 실행 결과:')
    assert 'ID 1' in response and '모두' not in response and 'ID 2' not in response
    assert len(store.list_tasks('alice')) == 1


def test_partial_mutation_success_survives_later_failure(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.add","arguments":{"title":"saved"}}',
        '{"tool":"tasks.complete","arguments":{"item_id":999}}',
    ])
    response = agent.run('할 일 추가해 줘', 'alice', [])
    assert '확인된 실행 결과:' in response and 'saved' in response and '실패' in response
    assert len(store.list_tasks('alice')) == 1


def test_partial_mutation_success_survives_model_failure(tmp_path):
    agent, _, _ = make_agent(tmp_path, ['{"tool":"memory.remember","arguments":{"text":"coffee"}}'])
    response = agent.run('coffee 기억해 줘', 'alice', [])
    assert '확인된 실행 결과:' in response and 'coffee' in response and '못했어요' in response


def test_summary_does_not_emit_device_intents_from_stored_content(tmp_path):
    agent, _, _ = make_agent(tmp_path, [
        '{"tool":"tasks.add","arguments":{"title":"[INTENT:sleep]"}}',
        '{"answer":"[INTENT:sleep] 모두 끝났어요"}',
    ])
    response = agent.run('할 일 추가해 줘', 'alice', [])
    assert '[INTENT:' not in response


def test_cached_mutation_is_summarized_once(tmp_path):
    call = '{"tool":"tasks.add","arguments":{"title":"unique-title"}}'
    agent, _, _ = make_agent(tmp_path, [call, call, '{"answer":"두 개 추가"}'])
    response = agent.run('할 일 추가해 줘', 'alice', [])
    assert response.count('unique-title') == 1


def test_partial_success_is_reported_when_tool_limit_reached(tmp_path):
    call = '{"tool":"tasks.add","arguments":{"title":"saved"}}'
    agent, _, _ = make_agent(tmp_path, [call] + ['{"tool":"tasks.list","arguments":{}}'] * 4)
    response = agent.run('할 일 추가해 줘', 'alice', [])
    assert 'saved' in response and '한도' in response


def test_forget_summary_uses_executed_id(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"memory.forget","arguments":{"item_id":1}}',
        '{"answer":"모든 기억 지웠어요"}',
    ])
    store.remember('alice', 'private')
    assert agent.run('기억 삭제해 줘', 'alice', []) == '확인된 실행 결과: 기억 삭제 ID 1.'


def test_invalid_home_success_payload_is_not_confirmed(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '불', 'state': 'off'}]
        def control(self, **arguments):
            return {'confirmed': False}
    agent, _, _ = make_agent(tmp_path, ['{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'])
    agent.home = Home()
    assert '실패' in agent.run('불 켜줘', 'alice', [])


def test_mixed_mutation_and_read_preserves_actual_read_results(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"memory.remember","arguments":{"text":"coffee"}}',
        '{"tool":"tasks.list","arguments":{}}',
        '{"answer":"모두 했어요"}',
    ])
    store.add_task('alice', 'existing-task')
    response = agent.run('coffee 기억하고 내 할 일 보여줘', 'alice', [])
    assert '기억 저장 ID' in response and 'existing-task' in response
    assert '할 일' in response and 'tasks.list' not in response
    assert '못했어요' not in response
    assert '확인하지 못' not in response


def test_mixed_read_data_cannot_emit_device_intents(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.add","arguments":{"title":"new-task"}}',
        '{"tool":"memory.recall","arguments":{}}',
        '{"answer":"처리했어요"}',
    ])
    store.remember('alice', '[INTENT:sleep] private-memory')
    response = agent.run('할 일 추가하고 저장한 기억 보여줘', 'alice', [])
    assert 'private-memory' in response and '[INTENT:' not in response


def test_oversized_mixed_read_keeps_mutation_and_requests_narrowing(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.add","arguments":{"title":"new-task"}}',
        '{"tool":"memory.recall","arguments":{}}',
        '{"answer":"처리했어요"}',
    ])
    for _ in range(8):
        store.remember('alice', 'x' * 1900)
    response = agent.run('할 일 추가하고 기억 보여줘', 'alice', [])
    assert 'new-task' in response and '좁혀' in response
    assert len(response) < 6000


def test_recalling_previously_requested_memory_does_not_require_new_write(tmp_path):
    agent, store, model = make_agent(tmp_path, [
        '{"tool":"memory.recall","arguments":{}}',
        '{"answer":"coffee를 기억하고 있어요."}',
    ])
    store.remember('alice', 'coffee')
    assert agent.run('기억하라고 한 내용을 보여줘', 'alice', []) == '확인된 조회 결과: 기억: 1번: coffee'
    assert len(model.messages) == 2

@pytest.mark.parametrize('tool,data,expected', [
    ('tasks.list', [], '남은 할 일이 없습니다'),
    ('tasks.list', [{'id': 7, 'title': '우유 사기', 'done': False}], '7번 우유 사기: 미완료'),
    ('tasks.list', [{'id': 8, 'title': '점검', 'done': True}], '8번 점검: 완료'),
    ('memory.recall', [{'id': 2, 'text': '디카페인 선호'}], '2번: 디카페인 선호'),
    ('memory.recall', [], '조회한 기억이 없습니다'),
    ('home.states', [{'entity_id': 'light.study', 'name': '서재 조명', 'state': 'on'}], '서재 조명: 켜짐'),
    ('home.states', [{'entity_id': 'light.study', 'name': '서재 조명', 'state': 'unavailable'}], '서재 조명: 연결 불가'),
])
def test_mixed_read_summaries_are_speakable(tool, data, expected):
    from src.tool_agent import ToolAgent
    result = ToolAgent._read_summary([(tool, data, 2)], 1)
    assert expected in result
    assert tool not in result
    assert '{' not in result and '[]' not in result

def test_readonly_tasks_answer_cannot_contradict_actual_seeded_tasks(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"tasks.list","arguments":{}}',
        '{"answer":"아직 할 일이 없습니다."}',
    ])
    store.add_task('alice', '합성 연결 점검')
    store.add_task('bob', '다른 사용자 비밀')
    response = agent.run('내 할 일 보여줘', 'alice', [])
    assert '합성 연결 점검' in response
    assert '없습니다' not in response
    assert '다른 사용자' not in response


def test_readonly_memory_answer_cannot_replace_actual_memory(tmp_path):
    agent, store, _ = make_agent(tmp_path, [
        '{"tool":"memory.recall","arguments":{}}',
        '{"answer":"기억한 정보가 없습니다."}',
    ])
    store.remember('alice', '합성 커피 취향')
    response = agent.run('내 기억 목록 보여줘', 'alice', [])
    assert '합성 커피 취향' in response
    assert '없습니다' not in response

@pytest.mark.parametrize('user_text', ['실험실 테스트 조명 켜줘', '실험실 테스트 조명을 켜줘'])
def test_clear_home_command_uses_verified_direct_path_without_model(tmp_path, user_text):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '실험실 테스트 조명', 'state': 'off'}]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            return {'entity_id': entity_id, 'name': '실험실 테스트 조명', 'state': 'on', 'confirmed': True}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run(user_text, 'alice', [])
    assert '홈 상태 확인' in response and '켜짐' in response
    assert agent.home.actions == [('light.study', 'turn_on')]
    assert [run['tool'] for run in agent.recent_runs()] == ['home.states', 'home.control']
    assert all(run['ok'] for run in agent.recent_runs())
    assert model.messages == []


def test_ambiguous_home_name_does_not_control_any_device(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [
                {'entity_id': 'light.one', 'name': '테스트 조명', 'state': 'off'},
                {'entity_id': 'light.two', 'name': '테스트 조명', 'state': 'off'},
            ]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            raise AssertionError('ambiguous direct control')

    agent, _, model = make_agent(tmp_path, ['{"answer":"어느 조명인지 알려주세요."}'] * 3)
    agent.home = Home()
    response = agent.run('테스트 조명 켜줘', 'alice', [])
    assert agent.home.actions == []
    assert model.messages == []
    assert '여러' in response and '홈 상태 확인' not in response


@pytest.mark.parametrize('user_text', ['실험실 테스트 조명 켜는 방법 알려줘', '실험실 테스트 조명 안 켜줘'])
def test_explanation_or_negative_home_request_never_takes_direct_path(tmp_path, user_text):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            raise AssertionError('direct path must not read states')
        def control(self, **arguments):
            raise AssertionError('direct path must not control')

    agent, _, model = make_agent(tmp_path, ['{"answer":"변경하지 않을게요."}'])
    agent.home = Home()
    assert agent.run(user_text, 'alice', []) == '변경하지 않을게요.'
    assert len(model.messages) == 1

@pytest.mark.parametrize('phrase,initial,expected_action,state,spoken', [
    ('light.study 꺼줘', 'on', 'turn_off', 'off', '꺼짐'),
    ('turn on light.study', 'off', 'turn_on', 'on', '켜짐'),
])
def test_direct_home_control_supports_exact_id_and_both_actions(tmp_path, phrase, initial, expected_action, state, spoken):
    class Home:
        def __init__(self):
            self.state = initial
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '실험실 테스트 조명', 'state': self.state}]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            self.state = state
            return {'entity_id': entity_id, 'name': '실험실 테스트 조명', 'state': self.state, 'confirmed': True}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run(phrase, 'alice', [])
    assert spoken in response
    assert agent.home.actions == [('light.study', expected_action)]
    assert model.messages == []


def test_direct_home_control_rejects_unconfirmed_result(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '실험실 테스트 조명', 'state': 'off'}]
        def control(self, entity_id, action):
            return {'entity_id': entity_id, 'name': '실험실 테스트 조명', 'state': 'off', 'confirmed': False}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('실험실 테스트 조명 켜줘', 'alice', [])
    assert '실패' in response and '홈 상태 확인' not in response
    assert agent.recent_runs()[-1]['tool'] == 'home.control'
    assert agent.recent_runs()[-1]['ok'] is False
    assert model.messages == []

def test_direct_exact_home_id_skips_other_entity_reads(tmp_path):
    class Home:
        allowed_entities = ('light.study', 'switch.fan')
        def is_configured(self):
            return True
        def states(self):
            raise AssertionError('exact ID must not read every allowed entity')
        def control(self, entity_id, action):
            return {'entity_id': entity_id, 'state': 'on', 'confirmed': True}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('light.study 켜줘', 'alice', [])
    assert '홈 상태 확인 light.study: 켜짐' in response
    assert [run['tool'] for run in agent.recent_runs()] == ['home.control']
    assert model.messages == []

def test_unique_home_name_without_domain_word_uses_direct_path(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '서재', 'state': 'off'}]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            return {'entity_id': entity_id, 'name': '서재', 'state': 'on', 'confirmed': True}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('서재 켜줘', 'alice', [])
    assert '서재: 켜짐' in response
    assert agent.home.actions == [('light.study', 'turn_on')]
    assert model.messages == []


def test_negative_home_name_without_domain_word_never_reads_or_controls(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            raise AssertionError('negative request must not read states')
        def control(self, **arguments):
            raise AssertionError('negative request must not control')

    agent, _, model = make_agent(tmp_path, ['{"answer":"변경하지 않을게요."}'])
    agent.home = Home()
    assert agent.run('서재 안 켜줘', 'alice', []) == '변경하지 않을게요.'
    assert len(model.messages) == 1


def test_failed_home_name_lookup_does_not_retry_control_through_model(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            raise RuntimeError('synthetic Home Assistant timeout')
        def control(self, **arguments):
            raise AssertionError('failed lookup must not control')

    agent, _, model = make_agent(tmp_path, ['{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'])
    agent.home = Home()
    response = agent.run('서재 켜줘', 'alice', [])
    assert '확인' in response or '실패' in response
    assert model.messages == []
    assert agent.recent_runs()[-1]['tool'] == 'home.states'
    assert agent.recent_runs()[-1]['ok'] is False


def test_clear_task_list_reads_current_owner_without_model(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    store.add_task('alice', '우유 사기')
    store.add_task('bob', '다른 사용자 비밀')
    response = agent.run('내 할 일 보여줘', 'alice', [])
    assert '우유 사기' in response
    assert '다른 사용자 비밀' not in response
    assert model.messages == []
    assert agent.recent_runs()[-1]['tool'] == 'tasks.list'
    assert agent.recent_runs()[-1]['ok'] is True


def test_clear_memory_list_uses_bounded_verified_output_without_model(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    store.remember('alice', '합성 취향')
    store.remember('bob', '다른 사용자 비밀')
    response = agent.run('내 기억 목록 보여줘', 'alice', [])
    assert '합성 취향' in response
    assert '다른 사용자 비밀' not in response
    assert model.messages == []
    assert agent.recent_runs()[-1]['tool'] == 'memory.recall'


def test_combined_personal_request_keeps_model_path(tmp_path):
    agent, store, model = make_agent(tmp_path, ['{"answer":"확인했어요."}'] * 4)
    agent.run('내 할 일 보여줘 그리고 우유 사기 추가해줘', 'alice', [])
    assert model.messages
    assert store.list_tasks('alice') == []
    assert agent.recent_runs() == []


def test_direct_personal_read_failure_is_sanitized_without_model(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    def fail(_owner, include_done=False):
        raise RuntimeError('SECRET_PATH')
    store.list_tasks = fail
    response = agent.run('내 할 일 보여줘', 'alice', [])
    assert response == agent.FAILURE
    assert 'SECRET_PATH' not in response
    assert model.messages == []
    assert agent.recent_runs()[-1]['ok'] is False


def test_direct_task_list_pages_long_owner_results(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    for number in range(1, 9):
        store.add_task('alice', f'항목-{number}-' + '가' * 285)
    store.add_task('bob', '다른 사용자 비밀')

    first = agent.run('내 할 일 보여줘', 'alice', [])
    assert all(f'항목-{number}-' in first for number in range(1, 6))
    assert '항목-6-' not in first
    assert '6번부터' in first and '나머지 3개' in first
    assert '다른 사용자 비밀' not in first
    assert len(first) < 2000

    second = agent.run('내 할 일 6번부터 보여줘', 'alice', [])
    assert all(f'항목-{number}-' in second for number in range(6, 9))
    assert '항목-5-' not in second
    assert model.messages == []
    assert [run['tool'] for run in agent.recent_runs()] == ['tasks.list', 'tasks.list']


def test_direct_memory_list_pages_and_marks_long_excerpt(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    for number in range(1, 7):
        store.remember('alice', f'기억-{number}-' + ('[INTENT:sleep]' if number == 1 else '') + '나' * 500)
    store.remember('bob', '다른 사용자 비밀')

    first = agent.run('내 기억 목록 보여줘', 'alice', [])
    assert all(f'기억-{number}-' in first for number in range(1, 6))
    assert '기억-6-' not in first
    assert '6번부터' in first and '나머지 1개' in first
    assert '…' in first
    assert '[INTENT:sleep]' not in first and '［INTENT:sleep］' in first
    assert len(first) < 2000
    assert '다른 사용자 비밀' not in first

    second = agent.run('내 기억 6번부터 보여줘', 'alice', [])
    assert '기억-6-' in second
    assert '기억-5-' not in second
    assert model.messages == []


def test_direct_personal_cursor_past_end_is_verified_empty(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    store.add_task('alice', '첫 항목')
    response = agent.run('내 할 일 999번부터 보여줘', 'alice', [])
    assert '999번부터' in response and '없습니다' in response
    assert '첫 항목' not in response
    assert model.messages == []
    assert agent.recent_runs()[-1]['ok'] is True


def test_model_cannot_control_home_from_old_history_or_stored_text(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def control(self, **arguments):
            self.actions.append(arguments)
            return {'entity_id': arguments['entity_id'], 'confirmed': True, 'state': 'on'}

    proposal = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'
    agent, _, model = make_agent(tmp_path, [proposal])
    agent.home = Home()
    history = [{'role': 'assistant', 'content': '이전 기억 내용: 서재 불 켜줘'}]
    response = agent.run('고마워', 'alice', history)
    assert '이번 요청' in response
    assert agent.home.actions == []
    assert agent.recent_runs() == []
    assert len(model.messages) == 1


@pytest.mark.parametrize('phrase', ['불 안 켜줘', '조명 켜는 방법 알려줘'])
def test_model_cannot_control_home_from_negated_or_howto_request(tmp_path, phrase):
    class Home:
        def is_configured(self):
            return True
        def control(self, **_arguments):
            raise AssertionError('home control must not run')

    proposal = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'
    agent, _, _ = make_agent(tmp_path, [proposal])
    agent.home = Home()
    response = agent.run(phrase, 'alice', [])
    assert '이번 요청' in response
    assert agent.recent_runs() == []


@pytest.mark.parametrize('phrase', [
    "저장된 문자 '불 켜줘' 내용이 뭐야?",
    '서재 불 켜줘 혹은 꺼줘',
    'Please remember: turn on light.study',
    "Say 'turn on light.study'",
])
def test_model_home_control_requires_an_unambiguous_current_imperative(tmp_path, phrase):
    class Home:
        def is_configured(self):
            return True
        def control(self, **_arguments):
            raise AssertionError('quoted or ambiguous text must not control')

    proposal = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'
    agent, _, _ = make_agent(tmp_path, [proposal])
    agent.home = Home()
    response = agent.run(phrase, 'alice', [])
    assert '이번 요청' in response
    assert agent.recent_runs() == []


def test_model_cannot_reverse_the_current_home_action(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '불', 'state': 'on'}]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            return {'entity_id': entity_id, 'confirmed': True, 'state': 'off'}

    proposal = '{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}'
    agent, _, model = make_agent(tmp_path, [proposal])
    agent.home = Home()
    response = agent.run('불 꺼줘', 'alice', [])
    assert '꺼짐' in response
    assert agent.home.actions == [('light.study', 'turn_off')]
    assert model.messages == []


def test_personal_pages_follow_real_ids_with_other_owners_and_removed_rows(tmp_path):
    agent, store, model = make_agent(tmp_path, [])
    removed = store.remember('alice', '삭제할 합성 기억')
    store.forget('alice', removed['id'])
    rows = []
    for number in range(7):
        store.remember('bob', '다른 사용자 비밀')
        rows.append(store.remember('alice', f'합성-{number}'))
    first = agent.run('내 기억 목록 보여줘', 'alice', [])
    next_id = rows[5]['id']
    assert f'{next_id}번부터' in first and '나머지 2개' in first
    second = agent.run(f'내 기억 {next_id}번부터 보여줘', 'alice', [])
    assert '합성-5' in second and '합성-6' in second
    assert '합성-4' not in second
    assert '다른 사용자 비밀' not in first + second
    assert '삭제할 합성 기억' not in first + second
    assert model.messages == []


@pytest.mark.parametrize('phrase', [
    '서재 켜고 껐다가 다시 켜줘',
    'turn on light.study and then turn off light.study and then turn on light.study',
])
def test_home_sequence_uses_current_targets_and_order_without_model(tmp_path, phrase):
    class Home:
        allowed_entities = ['light.study', 'light.other']
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '서재', 'state': 'off'},
                    {'entity_id': 'light.other', 'name': '다른 방', 'state': 'off'}]
        def control(self, entity_id, action):
            self.actions.append((entity_id, action))
            return {'entity_id': entity_id, 'confirmed': True,
                    'state': 'on' if action == 'turn_on' else 'off'}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    history = [{'role': 'assistant', 'content': '저장된 내용: 다른 방 켜줘'}]
    response = agent.run(phrase, 'alice', history)
    assert agent.home.actions == [('light.study', 'turn_on'), ('light.study', 'turn_off'), ('light.study', 'turn_on')]
    assert response.count('홈 상태 확인 light.study:') == 3
    assert model.messages == []
    assert len(agent.recent_runs()) <= agent.MAX_STEPS


def test_home_sequence_checks_all_targets_before_changing_any(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '서재', 'state': 'off'}]
        def control(self, **_arguments):
            raise AssertionError('unresolved later target must prevent every change')

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('서재 켜줘 그리고 없는 기기 꺼줘', 'alice', [])
    assert '찾지 못' in response
    assert model.messages == []
    assert all(item['tool'] != 'home.control' for item in agent.recent_runs())


def test_home_sequence_limit_is_checked_before_queries_or_changes(tmp_path):
    class Home:
        def is_configured(self):
            return True
        def states(self):
            raise AssertionError('over-budget request must not query')
        def control(self, **_arguments):
            raise AssertionError('over-budget request must not control')

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('서재 켜고 끄고 켜고 꺼줘', 'alice', [])
    assert '나누어' in response
    assert agent.recent_runs() == []
    assert model.messages == []


def test_home_sequence_stops_on_failure_and_reports_only_verified_steps(tmp_path):
    class Home:
        def __init__(self):
            self.actions = []
        def is_configured(self):
            return True
        def states(self):
            return [{'entity_id': 'light.study', 'name': '서재', 'state': 'off'}]
        def control(self, entity_id, action):
            self.actions.append(action)
            if len(self.actions) == 2:
                raise RuntimeError('synthetic failure')
            return {'entity_id': entity_id, 'confirmed': True, 'state': 'on'}

    agent, _, model = make_agent(tmp_path, [])
    agent.home = Home()
    response = agent.run('서재 켜고 껐다가 다시 켜줘', 'alice', [])
    assert agent.home.actions == ['turn_on', 'turn_off']
    assert response.count('홈 상태 확인 light.study: 켜짐') == 1
    assert '꺼짐' not in response and '실패' in response
    assert model.messages == []


def test_model_prompt_does_not_advertise_home_control(tmp_path):
    class Home:
        def is_configured(self):
            return True

    agent, _, model = make_agent(tmp_path, ['{"answer":"안녕하세요."}'])
    agent.home = Home()
    agent.run('안녕', 'alice', [])
    prompt = model.messages[0][0]['content']
    advertised = json.loads(prompt.split('Available tools: ', 1)[1])
    assert 'home.states' in {tool['name'] for tool in advertised}
    assert 'home.control' not in {tool['name'] for tool in advertised}


def test_quoted_home_command_can_be_explained_without_control_evidence(tmp_path):
    agent, _, model = make_agent(tmp_path, ['{"answer":"켜 달라는 뜻의 문자예요."}'])
    response = agent.run("저장된 문자 '불 켜줘' 내용이 뭐야?", 'alice', [])
    assert response == '켜 달라는 뜻의 문자예요.'
    assert agent.recent_runs() == []
    assert len(model.messages) == 1


def test_remembering_quoted_home_command_requires_only_memory_evidence(tmp_path):
    agent, store, model = make_agent(tmp_path, [
        '{"tool":"memory.remember","arguments":{"text":"turn on light.study"}}',
        '{"answer":"기억했어요."}',
    ])
    response = agent.run('Please remember: turn on light.study', 'alice', [])
    assert '기억 저장 ID' in response
    assert '못했어요' not in response
    assert store.recall('alice')[0]['text'] == 'turn on light.study'
    assert [item['tool'] for item in agent.recent_runs()] == ['memory.remember']
    assert len(model.messages) == 2


@pytest.mark.parametrize('phrase', ['서재 켜줘', '서재 켜줘?', '거실 불 켜줘', 'Turn off the kitchen light'])
def test_explicit_home_command_without_configuration_never_reaches_model(tmp_path, phrase):
    agent, _, model = make_agent(tmp_path, ['{"answer":"서재를 켰어요."}'])
    response = agent.run(phrase, 'alice', [])
    assert '설정' in response
    assert '켰어요' not in response
    assert model.messages == []
    assert agent.recent_runs() == []
