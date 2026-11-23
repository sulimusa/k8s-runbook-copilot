import copy
import json
from datetime import datetime

import pytest

from eval.knowledge_value.review_v3 import calibration_passed, controls
from eval.knowledge_value.study import digest
from runbook_copilot.history.chat import investigate
from runbook_copilot.history.demo import DemoClient, cases, retriever
from tests.test_history import Model


def test_demo_scopes_versions_and_preserves_data():
    case = cases()[0]
    index = retriever(case)
    ids = {c.chunk_id for c in index.chunks}
    assert 'cache-v2' in ids
    assert not {'cache-v1', 'cache-dev-v2'} & ids
    api = DemoClient(case)
    result = api.get('history', namespace=case['namespace'], since='2026-11-01T00:00:00Z', kind='Deployment', limit=1)
    assert result['total'] == 1 and result['records'][0]['before']['containers'][0]['image'].endswith(':v1')
    result['records'][0]['before'] = None
    assert api.case['history'][0]['before'] is not None
    with pytest.raises(ValueError, match='namespace mismatch'):
        api.get('current', namespace='dev-capstone')
    with pytest.raises(ValueError):
        api.get('patch', namespace=case['namespace'])


def test_snapshot_clock_filters_and_baseline_is_not_change():
    case = cases()[2]
    api = DemoClient(case)
    assert api.get('history', namespace=case['namespace'], since='2026-11-19T00:00:00Z')['total'] == 0
    assert api.get('history', namespace=case['namespace'], since='2026-11-01T00:00:00Z')['records'][0]['operation'] == 'BASELINE'
    assert 'November 5' in case['question']
    assert case['coverage']['history_available_since'].startswith('2026-11-18')


def test_disabled_rag_cannot_be_called(monkeypatch):
    monkeypatch.setattr('runbook_copilot.history.chat.save_report', lambda *a, **k: None)
    case = cases()[0]
    with pytest.raises(ValueError, match='retrieval is disabled'):
        investigate(case['question'],case['namespace'],7,retriever(case),client=DemoClient(case),
                    model=Model([{'action':'runbook','query':'cache'}]),knowledge_enabled=False,now=datetime.fromisoformat(case['as_of']))


def test_same_agent_records_replay_provenance(monkeypatch):
    monkeypatch.setattr('runbook_copilot.history.chat.save_report', lambda *a, **k: None)
    case = cases()[2]
    model = Model([{'action':'history','kind':'Deployment','name':'payments-api'},
                   {'answer':'H1 is a baseline after the outage; cause unknown.','citations':['H1']}])
    report = investigate(case['question'],case['namespace'],30,retriever(case),client=DemoClient(case),model=model,
                         knowledge_enabled=False,now=datetime.fromisoformat(case['as_of']))
    assert report['data_origin'] == 'synthetic_history_snapshot'
    assert report['as_of'] == case['as_of']
    assert report['instruction_version'] == 'history-sre-v6'
    assert 'reference' not in json.dumps(model.messages)


def fake_calibration():
    results=[]
    for control in controls():
        candidates=[]
        for label in 'ABC':
            item={'label':label,'unsupported_claims':['bad assertion'] if label=='B' else []}
            for dim in ('correctness','grounding','safety','uncertainty','usefulness'):
                item[dim]={'score':1 if label=='B' and dim==control['dimension'] else 2,'rationale':'test'}
            candidates.append(item)
        results.append({'error':None,'packet_sha256':digest(control['packet']),'judgment':{'candidates':candidates}})
    return results


def test_judge_gate_requires_all_controls_and_penalizes_known_errors():
    results=fake_calibration()
    assert calibration_passed(results)
    broken=copy.deepcopy(results)
    broken[2]['judgment']['candidates'][1]['grounding']['score']=2
    assert not calibration_passed(broken)
    broken=copy.deepcopy(results)
    broken[0]['judgment']['candidates'][0]['safety']['score']=1
    assert not calibration_passed(broken)
    with pytest.raises(ValueError):
        calibration_passed(results[:-1])


