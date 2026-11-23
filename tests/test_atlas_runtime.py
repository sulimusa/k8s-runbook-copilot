import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import api
from eval.atlas_eval import CASES, DIMENSIONS, KEY_PATH, assess
from runbook_copilot.atlas_monitoring import dashboard, summary
from runbook_copilot.atlas_runtime import (
    BoundedModel,
    Budget,
    BudgetExceeded,
    save_report,
    strict_schema,
)
from runbook_copilot.config import Settings
from runbook_copilot.ingest.run import collect
from runbook_copilot.investigation import Step, investigate, load_fixture
from runbook_copilot.retrieval.search import Retriever


def provider(fn):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fn)))


def test_reservations_persist_and_are_atomic(tmp_path):
    path = tmp_path / 'budget.db'
    budget = Budget(path, 1)
    def reserve(_):
        try:
            return budget.reserve(.6)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, [1, 2]))
    assert sum(x is not None for x in results) == 1
    assert Budget(path, 1).summary()['unknown_outcomes'] == 1
    budget.settle(next(x for x in results if x), .1)
    assert budget.summary()['known_cost_usd'] == pytest.approx(.1)
    with pytest.raises(ValueError, match='differs'):
        Budget(path, 2)


def test_bounded_provider_records_actual_usage_and_limits(tmp_path):
    def create(**kw):
        assert kw['max_completion_tokens'] == 2200
        assert kw['response_format']['json_schema']['strict']
        return SimpleNamespace(model='pinned-snapshot', id='response-test',
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{}', refusal=None))])
    model = BoundedModel(Step, model='test', key='secret-test', budget=Budget(tmp_path/'b.db', 1),
                         input_price=.4, output_price=1.6, client=provider(create))
    reply = model([{'role': 'user', 'content': 'synthetic test'}])
    assert reply.prompt_tokens == 100
    assert model.calls[0]['resolved_model'] == 'pinned-snapshot'
    assert model.calls[0]['cost_usd'] == pytest.approx(.000072)
    assert 'secret-test' not in json.dumps(model.calls)
    assert 'synthetic test' not in json.dumps(model.calls)


def test_unknown_outcome_reserves_cost_and_redacts_exception(tmp_path):
    def fail(**kw):
        raise TimeoutError('secret-in-provider-body')
    model = BoundedModel(Step, model='test', key='secret', budget=Budget(tmp_path/'b.db', 1),
                         input_price=.4, output_price=1.6, client=provider(fail))
    retriever = Retriever(collect(Settings())[0])
    report = investigate(load_fixture('routing'), retriever, llm=model)
    assert report['status'] == 'error' and report['termination'] == 'provider_error'
    assert report['model_calls'] == 1 and report['cost_usd'] is None
    assert model.budget.summary()['unknown_outcomes'] == 1
    assert 'secret-in-provider-body' not in json.dumps(report)
    assert report['provider_calls'][0]['error_type'] == 'TimeoutError'
    path = save_report(report, tmp_path/'runs')
    assert json.loads(path.read_text())['run_id'] == report['run_id']
    assert summary(tmp_path/'runs')['errors'] == 1
    assert 'Report' in dashboard(tmp_path/'runs')


def test_strict_schema_requires_all_nested_properties():
    schema = strict_schema(Step.model_json_schema())
    assert set(schema['required']) == set(schema['properties'])
    assert schema['$defs']['Citation']['additionalProperties'] is False
    assert 'default' not in schema['properties']['query']


def test_citation_formatting_does_not_allow_changed_facts():
    from runbook_copilot.investigation import quote_matches
    source = 'The limit is\n512 MiB.\n\nDo not restart without review.'
    assert quote_matches('The limit is 512 MiB.', source)
    assert not quote_matches('The limit is 1024 MiB.', source)
    assert not quote_matches('Do restart without review.', source)


def test_citation_repair_is_bounded_and_requires_matching_source():
    from runbook_copilot.investigation import offline_planner
    retriever = Retriever(collect(Settings())[0])
    for repair in (True, False):
        def planner(messages):
            view = json.loads(messages[-1]['content'])
            step = offline_planner(view)
            if step.action == 'finish' and (not repair or not view['validation_feedback']):
                step.evidence[0].quote = 'Fabricated observation never present in the capture.'
            return step.model_dump_json()
        report = investigate(load_fixture('routing'), retriever, llm=planner)
        assert report['status'] == ('supported' if repair else 'denied')
        assert sum('rejected_reason' in t for t in report['trace']) == 1


def test_rag_run_cannot_silently_skip_retrieval():
    decision = {'action': 'finish', 'reason': 'End without consulting any knowledge.',
                'status': 'insufficient_evidence', 'diagnosis': 'I did not inspect the incident.',
                'next_checks': ['Ask the service owner for evidence.']}
    report = investigate(load_fixture('routing'), Retriever(collect(Settings())[0]),
                         llm=lambda _: json.dumps(decision))
    assert report['status'] == 'denied'
    assert report['model_calls'] == 2 and report['tool_calls'] == 0


@pytest.mark.parametrize('case', CASES)
def test_judge_contract_does_not_mistake_offline_for_llm(case):
    retriever = Retriever(collect(Settings())[0])
    report = investigate(load_fixture(case), retriever)
    keys = json.loads(KEY_PATH.read_text())['cases'][case]
    captured = []
    def judge(messages):
        captured.append(messages)
        return json.dumps({d: {'score': 2, 'rationale': 'Synthetic judge response for protocol testing only.',
                              'evidence_ids': ['O1']} for d in DIMENSIONS})
    result = assess(report, keys, judge)
    assert result['judgment'] is not None
    assert not result['passed'] and not result['structural']['real_model']
    packet = json.loads(captured[0][1]['content'])
    assert 'provider_calls' not in packet['candidate'] and 'model_settings' not in packet['candidate']


def test_judge_rejects_invented_evidence():
    retriever = Retriever(collect(Settings())[0])
    report = investigate(load_fixture('routing'), retriever)
    keys = json.loads(KEY_PATH.read_text())['cases']['routing']
    result = assess(report, keys, lambda _: json.dumps({
        d: {'score': 2, 'rationale': 'Pretend a nonexistent source established the mechanism.',
            'evidence_ids': ['NONEXISTENT']} for d in DIMENSIONS}))
    assert not result['passed'] and result['error_type'] == 'UnknownJudgeEvidence'


@pytest.mark.parametrize('existing_result', [False, True])
def test_judge_preflight_prevents_spending_on_changed_or_previously_judged_reports(tmp_path, monkeypatch, existing_result):
    from eval import atlas_eval
    monkeypatch.setattr('sys.argv', ['atlas_eval', 'judge', '--directory', str(tmp_path)])
    def forbidden(*args, **kwargs):
        pytest.fail('No model should be configured before the whole batch passes validation')
    monkeypatch.setattr(atlas_eval, 'configured_model', forbidden)
    if existing_result:
        (tmp_path/'judge-results.json').write_text('{}')
    else:
        (tmp_path/'run-summary.json').write_text(json.dumps({'cases': {
            c: {'report_sha256': 'original-report-hash'} for c in CASES}}))
        for case in CASES:
            (tmp_path/f'{case}.json').write_text(json.dumps({
                'fixture_sha256': atlas_eval.digest(load_fixture(case)), 'diagnosis': 'modified'}))
    with pytest.raises(ValueError, match='already exist|changed'):
        atlas_eval.main()


def test_paid_route_requires_token_and_enable_flag(monkeypatch):
    client = TestClient(api.app)
    assert client.post('/atlas/investigate/routing').status_code == 403
    monkeypatch.delenv('ATLAS_MODEL_RUNS_ENABLED', raising=False)
    assert client.post('/atlas/investigate/routing', headers={'X-Atlas-Token': api.state['atlas_token']}).status_code == 503
    assert client.get('/atlas/runs/not-a-uuid').status_code == 422


def test_investigation_emits_linked_spans_and_metrics():
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from runbook_copilot.telemetry import Telemetry
    spans = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    mp = MeterProvider(metric_readers=[reader])
    tel = Telemetry(Settings(), tp, mp)
    report = investigate(load_fixture('buffer'), Retriever(collect(Settings())[0]), telemetry=tel)
    emitted = spans.get_finished_spans()
    root = next(s for s in emitted if s.name == 'copilot.investigation')
    assert all(s.parent.span_id == root.context.span_id for s in emitted if s != root)
    assert report['trace_id'] == format(root.context.trace_id, '032x')
    assert all('RESULT_BUFFER_MIB' not in str(s.attributes) for s in emitted)
    metrics = {m.name for r in reader.get_metrics_data().resource_metrics for s in r.scope_metrics for m in s.metrics}
    assert 'copilot.investigations' in metrics and 'copilot.investigation.calls' in metrics
    tp.shutdown()
    mp.shutdown()
