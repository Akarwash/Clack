import json
import httpx
import pytest
from clack.claude_correct import ClaudeCorrector, validate_candidates

CANDIDATES = [[['h', .8], ['x', .2]], [['i', .7], ['e', .3]], [['space', 1.]]]

@pytest.mark.asyncio
@pytest.mark.parametrize('indices,reason', [([0, 1, 0], None), ([0], 'invalid_output'), ([2, 0, 0], 'invalid_output'), ([True, 0, 0], 'invalid_output'), ([-1, 0, 0], 'invalid_output')])
async def test_constrained_selections(monkeypatch, indices, reason):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-test-key')
    def handler(request):
        body = json.loads(request.content)
        assert body['model'] == 'claude-opus-5-5'
        assert json.loads(body['messages'][0]['content']) == {'positions': CANDIDATES}
        assert body['output_config']['effort'] == 'medium'
        return httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps({'indices': indices})}], 'usage': {'input_tokens': 10, 'output_tokens': 4}})
    service = ClaudeCorrector(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await service.correct(CANDIDATES)
    assert result['fallback_reason'] == reason
    if reason is None: assert result['text'] == 'he ' and result['provider'] == 'claude'
    else: assert result['provider'] == 'local'
    assert 'private-test-key' not in json.dumps(result)
    await service.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure,reason', [(401,'authentication_failed'),(404,'model_unavailable'),(429,'rate_limited'),('refusal','refused'),('timeout','timeout'),('malformed','invalid_output')])
async def test_failure_falls_back(monkeypatch,failure,reason):
    monkeypatch.setenv('ANTHROPIC_API_KEY','private-test-key')
    def handler(request):
        if failure == 'timeout': raise httpx.ReadTimeout('private-test-key')
        if isinstance(failure,int): return httpx.Response(failure,text='private-test-key')
        if failure == 'malformed': return httpx.Response(200,text='not json')
        return httpx.Response(200,json={'stop_reason':'refusal'})
    service=ClaudeCorrector(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out=await service.correct(CANDIDATES)
    assert out['provider']=='local' and out['fallback_reason']==reason
    assert 'private-test-key' not in json.dumps(out)
    await service.close()

@pytest.mark.asyncio
async def test_no_requests_for_empty_missing_or_long(monkeypatch):
    def handler(request): raise AssertionError('No network expected')
    service=ClaudeCorrector(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setenv('ANTHROPIC_API_KEY','')
    assert (await service.correct([]))['provider']=='none'
    assert (await service.correct(CANDIDATES))['fallback_reason']=='missing_credentials'
    monkeypatch.setenv('ANTHROPIC_API_KEY','private-test-key')
    assert (await service.correct([[['a',1.]]]*501))['fallback_reason']=='too_many_detections'
    await service.close()

@pytest.mark.parametrize('value',[None,[[['a',float('nan')]]],[[['bad',.5]]],[[['a',True]]],[[]]])
def test_input_validation(value):
    with pytest.raises(ValueError): validate_candidates(value)

def test_route_compatibility_and_validation(monkeypatch):
    from fastapi.testclient import TestClient
    from clack.server import create_app
    monkeypatch.setenv('ANTHROPIC_API_KEY','')
    with TestClient(create_app()) as client:
        assert client.post('/correct',json={'lattice':[['t'],['h'],['e']]}).json()=={'text':'the'}
        assert client.post('/correct',json={'provider':'claude','candidates':[]}).json()['provider']=='none'
        assert client.post('/correct',json={'provider':'claude','candidates':CANDIDATES}).json()['fallback_reason']=='missing_credentials'
        assert client.post('/correct',json={'provider':'claude','candidates':[[['a',-1]]]}).status_code==422
        assert client.post('/correct',json={'provider':'unknown'}).status_code==422

def test_credential_precedence_and_permissions(monkeypatch,tmp_path):
    from pathlib import Path
    from clack.claude_correct import api_key
    file=tmp_path/'.env'
    monkeypatch.setattr('clack.claude_correct.ENV_FILE', file)
    file.write_text('ANTHROPIC_API_KEY=file-key\n');file.chmod(0o600)
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    assert api_key()=='file-key'
    file.chmod(0o644)
    assert api_key()==''
    monkeypatch.setenv('ANTHROPIC_API_KEY','environment-key')
    assert api_key()=='environment-key'
    monkeypatch.setenv('ANTHROPIC_API_KEY','')
    assert api_key()==''
