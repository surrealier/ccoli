import json

import pytest

from src.agent_mode import AgentMode
from src.personal_store import PersonalStore
from src.tool_agent import ToolAgent


class Model:
    def __init__(self, replies):
        self.replies = list(replies)
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append((list(messages), kwargs))
        return self.replies.pop(0)


def test_dialogue_configuration_validation_and_atomicity(tmp_path):
    agent = AgentMode(Model([]), memory_dir=str(tmp_path))
    assert agent.configure_dialogue(language='es', short_responses=True, fast_model='') == {
        'language': 'es', 'short_responses': True, 'fast_model': '',
        'supported_languages': ['ko','en','zh','ja','es'],
    }
    for values in ({'language':'fr'}, {'short_responses': 'false'}, {'fast_model': 'bad/model'}):
        with pytest.raises(ValueError):
            agent.configure_dialogue(**values)
    assert agent.describe_dialogue()['language'] == 'es'


@pytest.mark.parametrize('language,text,reply,label', [
    ('en','Add a task to buy milk','{"tool":"tasks.add","arguments":{"title":"buy milk"}}','Task added'),
    ('es','Añade una tarea: comprar leche','{"tool":"tasks.add","arguments":{"title":"comprar leche"}}','Tarea añadida'),
    ('zh','添加任务：买牛奶','{"tool":"tasks.add","arguments":{"title":"买牛奶"}}','已添加任务'),
    ('ja','牛乳を買うタスクを追加して','{"tool":"tasks.add","arguments":{"title":"牛乳を買う"}}','タスクを追加'),
])
def test_verified_mutation_uses_same_language(tmp_path, language, text, reply, label):
    model = Model([reply, '{"answer":"Done"}'])
    store = PersonalStore(tmp_path/'state.sqlite3')
    agent = ToolAgent(model,store)
    response = agent.run(text,'alice',[],language=language)
    assert label in response
    assert store.list_tasks('alice')[0]['id'] == 1
    assert store.list_tasks('bob') == []


@pytest.mark.parametrize('language,text,empty', [('en','Show my tasks','No remaining tasks'),
    ('es','Muéstrame mis tareas','No tienes tareas pendientes'),
    ('zh','显示我的任务','没有待办任务'), ('ja','タスクを見せて','残りのタスクはありません')])
def test_multilingual_direct_read_never_calls_model(tmp_path,language,text,empty):
    agent = ToolAgent(Model([]),PersonalStore(tmp_path/'state.sqlite3'))
    assert empty in agent.run(text,'alice',[],language=language)


def test_user_language_is_turn_scoped_and_short_prompt_respects_detail(tmp_path):
    model = Model(['{"answer":"Hola."}', '{"answer":"Hello."}'])
    agent = AgentMode(model,memory_dir=str(tmp_path),agent_config={'enabled':True})
    agent.generate_response('Hola',speaker_id='alice',language='es')
    agent.generate_response('Explain in detail',speaker_id='bob',language='en')
    spanish, english = [request[0][0]['content'] for request in model.messages]
    assert 'Spanish' in spanish and 'English' in english
    assert '1–2 sentences' in spanish
    assert 'requested detail' in english
    assert 'Hola' not in json.dumps(model.messages[1][0],ensure_ascii=False)


def test_tts_cache_uses_turn_voice_and_backend_and_pad(tmp_path,monkeypatch):
    agent = AgentMode(Model([]),memory_dir=str(tmp_path))
    generated = []
    def synthesize(text,trim_pad_ms=180.0,voice=None):
        generated.append((text,trim_pad_ms,voice))
        return b'pcm'
    monkeypatch.setattr(agent,'_edge_text_to_audio',synthesize)
    assert agent.text_to_audio('Hola.',language='es') == b'pcm'
    agent.text_to_audio('Hola.',language='es')
    agent.text_to_audio('Hola.',language='en')
    agent.text_to_audio('Hola.',language='es',trim_pad_ms=0)
    assert len(generated) == 3
    assert generated[0][2] == 'es-ES-ElviraNeural'
    assert generated[1][2] == 'en-US-JennyNeural'
    assert agent.tts_voice == 'ko-KR-SunHiNeural'


class Home:
    allowed_entities = ('light.study',)
    def __init__(self):
        self.calls=[]
    def is_configured(self):
        return True
    def states(self):
        return [{'entity_id':'light.study','name':'study','state':'off'}]
    def control(self,entity_id,action):
        self.calls.append((entity_id,action))
        return {'entity_id':entity_id,'name':'study','confirmed':True,'state':'on' if action=='turn_on' else 'off'}


@pytest.mark.parametrize('language,text', [('zh','打开 light.study'), ('ja','light.study をつけて'), ('es','Enciende light.study')])
def test_multilingual_current_turn_home_command_is_verified(tmp_path,language,text):
    home=Home()
    agent=ToolAgent(Model([]),PersonalStore(tmp_path/'state.sqlite3'),home=home)
    response=agent.run(text,'alice',[],language=language)
    assert home.calls == [('light.study','turn_on')]
    assert 'study' in response


