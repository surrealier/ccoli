#!/usr/bin/env python3
"""At most twenty real provider attempts, using only checked-in public scenarios."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time
from typing import Callable

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from src.dialogue_policy import conversation_instructions,detect_language,voice_for_language

DEFAULT_MODELS=['gemini-3.8-flash','gemini-3.5-flash-lite']
MAX_PROVIDER_ATTEMPTS=20


def public_cases() -> list[dict]:
    examples={
        'ko':('고양이는 왜 가르랑거려?', '초보자가 화분에 물을 주는 방법을 세 단계로 자세히 알려줘.',
              '파란 화분 확인','파란 화분 확인이라는 할 일을 추가해 줘.'),
        'en':('Why do cats purr?', 'Explain in detail, in three steps, how a beginner waters a houseplant.',
              'Check the blue plant pot','Add a task titled Check the blue plant pot.'),
        'zh':('猫为什么会呼噜？', '请详细分三步说明新手如何给盆栽浇水。',
              '检查蓝色花盆','添加一个名为检查蓝色花盆的任务。'),
        'ja':('猫はどうして喉を鳴らすの？', '初心者が鉢植えに水をあげる方法を三つの手順で詳しく説明して。',
              '青い植木鉢を確認','青い植木鉢を確認というタスクを追加して。'),
        'es':('¿Por qué ronronean los gatos?', 'Explica en detalle, en tres pasos, cómo regar una planta de interior.',
              'Revisar la maceta azul','Añade una tarea titulada Revisar la maceta azul.'),
    }
    rows=[]
    for language,(ordinary,detail,title,tool_request) in examples.items():
        rows.append({'id':f'{language}-ordinary','language':language,'category':'ordinary','prompt':ordinary})
        rows.append({'id':f'{language}-detail-tool','language':language,'category':'detail_tool',
                     'prompt':detail,'title':title,'tool_request':tool_request})
    return rows


def validate_models(models: list[str]) -> list[str]:
    if (not isinstance(models,list) or not 1<=len(models)<=2 or len(set(models))!=len(models)
            or any(not isinstance(model,str) or not re.fullmatch(r'gemini-[A-Za-z0-9][A-Za-z0-9_.:-]{0,80}',model) for model in models)):
        raise ValueError('Choose one or two distinct Gemini model IDs')
    if len(models)*len(public_cases())>MAX_PROVIDER_ATTEMPTS:
        raise ValueError('The benchmark would exceed twenty provider attempts')
    return list(models)


def messages_for(row: dict) -> list[dict]:
    policy=conversation_instructions(row['language'],True,row['prompt'])
    if row['category']=='ordinary':
        return [{'role':'system','content':'You are ccoli, a personal home assistant. '+policy},
                {'role':'user','content':row['prompt']}]
    instructions=(policy+' This is a public synthetic evaluation with two independent requests. '
        'Return exactly one JSON object with keys detail and tool. detail is an array of exactly '
        'three useful explanatory strings answering the first request in the selected language. '
        'tool is only the plan for the second request, shaped {"tool":"tasks.add","arguments":{"title":"exact title"}}. '
        'Preserve the exact title. No owner, IDs, other keys, markdown fences or claims that the task has already been added. '
        'No tool is executed by this provider request.')
    content=json.dumps({'first_request':row['prompt'],'second_request':row['tool_request'],
                        'exact_title':row['title']},ensure_ascii=False)
    return [{'role':'system','content':instructions},{'role':'user','content':content}]


def _brief(text: str,language: str) -> bool:
    return len(text)<=160 if language in ('ko','zh','ja') else len(text.split())<=40


def assess(row: dict,text: str) -> dict:
    metrics={'nonempty':bool(text.strip()),'language_heuristic_matches':False,
             'brief':None,'json_valid':None,'tool_schema_correct':None,
             'detail_requested_respected':None}
    if row['category']=='ordinary':
        metrics['language_heuristic_matches']=bool(text.strip()) and detect_language(text)==row['language']
        metrics['brief']=_brief(text,row['language']) and bool(text.strip())
        return metrics
    try:
        value=json.loads(text)
    except (json.JSONDecodeError,TypeError):
        metrics.update(json_valid=False,tool_schema_correct=False,detail_requested_respected=False)
        return metrics
    metrics['json_valid']=isinstance(value,dict) and set(value)=={'detail','tool'}
    detail=value.get('detail') if isinstance(value,dict) else None
    valid_detail=isinstance(detail,list) and len(detail)==3 and all(isinstance(step,str) and len(step.strip())>=10 for step in detail)
    metrics['detail_requested_respected']=valid_detail
    expected={'tool':'tasks.add','arguments':{'title':row['title']}}
    metrics['tool_schema_correct']=isinstance(value,dict) and value.get('tool')==expected
    if valid_detail:
        metrics['language_heuristic_matches']=detect_language(' '.join(detail))==row['language']
    return metrics


def latency_stats(values: list[float]) -> dict:
    if not values:
        return {'sample_count':0,'p50_ms':None,'p95_ms':None}
    ordered=sorted(values)
    return {'sample_count':len(values),'p50_ms':round(statistics.median(values),2),
            'p95_ms':round(ordered[max(0,math.ceil(.95*len(ordered))-1)],2)}


def run_cloud(models: list[str],requester: Callable,*,provenance: str='provider_responses') -> dict:
    models=validate_models(models)
    reports={model:[] for model in models}
    attempts=0
    # Interleave models per public scenario to reduce time-of-day bias; no retries or fallback.
    for row in public_cases():
        for model in models:
            started=time.perf_counter(); attempts+=1
            try:
                result=requester(model,messages_for(row),768 if row['category']=='detail_tool' else 384)
                text=result.get('text','')
                if not isinstance(text,str):
                    raise ValueError('invalid response type')
                error_code=result.get('error_code')
                finish_reason=result.get('finish_reason','')
            except Exception:
                text=''; finish_reason=''; error_code='provider_request_failed'
            duration=(time.perf_counter()-started)*1000
            reports[model].append({'case_id':row['id'],'language':row['language'],'category':row['category'],
                'prompt':row['prompt'],'response':text,'latency_ms':round(duration,2),
                'error_code':error_code,'finish_reason':finish_reason,'metrics':assess(row,text)})
    output=[]
    for model,rows in reports.items():
        successful=[row for row in rows if not row['error_code'] and row['metrics']['nonempty']]
        output.append({'model':model,'latency':latency_stats([row['latency_ms'] for row in rows]),
            'successful_latency':latency_stats([row['latency_ms'] for row in successful]),
            'ordinary_latency':latency_stats([row['latency_ms'] for row in rows if row['category']=='ordinary']),
            'compound_detail_tool_latency':latency_stats([row['latency_ms'] for row in rows if row['category']=='detail_tool']),
            'success_count':len(successful),'rows':rows})
    return {'schema_version':1,'provenance':provenance,'attempts':attempts,'maximum_attempts':20,
            'models':output,'input_source':'checked_in_public_synthetic',
            'auto_retry':False,'provider_fallback':False,'human_quality_review_required':True,
            'physical_or_external_actions_executed':False,'model_selection_changed':False}


def local_paths() -> dict:
    from src.personal_store import PersonalStore
    from src.tool_agent import ToolAgent
    from src.agent_mode import AgentMode
    from src.dialogue_policy import AudioCache
    class NoModel:
        calls=0
        def chat(self,*args,**kwargs):
            self.calls+=1
            raise AssertionError('Direct path should never call an LLM')
    direct=[]
    reads={'ko':'내 할 일 보여줘','en':'Show my tasks','zh':'显示我的任务',
           'ja':'タスクを見せて','es':'Muéstrame mis tareas'}
    with tempfile.TemporaryDirectory(prefix='ccoli-public-benchmark-') as directory:
        store=PersonalStore(Path(directory)/'fixture.sqlite3')
        store.add_task('public-owner','PUBLIC FIXTURE ONE')
        store.add_task('other-public-owner','OTHER PUBLIC FIXTURE')
        for language,request in reads.items():
            model=NoModel(); agent=ToolAgent(model,store)
            started=time.perf_counter()
            response=agent.run(request,'public-owner',[],language=language)
            direct.append({'language':language,'latency_ms':round((time.perf_counter()-started)*1000,3),
                'response':response,'direct_model_calls':model.calls,
                'owner_isolation':'PUBLIC FIXTURE ONE' in response and 'OTHER PUBLIC FIXTURE' not in response})
    cache_rows=[]
    for language in reads:
        agent=AgentMode.__new__(AgentMode)
        agent.tts_voice='ko-KR-SunHiNeural'; agent.tts_backend='synthetic_fixture'
        agent.gemini_tts=None; agent._dialogue={'language':'auto'}; agent._audio_cache=AudioCache()
        generated=[]
        def synthesize(text,trim_pad_ms=180,voice=None):
            generated.append(voice)
            return b'\x00\x00'*160
        agent._edge_text_to_audio=synthesize
        text='PUBLIC AUDIO FIXTURE'
        started=time.perf_counter(); first=agent.text_to_audio(text,language=language)
        cold=(time.perf_counter()-started)*1000
        hits=[]
        for _ in range(5):
            started=time.perf_counter()
            assert agent.text_to_audio(text,language=language)==first
            hits.append((time.perf_counter()-started)*1000)
        count=len(generated)
        other='en' if language!='en' else 'ko'
        agent.text_to_audio(text,language=other)
        cache_rows.append({'language':language,'voice':voice_for_language(language),
            'cold_dispatch_ms':round(cold,3),'warm_dispatch':latency_stats(hits),
            'synthesis_count':count,'voice_change_misses':len(generated)==count+1,
            'provenance':'synthetic_pcm_cache_dispatch_only'})
    return {'provenance':'local_public_fixture','llm_calls':0,'tts_provider_calls':0,
            'direct_tools':direct,'tts_cache':cache_rows,'audio_persisted':False,
            'final_answer_cache_used':False,'action_result_cache_used':False}


def main(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',nargs='+',default=DEFAULT_MODELS)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--local-only',action='store_true',help='No key or cloud calls; direct tools/cache only')
    args=parser.parse_args(argv)
    try:
        models=validate_models(args.models)
    except ValueError as exc:
        parser.error(str(exc))
    key=os.environ.get('GEMINI_API_KEY','')
    if not args.local_only and not key:
        parser.error('Pass GEMINI_API_KEY in the ephemeral Docker environment; no .env is read')
    if args.local_only:
        report={'schema_version':1,'attempts':0,'provenance':'local_public_fixture'}
    else:
        from src.llm_client import LLMClient
        clients={model:LLMClient('',model,provider='gemini',api_key=key) for model in models}
        def request(model,messages,max_tokens):
            # Exactly one HTTP attempt. Normal runtime chat() may retry MAX_TOKENS; this budget cannot.
            text,reason=clients[model]._chat_gemini_once(messages,.2,max_tokens)
            return {'text':text,'finish_reason':reason}
        report=run_cloud(models,request)
    report['local_paths']=local_paths()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'output':str(args.output),'attempts':report['attempts'],
                      'provenance':report['provenance'],'model_selection_changed':False}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