def test_factual_review_never_gets_reference_or_other_candidates():
    from eval.knowledge_value.factual_review import packet, validate
    candidate={'available_context':{'observations':[]},'answer':{'recommendation':'Check the "reload" setting.'},
               'generation_failed':False,'reference':'SECRET ANSWER','other_candidates':['SECRET ANSWER']}
    assert 'SECRET ANSWER' not in json.dumps(packet(candidate))
    assert validate({'issues':[{'kind':'unsupported_fact','quote':'Check the "reload" setting.','reason':'test'}]},candidate)
    with pytest.raises(ValueError,match='exact candidate'):
        validate({'issues':[{'kind':'unsupported_fact','quote':'Made up words','reason':'test'}]},candidate)


def test_quote_gate_preserves_conditions_and_never_autoscores():
    from eval.knowledge_value.review_gate import contextualize
    issue={'kind':'unsupported_fact','quote':'doubling replicas will not exceed the cap','reason':'test'}
    result=contextualize(issue,{'recommendation':'Before scaling, check the pool and ensure that doubling replicas will not exceed the cap.'})
    assert result['status']=='needs_review_conditional_or_uncertain'
    assert result['context'].startswith('Before scaling')
    assert 'score' not in result
    assert contextualize(issue,{'recommendation':'Different answer'})['status']=='invalid_quote'


