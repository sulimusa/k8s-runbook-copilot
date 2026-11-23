import copy
import json
import time
import uuid

import pytest

from runbook_copilot.history.monitoring import (
    finish_metrics,
    read_feedback,
    regression_candidate,
    save_feedback,
    summarize,
)


def report():
    return {'run_id':str(uuid.uuid4()),'status':'completed','structured':{'observations':'Example'},
            'question':'Test question','citations':{},'trace':[{'step':{'action':'runbook'}}],
            'calls':[{'cost_usd':0.01,'input_tokens':20,'output_tokens':10,'duration_ms':100}]}


def test_cost_missing_usage_is_unknown_not_zero():
    known=report()
    unknown=copy.deepcopy(known)
    unknown['calls'][0]['cost_usd']=None
    unknown['status']='failed'
    data=summarize([known,unknown])
    assert data['known_cost_usd']==0.01 and data['unknown_cost_runs']==1
    assert data['failures']==1
    assert data['rows'][0]['retrieval_calls']==1
    finish_metrics(known,time.monotonic()-1)
    assert known['duration_ms']>=1000 and known['model_calls']==1
    assert known['input_tokens']==20 and known['finished_at']


def test_feedback_bound_to_exact_answer_and_requires_human_label(tmp_path):
    r=report()
    db=tmp_path/'feedback.sqlite'
    f=save_feedback(r,'Not useful','Explain the uncertainty.',db)
    assert read_feedback(db)[0]==f
    candidate=regression_candidate(r,f)
    assert candidate['expected_answer'] is None
    assert candidate['status']=='requires_human_ground_truth_review'
    r['structured']['observations']='changed'
    with pytest.raises(ValueError,match='does not match'):
        regression_candidate(r,f)
    with pytest.raises(ValueError):
        save_feedback(r,'Made-up rating',path=db)


def test_default_ui_and_monitoring_need_neither_corpus_nor_cluster(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest

    from runbook_copilot.config import ROOT
    from runbook_copilot.history.monitoring import read_feedback as reader
    monkeypatch.setattr('runbook_copilot.history.chat.HistoryClient.get',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No cluster')))
    monkeypatch.setattr('runbook_copilot.retrieval.search.Retriever.load',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No corpus')))
    monkeypatch.setattr('runbook_copilot.history.ui_monitoring.read_feedback',lambda:reader(tmp_path/'feedback.sqlite'))
    app=AppTest.from_file(str(ROOT/'app/ui.py'),default_timeout=30).run()
    assert not app.exception
    assert app.sidebar.radio[0].value=='Three capstone demos'
    app.sidebar.radio[0].set_value('Monitoring & feedback').run()
    assert not app.exception
    assert app.metric[0].value=='6'
    assert not read_feedback(tmp_path/'feedback.sqlite')
    bundled=json.loads((ROOT/'docs/history-demo-results.json').read_text())
    cost=sum(c['cost_usd'] for arms in bundled['cases'].values() for r in arms.values() for c in r['calls'])
    assert app.metric[2].value==f'${cost:.4f}'
