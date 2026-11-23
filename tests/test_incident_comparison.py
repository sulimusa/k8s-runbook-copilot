"""Protocol tests with fabricated responses; these are never model-quality measurements."""
import copy
import json
from datetime import datetime, timezone

import pytest

from eval.incident_comparison import (
    ARMS,
    DIMENSIONS,
    ArmRun,
    digest,
    load_experiment,
    package,
    prepare,
    summarize,
)
from eval.incident_eval import ROOT, read_json


def replace(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def experiment(tmp_path):
    directory = tmp_path / 'experiment'
    manifest = prepare(directory)
    for arm in ARMS:
        rows = []
        for case_id in manifest['cases']:
            rows.append({'id': case_id, 'prompt_sha256': manifest['prompt_hashes'][arm][case_id],
                         'prediction': {'id': case_id, 'status': 'insufficient_evidence',
                                        'diagnosis': 'Test placeholder: ' + arm, 'confidence': 0.5,
                                        'evidence': [], 'next_checks': [],
                                        'diagnostic_commands': [], 'reference_ids': []},
                         'error': None, 'latency_ms': None, 'input_tokens': None, 'output_tokens': None})
        replace(directory / f'{arm}-responses.json', {
            'mode': arm, 'manifest_sha256': digest(manifest),
            'model': 'test-only', 'resolved_model': 'test-only-snapshot',
            'settings': {'temperature': 0, 'max_output_tokens': 1024, 'retries': 0},
            'completed_at': datetime.now(timezone.utc).isoformat(), 'records': rows})
    return directory


def rate(directory):
    packet = read_json(directory / 'review' / 'judge-packet.json')
    ratings = []
    for case in packet['records']:
        item = {'id': case['id']}
        for label, candidate in case['candidates'].items():
            value = 0 if candidate.get('generation_failed') else 1
            item[label] = {d: {'score': value, 'rationale': 'Fabricated test rating only.'} for d in DIMENSIONS}
        ratings.append(item)
    replace(directory / 'review' / 'judge-ratings.json', {
        'packet_sha256': digest(packet), 'reviewer': 'test-only-reviewer',
        'completed_at': datetime.now(timezone.utc).isoformat(), 'records': ratings})


def test_freeze_excludes_keys_and_uses_identical_observations(experiment):
    baseline = read_json(experiment / 'baseline-prompts.json')
    patterns = read_json(experiment / 'patterns-prompts.json')
    for a, b in zip(baseline, patterns, strict=True):
        assert a['messages'][0] == b['messages'][0]
        assert json.loads(a['messages'][1]['content'])['case'] == json.loads(b['messages'][1]['content'])['case']
        assert 'expected_cause' not in json.dumps(b)
    assert not (experiment / 'answer_keys.json').exists()
    with pytest.raises(FileExistsError):
        prepare(experiment)


def test_roundtrip_blind_packet_and_descriptive_report(experiment):
    mapping = package(experiment)
    packet = read_json(experiment / 'review' / 'judge-packet.json')
    assert len(packet['records']) == 36
    assert 'assignments' not in packet
    for row in packet['records']:
        assert set(row['candidates']) == {'A', 'B'}
        assert set(mapping['assignments'][row['id']].values()) == set(ARMS)
        assert 'expected_cause' not in json.dumps(row)
        assert 'resolved_model' not in json.dumps(row)
    rate(experiment)
    report = summarize(experiment)
    assert report['overall']['cases'] == 36
    assert report['overall']['families'] == 12
    assert len(report['groups']['family']) == 12
    assert {g['cases'] for g in report['groups']['variant'].values()} == {12}
    assert report['overall']['paired_mean_delta_patterns_minus_baseline']['diagnosis'] == 0
    with pytest.raises(FileExistsError):
        summarize(experiment)
    with pytest.raises(FileExistsError):
        package(experiment)


@pytest.mark.parametrize('field,value', [('model', 'another-model'), ('resolved_model', 'other-snapshot'),
                                        ('settings', {'temperature': 1})])
def test_mismatched_generation_configuration_rejected(experiment, field, value):
    path = experiment / 'patterns-responses.json'
    run = read_json(path)
    run[field] = value
    replace(path, run)
    with pytest.raises(ValueError, match='same model'):
        package(experiment)


@pytest.mark.parametrize('change', ['omit', 'duplicate', 'prompt', 'manifest', 'id'])
def test_response_provenance_and_completeness(experiment, change):
    path = experiment / 'baseline-responses.json'
    run = read_json(path)
    if change == 'omit':
        run['records'].pop()
    elif change == 'duplicate':
        run['records'][-1] = copy.deepcopy(run['records'][0])
    elif change == 'prompt':
        run['records'][0]['prompt_sha256'] = 'wrong'
    elif change == 'manifest':
        run['manifest_sha256'] = 'wrong'
    else:
        run['records'][0]['prediction']['id'] = 'other-case'
    replace(path, run)
    with pytest.raises(ValueError):
        package(experiment)


def test_prompt_edit_rejected(experiment):
    path = experiment / 'baseline-prompts.json'
    prompts = read_json(path)
    prompts[0]['messages'][0]['content'] += ' Tampered.'
    replace(path, prompts)
    with pytest.raises(ValueError, match='prompts changed'):
        package(experiment)


def test_stale_suite_rejected_without_mutating_real_fixtures(experiment, tmp_path):
    manifest = read_json(experiment / 'manifest.json')
    fake_root = tmp_path / 'root'
    for relative in manifest['artifacts']:
        target = fake_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    with (fake_root / 'eval/incident_suite/inputs.json').open('a') as handle:
        handle.write('\n')
    with pytest.raises(ValueError, match='Stale experiment'):
        load_experiment(experiment, fake_root)


def test_failed_generation_retained_and_unknown_usage_stays_unknown(experiment):
    path = experiment / 'baseline-responses.json'
    run = read_json(path)
    run['records'][0].update(prediction=None, error='Test timeout, not a real provider call')
    replace(path, run)
    parsed = ArmRun.model_validate(run)
    assert parsed.records[0].input_tokens is None
    package(experiment)
    rate(experiment)
    result = summarize(experiment)
    assert result['overall']['arms']['baseline']['failed_generations'] == 1
    assert result['overall']['paired_mean_delta_patterns_minus_baseline']['diagnosis'] > 0


def test_cannot_change_answers_after_judge_review(experiment):
    package(experiment)
    rate(experiment)
    path = experiment / 'baseline-responses.json'
    run = read_json(path)
    run['records'][0]['prediction']['diagnosis'] = 'A new diagnosis'
    replace(path, run)
    with pytest.raises(ValueError, match='Responses changed'):
        summarize(experiment)


@pytest.mark.parametrize('change', ['packet_hash', 'missing_case', 'range', 'fraction', 'rationale'])
def test_incomplete_or_invalid_judge_scores_rejected(experiment, change):
    package(experiment)
    rate(experiment)
    path = experiment / 'review' / 'judge-ratings.json'
    ratings = read_json(path)
    if change == 'packet_hash':
        ratings['packet_sha256'] = 'other-packet'
    elif change == 'missing_case':
        ratings['records'].pop()
    elif change == 'range':
        ratings['records'][0]['A']['diagnosis']['score'] = 3
    elif change == 'fraction':
        ratings['records'][0]['A']['diagnosis']['score'] = 1.5
    else:
        ratings['records'][0]['A']['diagnosis']['rationale'] = ''
    replace(path, ratings)
    with pytest.raises(ValueError):
        summarize(experiment)