def test_ui_demo_cases_render_without_cluster_or_model_calls(monkeypatch):
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest

    from runbook_copilot.config import ROOT
    monkeypatch.setattr('runbook_copilot.history.chat.HistoryClient.get',lambda *a,**k: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr('runbook_copilot.retrieval.search.Retriever.load',lambda *a,**k: retriever(cases()[0]))
    monkeypatch.setattr('runbook_copilot.history.chat.configured_model',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No paid calls while browsing')))
    app=AppTest.from_file(str(ROOT/'app/ui.py'),default_timeout=30).run()
    app.sidebar.radio[0].set_value('Recorded investigations').run()
    for case in cases():
        app.selectbox[0].set_value(case).run()
        assert not app.exception
        assert any('Synthetic history snapshot' in w.value for w in app.warning)
        assert not any('Restore previous selector' in b.label for b in app.button)
        assert any('Recorded model comparison' in e.label for e in app.expander)


def test_summary_citation_fetches_full_record_before_acceptance(monkeypatch):
    monkeypatch.setattr('runbook_copilot.history.chat.save_report',lambda *a,**k: None)
    case=cases()[2]
    step={'answer':'H1 is first observed state, not a deployment date.','citations':['H1']}
    model=Model([step,step])
    report=investigate(case['question'],case['namespace'],30,retriever(case),client=DemoClient(case),model=model,
                       knowledge_enabled=False,now=datetime.fromisoformat(case['as_of']))
    assert report['trace'][0]['reason']=='Resolve requested summary citation against full records'
    assert report['citations']['H1']['after']['kind']=='Deployment'
    assert len(model.messages)==2


def test_memory_fixture_labels_and_ownership_do_not_invent_a_second_failure():
    case=cases()[0]
    pod=next(o for o in case['current'] if o['kind']=='Pod')
    deployment=next(o for o in case['current'] if o['kind']=='Deployment')
    rs=next(o for o in case['current'] if o['kind']=='ReplicaSet')
    assert pod['labels']==deployment['selector']==rs['labels']
    assert pod['owners'][0]['uid']==rs['uid']
    assert rs['owners'][0]['uid']==deployment['uid']
    assert deployment['replicas']==1


def test_claim_guard_deduplicates_same_termination_and_allows_distinct_evidence():
    from runbook_copilot.history.chat import FinalAnswer
    from runbook_copilot.history.claims import final_claim_issues
    final = FinalAnswer(assessment='hypothesis', observed_impact='Pod repeatedly restarts due to OOMKilled.',
                        timeline=[], observations='', explanation='', alternatives='', missing_evidence='',
                        next_check='', mitigation_conditions='', verification_and_stop='')
    pod = next(copy.deepcopy(o) for o in cases()[0]['current'] if o['kind'] == 'Pod')
    evidence = {'C0':pod, 'H0':{'after':copy.deepcopy(pod)}}
    assert final_claim_issues(final, evidence)
    evidence['H0']['after']['container_status'][0]['restart_count'] = 2
    assert not final_claim_issues(final, evidence)
    final.observed_impact = 'Three restarts, last termination OOMKilled; earlier reasons unknown.'
    assert not final_claim_issues(final, {'C0':pod})
    final.observed_impact = 'Pod is repeatedly restarting; only the last termination is evidenced as OOMKilled.'
    assert not final_claim_issues(final, {'C0':pod})
    final.observed_impact = 'The Pod was not repeatedly OOMKilled.'
    assert not final_claim_issues(final, {'C0':pod})
    final.verification_and_stop = 'Verify that Service DNS resolves to the Pod IP.'
    assert 'ClusterIP' in final_claim_issues(final, {'C0':pod})[0]


def test_all_disputed_findings_have_bound_review_decisions():
    from runbook_copilot.config import ROOT
    review = json.loads((ROOT/'docs/judge-adjudications.json').read_text())
    queue = json.loads((ROOT/'docs/judge-review-queue.json').read_text())
    assert review['queue_sha256'] == digest(queue)
    assert len(review['decisions']) == sum(len(v) for c in queue['cases'] for v in c['candidates'].values())
    assert all(d['verdict'] in {'reject_deduction','accept_defect','wording_correction'} for d in review['decisions'])
    assert all(d['reason'] and d['context_sha256'] and d['answer_sha256'] for d in review['decisions'])


def test_investigation_retries_unsupported_termination_claim_without_silent_edit(monkeypatch):
    monkeypatch.setattr('runbook_copilot.history.chat.save_report', lambda *a, **k: None)
    case = cases()[0]
    bad = {'answer':'Pod repeatedly restarts due to OOMKilled.', 'citations':['C0-0']}
    good = {'answer':'Three restarts; last termination OOMKilled. Earlier reasons unknown.', 'citations':['C0-0']}
    model = Model([{'action':'current','kind':'Pod','name':'cache-api-abc'}, bad, good])
    report = investigate(case['question'],case['namespace'],7,retriever(case),client=DemoClient(case),model=model,
                         knowledge_enabled=False,now=datetime.fromisoformat(case['as_of']))
    assert len(report['claim_corrections']) == 1
    assert report['attempts'][1]['final']['observations'] == bad['answer']
    assert report['structured']['observations'] == good['answer']
    assert len(report['trace']) == 1


def test_published_comparison_review_matches_answers_and_rag_evidence():
    from runbook_copilot.config import ROOT
    from runbook_copilot.history.chat import FinalAnswer
    from runbook_copilot.history.claims import final_claim_issues
    results=json.loads((ROOT/'docs/history-demo-results.json').read_text())
    review=json.loads((ROOT/'docs/history-demo-adjudications.json').read_text())
    assert review['results_sha256']==digest(results)
    for case,arms in results['cases'].items():
        for arm,r in arms.items():
            assert r['status']=='completed'
            assert review['cases'][case][arm]['answer_sha256']==digest(r['structured'])
            assert not final_claim_issues(FinalAnswer.model_validate(r['structured']),r['citations'])
            if arm=='evidence':
                assert not any(t['step']['action']=='runbook' for t in r['trace'])
            for entry in r['structured']['timeline']:
                assert r['citations'][entry['evidence_id']]['observed_at']==entry['observed_at']
    cache=results['cases']['cache-rollout']['rag']
    assert 'D-cache-v2' in cache['citations']
    assert '768' in cache['structured']['observations']
    assert 'worker' in cache['structured']['next_check'] and 'allocation' in cache['structured']['next_check']
    for r in results['cases']['missing-history'].values():
        assert r['structured']['assessment']=='insufficient_evidence'
