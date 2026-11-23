"""Protocol tests; fabricated predictions never count as LLM quality evidence."""
import copy
import json
from collections import Counter

import pytest

from eval.knowledge_value import study


def replace(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def experiment(tmp_path):
    directory = tmp_path / 'study'
    study.prepare(directory, public=[])
    return directory


def fabricate(directory, failed=None):
    manifest = study.load(directory)
    prompts = study.read(directory / 'prompts.json')
    study.write(directory / 'generation-settings.json', {'requested_model': 'test-only'})
    (directory / 'predictions').mkdir()
    for case_id, arm in manifest['order']:
        answer = {'status': 'insufficient_evidence', 'diagnosis': 'Test placeholder',
                  'recommendation': 'Ask for evidence', 'next_checks': [], 'uncertainties': ['Unknown'],
                  'citations': []}
        bad = (case_id, arm) == failed
        study.write(directory / 'predictions' / f'{case_id}--{arm}.json', {
            'case_id': case_id, 'arm': arm, 'prompt_sha256': study.digest(prompts[case_id][arm]),
            'manifest_sha256': study.digest(manifest), 'answer': None if bad else answer,
            'error': 'SyntheticTestFailure' if bad else None,
            'provider': {'requested_model': 'test-only', 'resolved_model': 'test-only-v1',
                         'duration_ms': 1, 'cost_usd': 0, 'input_tokens': 1, 'output_tokens': 1}})


def rate(directory, regression=None):
    study.package(directory)
    packet = study.read(directory / 'judge-packet.json')
    mapping = study.read(directory / 'judge-mapping.json')
    (directory / 'judgments').mkdir()
    for case_id, case in packet['cases'].items():
        candidates = []
        for c in case['candidates']:
            score = 0 if c['generation_failed'] else 2
            if case_id == regression and mapping[case_id][c['label']] == 'rag':
                score = 1
            candidates.append({'label': c['label'], 'unsupported_claims': [],
                               **{d: {'score': score, 'rationale': 'Synthetic test rating'} for d in study.DIMENSIONS}})
        study.write(directory / 'judgments' / f'{case_id}.json', {
            'packet_sha256': study.digest(packet), 'error': None,
            'judgment': {'candidates': candidates}, 'provider': {}})


def test_family_disjoint_balanced_cases_and_keys():
    cases = study.read(study.ROOT / 'eval/knowledge_value/cases.json')
    keys = study.read(study.ROOT / 'eval/knowledge_value/answer_keys.json')
    assert len(cases) == 24
    assert {c['id'] for c in cases} == {k['id'] for k in keys}
    assert Counter(c['category'] for c in cases) == {
        'knowledge_changes_decision': 12, 'knowledge_should_not_help': 6, 'missing_applicable_knowledge': 6}
    a = {c['family'] for c in cases if c['split'] == 'development'}
    b = {c['family'] for c in cases if c['split'] == 'reserved_test'}
    assert not a & b
    assert all(k['human_review'] == 'pending' for k in keys)


def test_fair_context_and_key_isolation(experiment):
    prompts = study.read(experiment / 'prompts.json')
    for arms in prompts.values():
        ctx = {a: json.loads(p[1]['content']) for a, p in arms.items()}
        assert ctx['evidence']['observations'] == ctx['rag']['observations']
        assert ctx['question_only']['observations'] == []
        assert ctx['question_only']['documents'] == ctx['evidence']['documents'] == []
        assert len({p[0]['content'] for p in arms.values()}) == 1
        for forbidden in ('expected_facts', 'forbidden_claims', 'decisive_documents', 'human_review', 'category', 'family'):
            assert forbidden not in json.dumps(arms)
    assert all(c['source_id'] == 'fictional-contracts' for c in study.read(experiment / 'corpus.json'))


def test_scoped_retrieval_excludes_cross_version_environment_and_stale_docs(experiment):
    prompts = study.read(experiment / 'prompts.json')
    for case_id, arms in prompts.items():
        ctx = json.loads(arms['rag'][1]['content'])
        for doc in ctx['documents']:
            assert study.applicable(doc['scope'], ctx['scope'])
        if case_id.endswith('unknown'):
            assert not ctx['documents']
    stats = study.audit_summary(experiment)
    assert stats['unfiltered']['cases_with_inapplicable_documents'] > 0
    assert stats['scoped']['cases_with_inapplicable_documents'] == 0
    assert 'not model answer quality' in stats['status']


def test_effective_dates_fail_closed():
    doc = study.read(study.ROOT / 'data/knowledge_value/documents.json')[0]
    scope = {'as_of': '2026-11-04T00:00:00+00:00', 'service': doc['service'],
             'namespace': doc['environment'], 'version': doc['versions'][0]}
    assert study.applicable(doc, scope)
    assert not study.applicable({**doc, 'valid_until': scope['as_of']}, scope)
    assert not study.applicable({**doc, 'valid_from': '2027-01-01T00:00:00+00:00'}, scope)


def test_freeze_and_no_overwrite(experiment):
    with pytest.raises(FileExistsError):
        study.prepare(experiment, public=[])
    prompts = study.read(experiment / 'prompts.json')
    prompts['release-a']['rag'][0]['content'] += 'changed'
    replace(experiment / 'prompts.json', prompts)
    with pytest.raises(ValueError, match='Frozen artifact'):
        study.load(experiment)


def test_unknown_citation_and_question_only_proof_rejected():
    a = {'status': 'supported', 'diagnosis': 'x', 'recommendation': 'x',
         'next_checks': [], 'uncertainties': [], 'citations': ['Q0']}
    ctx = {'observations': [], 'documents': []}
    with pytest.raises(ValueError, match='observation/document'):
        study.validate_answer(a, ctx)
    with pytest.raises(ValueError, match='Unknown citation'):
        study.validate_answer({**a, 'citations': ['invented']}, ctx)


def test_blind_mapping_tampering_and_model_mismatch(experiment):
    fabricate(experiment)
    study.package(experiment)
    packet = study.read(experiment / 'judge-packet.json')
    for case in packet['cases'].values():
        assert {c['label'] for c in case['candidates']} == set('ABC')
        assert all('arm' not in c and 'provider' not in c for c in case['candidates'])
    mapping = study.read(experiment / 'judge-mapping.json')
    mapping['release-a']['A'] = 'tampered'
    replace(experiment / 'judge-mapping.json', mapping)
    with pytest.raises(ValueError, match='mapping changed'):
        study.review_packet(experiment)
    path = experiment / 'predictions/release-a--rag.json'
    row = study.read(path)
    row['provider']['requested_model'] = 'different'
    replace(path, row)
    with pytest.raises(ValueError, match='model mismatch'):
        study.prediction(experiment, 'release-a', 'rag')


def test_failed_generations_and_regressions_retained(experiment):
    fabricate(experiment, failed=('memory-a', 'rag'))
    rate(experiment, regression='release-a')
    report = study.summarize(experiment)
    assert report['planned_cases'] == len(report['cases']) == 12
    assert report['generation_telemetry']['rag']['failed'] == 1
    regressions = report['groups']['knowledge_changes_decision']['regressions']
    assert {'memory-a', 'release-a'} <= set(regressions)
    assert report['groups']['knowledge_changes_decision']['mean_paired_delta']['usefulness'] < 0
    with pytest.raises(FileExistsError):
        study.summarize(experiment)


def test_missing_judgment_prevents_complete_result(experiment):
    fabricate(experiment)
    rate(experiment)
    path = experiment / 'judgments/release-a.json'
    row = study.read(path)
    row.update(judgment=None, error='SyntheticJudgeFailure')
    replace(path, row)
    report = study.summarize(experiment)
    assert report['status'] == 'incomplete'
    assert report['missing_judgments'] == ['release-a']


def test_estimate_does_not_call_provider(experiment, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Offline command attempted provider configuration')
    monkeypatch.setattr(study, 'configured_model', forbidden)
    result = study.estimate(experiment)
    assert result['prediction_calls'] == 36
    assert result['judge_calls'] == 12
    assert result['total_upper_estimate_usd'] > 0


def test_judge_rejects_missing_duplicate_labels_and_nonzero_failure():
    candidate = {'label': 'A', 'unsupported_claims': [],
                 **{d: {'score': 2, 'rationale': 'test'} for d in study.DIMENSIONS}}
    value = {'candidates': [copy.deepcopy(candidate) for _ in range(3)]}
    packet = {'candidates': [{'label': 'A', 'generation_failed': True}]}
    with pytest.raises(ValueError, match='exactly once'):
        study.validate_judgment(value, packet)
    for c, label in zip(value['candidates'], 'ABC', strict=True):
        c['label'] = label
    with pytest.raises(ValueError, match='must score zero'):
        study.validate_judgment(value, packet)


def test_supplemental_review_requires_passing_calibration(tmp_path, monkeypatch):
    from eval.knowledge_value import review_context
    path = tmp_path / 'calibration.json'
    replace(path, {'passed': False, 'system_sha256': study.digest(review_context.REVIEW_SYSTEM)})
    monkeypatch.setattr(review_context, 'configured_model', lambda *a, **k: pytest.fail('Must not spend'))
    with pytest.raises(ValueError, match='Calibration'):
        review_context.review(tmp_path / 'absent', path)


def test_supplemental_review_retains_parse_failure():
    from eval.knowledge_value.review_context import call_review
    from runbook_copilot.llm.client import LLMReply

    class Broken:
        calls = []

        def __call__(self, messages):
            self.calls.append({'cost_usd': 0, 'requested_model': 'test-only'})
            return LLMReply('not json')

    record = call_review(Broken(), {'candidates': []})
    assert record['error'] == 'JSONDecodeError'
    assert record['judgment'] is None
    assert record['provider']['requested_model'] == 'test-only'


def test_export_preserves_supplemental_regressions(experiment, monkeypatch):
    from eval.knowledge_value import report_live
    fabricate(experiment)
    rate(experiment)
    study.summarize(experiment)
    packet, mapping = study.review_packet(experiment)
    folder = experiment / 'judgments-context-aware-v2'
    folder.mkdir()
    study.write(folder / 'protocol.json', {'packet_sha256': study.digest(packet), 'system_sha256': 'test-only'})
    for case_id in packet['cases']:
        original = study.read(experiment / 'judgments' / f'{case_id}.json')
        original['provider'] = {'cost_usd': 0}
        replace(experiment / 'judgments' / f'{case_id}.json', original)
        modified = copy.deepcopy(original)
        modified.update(packet_sha256=study.digest(packet['cases'][case_id]), system_sha256='test-only')
        if case_id == 'memory-a':
            for c in modified['judgment']['candidates']:
                if mapping[case_id][c['label']] == 'rag':
                    c['usefulness']['score'] = 0
        study.write(folder / f'{case_id}.json', modified)
    monkeypatch.setattr(report_live, 'ROOT', experiment.parent)
    raw = report_live.collect([experiment])
    adjusted = report_live.collect([experiment], context_review=True)
    assert raw['summary']['knowledge_changes_decision']['usefulness_rag_vs_evidence'] == {'tie': 6}
    assert adjusted['summary']['knowledge_changes_decision']['usefulness_rag_vs_evidence']['loss'] == 1
    assert 'memory-a' in adjusted['summary']['knowledge_changes_decision']['any_dimension_regressions']
