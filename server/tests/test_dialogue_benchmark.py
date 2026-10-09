import importlib.util
import json
from pathlib import Path

import pytest


def load_benchmark():
    path=Path(__file__).resolve().parents[2]/'scripts'/'benchmark_dialogue.py'
    spec=importlib.util.spec_from_file_location('benchmark_dialogue',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_suite_covers_five_languages_with_twenty_maximum_calls():
    benchmark=load_benchmark()
    rows=benchmark.public_cases()
    assert len(rows)==10
    assert {row['language'] for row in rows}=={'ko','en','zh','ja','es'}
    for language in ('ko','en','zh','ja','es'):
        assert {row['category'] for row in rows if row['language']==language}=={'ordinary','detail_tool'}
    assert benchmark.validate_models(['gemini-3.8-flash','gemini-3.5-flash-lite'])
    with pytest.raises(ValueError):
        benchmark.validate_models(['gemini-one','gemini-two','gemini-three'])


def test_benchmark_exact_tool_schema_and_detail_are_separate_from_language_heuristics():
    benchmark=load_benchmark()
    row=next(row for row in benchmark.public_cases() if row['category']=='detail_tool' and row['language']=='en')
    output=json.dumps({'detail':['First, save a draft.','Then, review its contents.','Finally, send it after approval.'],
                       'tool':{'tool':'tasks.add','arguments':{'title':row['title']}}})
    metrics=benchmark.assess(row,output)
    assert metrics['json_valid'] and metrics['tool_schema_correct'] and metrics['detail_requested_respected']
    bad=json.loads(output); bad['tool']['arguments']['owner']='another-owner'
    assert benchmark.assess(row,json.dumps(bad))['tool_schema_correct'] is False
    assert benchmark.assess(row,'not JSON')['json_valid'] is False


def test_injected_model_responses_never_masquerade_as_cloud_calls_and_errors_are_safe():
    benchmark=load_benchmark(); called=[]
    def requester(model,messages,max_tokens):
        called.append((model,messages,max_tokens))
        if len(called)==1:
            raise RuntimeError('PRIVATE_SECRET_TOKEN')
        return {'text':'Hello.','finish_reason':'STOP'}
    report=benchmark.run_cloud(['gemini-3.8-flash','gemini-3.5-flash-lite'],requester,provenance='mock_fixture')
    assert len(called)==20 and report['attempts']==20
    assert report['provenance']=='mock_fixture'
    assert 'PRIVATE_SECRET_TOKEN' not in json.dumps(report)
    assert len(report['models'])==2 and report['models'][0]['latency']['sample_count']==10


def test_local_tools_execute_ephemeral_owner_scoped_data_without_any_model_or_tts_cloud():
    benchmark=load_benchmark()
    report=benchmark.local_paths()
    assert report['provenance']=='local_public_fixture'
    assert report['llm_calls']==0 and report['tts_provider_calls']==0
    assert all(row['owner_isolation'] and row['direct_model_calls']==0 for row in report['direct_tools'])
    assert all(row['synthesis_count']==1 and row['voice_change_misses'] for row in report['tts_cache'])


def test_cli_refuses_missing_key_before_any_request_or_output(tmp_path,monkeypatch):
    benchmark=load_benchmark()
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    with pytest.raises(SystemExit):
        benchmark.main(['--output',str(tmp_path/'public.json')])
    assert not (tmp_path/'public.json').exists()
