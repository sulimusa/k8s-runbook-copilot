import copy
import json
import shutil

import pytest

from eval.incident_eval import (
    ROOT,
    SUITE,
    Prediction,
    make_prompt,
    read_json,
    review_status,
    score,
    validate_suite,
)


def fixture():
    inputs=read_json(SUITE/'inputs.json')
    keys=read_json(SUITE/'answer_keys.json')
    return inputs,keys


def test_structure_and_family_split_integrity():
    inputs,keys=fixture()
    assert validate_suite(inputs,keys)['cases']==36
    wrong=copy.deepcopy(keys)
    wrong[0]['split']='different'
    with pytest.raises(ValueError,match='crosses'):
        validate_suite(inputs,wrong)


def test_prompt_has_no_answers_company_or_variant_in_baseline():
    inputs,keys=fixture()
    for case,key in zip(inputs,keys,strict=True):
        prompt=make_prompt(case)
        payload=json.loads(prompt['messages'][1]['content'])
        assert payload['case']==case
        assert payload['historical_patterns']==[]
        assert key['source_url'] not in prompt['messages'][1]['content']
        assert key['source_company'] not in prompt['messages'][1]['content']
        assert 'expected_cause' not in prompt['messages'][1]['content']
        assert 'variant' not in prompt['messages'][1]['content']


def test_prompt_refuses_injected_answer_key_fields():
    case=fixture()[0][0] | {'expected_cause':'leaked'}
    with pytest.raises(ValueError,match='leakage'):
        make_prompt(case)


def test_patterns_are_separate_and_bounded():
    patterns=read_json(ROOT/'data'/'incident_patterns.json')
    inputs,_=fixture()
    p=make_prompt(inputs[0],patterns)
    refs=json.loads(p['messages'][1]['content'])['historical_patterns']
    assert len(refs)==3
    assert p['allowed_reference_ids']==[x['id'] for x in refs]
    assert all('expected_cause' not in x and 'variant' not in x for x in refs)


def prediction(case,**changes):
    values={'id':case['id'],'status':'supported','diagnosis':'Test-only placeholder',
            'confidence':0.8,'evidence':[{'evidence_id':'E2','quote':case['evidence'][1]['text']}],
            'next_checks':['Inspect audit events.'],'diagnostic_commands':['kubectl get pods'],
            'reference_ids':[]}
    values.update(changes)
    return Prediction.model_validate(values)


def test_fake_citations_and_write_commands_do_not_pass_proxies():
    inputs,keys=fixture()
    bad=prediction(inputs[0],evidence=[{'evidence_id':'E99','quote':'invented'}],
                   diagnostic_commands=['kubectl delete nodes --all'],reference_ids=['P99'])
    result=score(inputs[0],keys[0],bad)
    assert result['citation_integrity'] is False
    assert result['has_valid_evidence'] is False
    assert result['unsafe_commands']
    assert result['invalid_reference_ids']==['P99']


def test_quote_must_belong_to_cited_evidence_and_wrong_diagnosis_not_graded_as_correct():
    inputs,keys=fixture()
    wrong=prediction(inputs[0],evidence=[{'evidence_id':'E1','quote':inputs[0]['evidence'][1]['text']}])
    assert score(inputs[0],keys[0],wrong)['citation_integrity'] is False
    result=score(inputs[0],keys[0],prediction(inputs[0]))
    assert result['decisive_evidence_recall']==0.5
    assert result['semantic_correctness'].startswith('not_scored')


def test_empty_evidence_not_reported_as_grounded():
    inputs,keys=fixture()
    result=score(inputs[0],keys[0],prediction(inputs[0],evidence=[]))
    assert result['has_valid_evidence'] is False
    assert result['decisive_evidence_recall']==0


def test_missing_evidence_requires_uncertainty():
    inputs,keys=fixture()
    case=inputs[2]
    pred=Prediction(id=case['id'],status='supported',diagnosis='A guessed cause',confidence=1,
                    evidence=[],next_checks=[],diagnostic_commands=[],reference_ids=[])
    result=score(case,keys[2],pred)
    assert result['decision_agreement'] is False
    assert result['overconfident_on_missing_evidence'] is True
    abstention=pred.model_copy(update={'status':'insufficient_evidence'})
    assert score(case,keys[2],abstention)['overconfident_on_missing_evidence'] is False


def test_review_is_current_and_future_edits_invalidate_it(tmp_path):
    assert review_status()['cases']==36
    shutil.copytree(SUITE,tmp_path/'eval'/'incident_suite')
    (tmp_path/'data').mkdir()
    shutil.copyfile(ROOT/'data'/'incident_patterns.json',tmp_path/'data'/'incident_patterns.json')
    assert review_status(tmp_path)['human_review']=='pending'
    with (tmp_path/'eval'/'incident_suite'/'inputs.json').open('a') as f:
        f.write('\n')
    with pytest.raises(ValueError,match='Stale judge review'):
        review_status(tmp_path)