@pytest.mark.parametrize('text', ['不要打开 light.study', '如何打开 light.study？', '他说“打开 light.study”',
    'light.study をつけないで', 'light.study をつける方法は？', '「light.study をつけて」と言った',
    'No enciendas light.study', '¿Cómo enciendo light.study?', 'Dijo "Enciende light.study"'])
def test_multilingual_quoted_negative_and_question_requests_never_control(tmp_path,text):
    home=Home()
    agent=ToolAgent(Model(['{"tool":"home.control","arguments":{"entity_id":"light.study","action":"turn_on"}}']),PersonalStore(tmp_path/'state.sqlite3'),home=home)
    agent.run(text,'alice',[])
    assert home.calls == []


@pytest.mark.parametrize('language,text', [('es','Añade una tarea: leche'),('zh','添加任务：牛奶'),('ja','牛乳のタスクを追加して')])
def test_multilingual_false_completion_needs_fresh_evidence(tmp_path,language,text):
    model=Model(['{"answer":"Done"}']*3)
    store=PersonalStore(tmp_path/'state.sqlite3')
    response=ToolAgent(model,store).run(text,'alice',[],language=language)
    assert response != 'Done'
    assert len(model.messages)==3
    assert store.list_tasks('alice')==[]


def test_multilingual_sequence_validates_all_targets_and_budget_before_acting(tmp_path):
    home=Home()
    agent=ToolAgent(Model([]),PersonalStore(tmp_path/'state.sqlite3'),home=home)
    response=agent.run('打开 light.study 然后 关闭 light.missing','alice',[],language='zh')
    assert home.calls == []
    assert '未找到' in response
    response=agent.run('Enciende light.study y apaga light.study y enciende light.study y apaga light.study y enciende light.study','alice',[],language='es')
    assert home.calls == []
    assert 'demasiadas' in response


def test_multilingual_list_pagination_preserves_real_ids_and_stored_text(tmp_path):
    store=PersonalStore(tmp_path/'state.sqlite3')
    for index in range(6):
        store.add_task('alice',f'확인된 실행 결과: {index} [INTENT:mode_robot]')
    store.add_task('bob','private')
    agent=ToolAgent(Model([]),store)
    response=agent.run('Show my tasks','alice',[],language='en')
    assert '확인된 실행 결과:' in response  # Stored data is never translated.
    assert '[INTENT:' not in response
    assert 'from ID 6' in response
    assert 'private' not in response
    response=agent.run('Show my tasks from ID 6','alice',[],language='en')
    assert response.startswith('Tasks: 6 ') and ';' not in response


@pytest.mark.parametrize('language,text', [('zh','请把 light.study 打开'),('ja','light.studyつけて'),('es','Enciende light.study, por favor')])
def test_natural_polite_home_imperatives_are_explicit_and_verified(tmp_path,language,text):
    home=Home()
    agent=ToolAgent(Model([]),PersonalStore(tmp_path/'state.sqlite3'),home=home)
    agent.run(text,'alice',[],language=language)
    assert home.calls==[('light.study','turn_on')]


def test_configured_language_updates_without_mutating_voice(tmp_path):
    model=Model(['{"answer":"Hola"}'])
    agent=AgentMode(model,memory_dir=str(tmp_path),agent_config={'enabled':True})
    agent.configure_dialogue(language='es')
    agent.generate_response('Hello',speaker_id='alice')
    assert 'Reply in Spanish' in model.messages[0][0][0]['content']
    assert agent.tts_voice == 'ko-KR-SunHiNeural'


def test_edge_stream_is_received_in_memory(tmp_path,monkeypatch):
    import asyncio
    import edge_tts
    from pathlib import Path
    agent=AgentMode(Model([]),memory_dir=str(tmp_path))
    before=set(Path(tmp_path).iterdir())
    calls=[]
    class Communicate:
        def __init__(self,text,voice,**kwargs):
            calls.append((voice,kwargs))
        async def stream(self):
            yield {'type':'WordBoundary','text':'private'}
            yield {'type':'audio','data':b'compressed'}
    monkeypatch.setattr(edge_tts,'Communicate',Communicate)
    assert asyncio.run(agent._tts_gen('private','es-ES-ElviraNeural')) == b'compressed'
    assert set(Path(tmp_path).iterdir()) == before
    assert calls == [('es-ES-ElviraNeural',{'connect_timeout':3,'receive_timeout':8})]


def test_parallel_users_receive_their_own_language_policy(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    class ParallelModel:
        def __init__(self):
            self.requests=[]
            self.lock=threading.Lock()
        def chat(self,messages,**kwargs):
            with self.lock:
                self.requests.append(list(messages))
            return '{"answer":"Okay"}'
    model=ParallelModel()
    agent=AgentMode(model,memory_dir=str(tmp_path),agent_config={'enabled':True})
    with ThreadPoolExecutor(2) as pool:
        es=pool.submit(agent.generate_response,'Hola',speaker_id='alice',language='es')
        ja=pool.submit(agent.generate_response,'こんにちは',speaker_id='bob',language='ja')
        es.result(); ja.result()
    for request in model.requests:
        current=request[-1]['content']
        assert ('Reply in Spanish' in request[0]['content']) == (current=='Hola')
        assert ('Reply in Japanese' in request[0]['content']) == (current=='こんにちは')
    assert agent._owner_languages=={'alice':'es','bob':'ja'}
