from src.llm_client import LLMClient, PriorityLLMClient
from src.runtime_preferences import RuntimePreferences


def test_gemini_lite_uses_supported_minimal_thinking(monkeypatch):
    captured=[]
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Hello'}]}}]}
    def post(url,**kwargs):
        captured.append(kwargs['json'])
        return Response()
    monkeypatch.setattr('src.llm_client.requests.post',post)
    assert LLMClient('', 'gemini-3.5-flash-lite',provider='gemini',api_key='synthetic').chat([]) == 'Hello'
    assert captured[0]['generationConfig']['thinkingConfig'] == {'thinkingLevel':'minimal'}


def test_fast_client_does_not_change_normal_active_model_and_falls_back(monkeypatch):
    cfg={'provider':'gemini','priority':['api'],'api_priority':['gemini'],
         'gemini_api_key':'synthetic','api_models':{'gemini':'gemini-3.8-flash'}}
    client=PriorityLLMClient(cfg,RuntimePreferences.from_mapping({'llm':cfg}))
    calls=[]
    replies=['normal','fast','','fallback']
    def chat(self,messages,**kwargs):
        calls.append(self.model)
        return replies.pop(0)
    monkeypatch.setattr(LLMClient,'chat',chat)
    assert client.chat([]) == 'normal'
    previous=dict(client.active_candidate)
    assert client.chat_fast([],model='gemini-3.5-flash-lite') == 'fast'
    assert client.active_candidate == previous
    assert client.chat_fast([],model='gemini-3.5-flash-lite') == 'fallback'
    assert calls == ['gemini-3.8-flash','gemini-3.5-flash-lite','gemini-3.5-flash-lite','gemini-3.8-flash']


def test_raised_fast_provider_failure_uses_primary_without_exposing_exception(monkeypatch):
    cfg={'provider':'gemini','priority':['api'],'api_priority':['gemini'],'gemini_api_key':'synthetic'}
    client=PriorityLLMClient(cfg,RuntimePreferences.from_mapping({'llm':cfg}))
    def chat(self,messages,**kwargs):
        if self.model=='gemini-3.5-flash-lite':
            raise RuntimeError('SECRET_PROVIDER_ERROR')
        return 'fallback'
    monkeypatch.setattr(LLMClient,'chat',chat)
    assert client.chat_fast([],model='gemini-3.5-flash-lite')=='fallback'
    assert 'SECRET' not in client.last_error
