"""Replay protocol and scripted-model tests, not measurements of LLM accuracy."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from app import api
from runbook_copilot.config import ROOT, Settings
from runbook_copilot.ingest.run import collect
from runbook_copilot.investigation import investigate, load_fixture, render_report
from runbook_copilot.retrieval.search import Retriever


@pytest.fixture(scope='module')
def knowledge():
    # CI can run these protocol tests without fetching the remote corpus first.
    # The local sources include relevant, superseded and wrong-workload documents.
    chunks, _ = collect(Settings())
    return Retriever(chunks)


@pytest.mark.parametrize('case,status,phrase', [
    ('routing', 'supported', 'concentrates traffic'),
    ('buffer', 'supported', 'configuration-driven'),
    ('incomplete', 'insufficient_evidence', 'cannot distinguish'),
])
def test_three_replay_outcomes_and_knowledge_citations(knowledge, case, status, phrase):
    report = investigate(load_fixture(case), knowledge)
    assert report['planner'] == 'offline_rule_based'
    assert report['status'] == status and phrase in report['diagnosis']
    assert report['model_calls'] == 0
    assert report['termination'] == 'conclusion'
    assert len(report['corpus_sha256']) == 64
    assert report['documents']
    assert all('legacy' not in d['id'] and 'worker' not in d['id'] for d in report['documents'])
    actions = [s['decision']['action'] for s in report['trace']]
    assert ('inspect_configuration' in actions) == (case == 'buffer')
    assert actions.count('search_knowledge') == 2


def test_retrieval_has_applicability_distractors(knowledge):
    hits = knowledge.search('Atlas API routing contract public Service release selector rolling update', k=4, max_per_doc=1)
    assert hits[0].chunk.doc_path == 'atlas-routing.md'
    assert any(h.chunk.doc_path == 'atlas-legacy-routing.md' for h in hits)
    memory = knowledge.search('Atlas API memory concurrency operating envelope RESULT_BUFFER_MIB reference requests', k=4)
    assert memory[0].chunk.doc_path == 'atlas-memory.md'


def test_modes_enforce_tool_and_document_access(knowledge):
    for case in ('routing', 'buffer', 'incomplete'):
        base = investigate(load_fixture(case), knowledge, mode='baseline')
        tools = investigate(load_fixture(case), knowledge, mode='tools')
        assert base['tool_calls'] == 0 and base['status'] == 'insufficient_evidence'
        assert not tools['retrieved_sources']
        assert not any(s['decision']['action'] == 'search_knowledge' for s in tools['trace'])


def test_missing_metrics_not_interpreted_as_zero(knowledge):
    fixture = load_fixture('routing')
    fixture['observations']['inspect_memory'] = load_fixture('incomplete')['observations']['inspect_memory']
    assert investigate(fixture, knowledge)['status'] == 'insufficient_evidence'


def test_observations_drive_outcome_not_scenario_identity(knowledge):
    fixture = load_fixture('routing')
    fixture['observations'] = copy.deepcopy(load_fixture('buffer')['observations'])
    report = investigate(fixture, knowledge)
    assert 'configuration-driven' in report['diagnosis']


def test_model_can_choose_and_requery_without_access_to_hidden_observations(knowledge):
    views = []
    def planner(messages):
        view = json.loads(messages[-1]['content'])
        assert len([m for m in messages if m['role'] == 'assistant']) == len(views)
        views.append(view)
        i = len(views)
        if i == 1:
            assert not view['observations']
            return json.dumps({'action': 'inspect_configuration', 'reason': 'Compare effective configuration changes first.'})
        if i == 2:
            assert set(view['observations']) == {'inspect_configuration'}
            return json.dumps({'action': 'search_knowledge', 'reason': 'Find the observed buffer setting applicability.',
                               'query': 'Atlas API memory RESULT_BUFFER_MIB'})
        return json.dumps({'action': 'finish', 'reason': 'Configuration difference alone is not causal evidence.',
                           'status': 'insufficient_evidence', 'diagnosis': 'Need matched traffic and memory observations.',
                           'next_checks': ['Collect matched-load allocation profiles.']})
    report = investigate(load_fixture('buffer'), knowledge, llm=planner)
    assert report['model_calls'] == 3 and report['tool_calls'] == 2
    assert report['status'] == 'insufficient_evidence'
    assert views[-1]['documents']
    assert 'expected_cause' not in json.dumps(views)


@pytest.mark.parametrize('response', [
    {'action': 'delete_pod', 'reason': 'Try to mutate a workload.'},
    {'action': 'inspect_routes', 'reason': 'Not allowed in the baseline arm.'},
    {'action': 'finish', 'reason': 'Pretend to know the answer without evidence.', 'status': 'supported',
     'diagnosis': 'A made-up cause', 'next_checks': ['Do something'],
     'evidence': [{'id': 'O99', 'quote': 'Invented observation'}]},
])
def test_model_cannot_write_expand_scope_or_forge_evidence(knowledge, response):
    result = investigate(load_fixture('routing'), knowledge, mode='baseline', llm=lambda _: json.dumps(response))
    assert result['status'] in ('denied', 'error')
    assert result['tool_calls'] == 0


def test_step_budget_and_no_repeated_reads(knowledge):
    report = investigate(load_fixture('routing'), knowledge, max_steps=1)
    assert report['termination'] == 'step_budget_exhausted'
    assert report['status'] == 'insufficient_evidence'
    report = investigate(load_fixture('routing'), knowledge, llm=lambda _: json.dumps(
        {'action': 'inspect_rollout', 'reason': 'Repeated read must be refused.'}))
    assert report['status'] == 'denied' and report['tool_calls'] == 1


def test_current_review_synopses_match_corpus_and_no_keys_ingested(knowledge):
    patterns = json.loads((ROOT / 'data/incident_patterns.json').read_text())
    for p in patterns:
        text = (ROOT / 'data/incident_knowledge' / (p['id'] + '.md')).read_text()
        assert p['text'] in text and p['source_url'] in text
    assert not any(c.source_id.startswith('eval') or 'expected_cause' in c.text for c in knowledge.chunks)


def test_demo_web_routes_and_html_escape(knowledge):
    api.state['retriever'] = knowledge
    client = TestClient(api.app)
    assert client.get('/demo/rollout-oom').status_code == 200
    assert 'configuration-driven' in client.get('/demo/rollout-oom/buffer').text
    assert client.get('/demo/rollout-oom/other').status_code == 400
    assert client.get('/demo/rollout-oom/routing?mode=write').status_code == 400
    report = investigate(load_fixture('incomplete'), knowledge)
    report['diagnosis'] = '<script>alert(1)</script>'
    assert '<script>' not in render_report(report)
