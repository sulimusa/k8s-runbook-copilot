"""Quarantine ambiguous judge deductions; never silently promote them to factual scores."""
from __future__ import annotations

import re


def answer_strings(value):
    if isinstance(value,str):
        return [value]
    if isinstance(value,dict):
        return [s for v in value.values() for s in answer_strings(v)]
    if isinstance(value,list):
        return [s for v in value for s in answer_strings(v)]
    return []


def contextualize(issue, answer):
    """An exact substring is insufficient: preserve the enclosing sentence/condition."""
    quote=issue['quote']
    fields=[text for text in answer_strings(answer) if quote in text]
    if not fields:
        return {**issue,'status':'invalid_quote','context':None}
    text=fields[0]
    start=text.index(quote)
    # Keep the previous sentence too: "Check support. If not, ..." has a dependency.
    sentences=re.split(r'(?<=[.!?])\s+',text)
    context=text
    offset=0
    for i,sentence in enumerate(sentences):
        if offset <= start < offset+len(sentence):
            context=' '.join(sentences[max(0,i-1):i+2])
            break
        offset+=len(sentence)+1
    tentative=re.search(r'\b(if|unless|may|might|could|hypothesis|unclear|unknown|verify|check|ensure|confirm|review|before)\b',context,re.I)
    return {**issue,'context':context,'status':'needs_review_conditional_or_uncertain' if tentative else 'needs_review_affirmative_claim'}


def known_regressions(cases):
    """Explicit developer adjudications, not independent human labels or a model score override."""
    indexed={c['id']:c for c in cases}
    definitions=[
        ('certificate-a','evidence','If not, plan a controlled restart','reject_deduction','The preceding sentence requests verification of reload support. This is conditional advice, not an unsupported claim that reload is unavailable.'),
        ('scaling-b','evidence','ensure that doubling replicas will not exceed the 240-connection cap','reject_deduction','This is a requested check, not a claim that per-replica pool size is known or that scaling is safe.'),
        ('memory-a','rag','directly addressing the cause of the OOMKilled event','accept_defect','A configured potential budget does not prove actual allocation or causality.'),
        ('certificate-a','rag','Investigate why no reload event is logged.','accept_defect','The context says logs are unavailable. This presupposes that no event was logged, which is not established.'),
    ]
    out=[]
    for ident,arm,quote,verdict,reason in definitions:
        answer=indexed[ident]['answers'][arm]
        if not any(quote in s for s in answer_strings(answer)):
            raise ValueError('Known regression answer changed; adjudication must be revisited')
        out.append({'case':ident,'arm':arm,'quote':quote,'verdict':verdict,'reason':reason,
                    'reviewer':'implementation assistant; independent human review pending'})
    return out


def export_queue(output):
    import json

    from eval.knowledge_value.study import read, review_packet, write
    from runbook_copilot.config import ROOT
    source=read(ROOT/'docs/knowledge-value-live-claim-reviewed-results.json')
    result={'method':'Review queue only; no automatically accepted factual scores.',
            'known_regressions':known_regressions(source['cases']),'cases':[]}
    for case in source['cases']:
        directory=ROOT/'eval/reports'/f"knowledge-value-{case['split']}-v3"
        _,mapping=review_packet(directory)
        raw=read(directory/'judgments-factual-v4'/f"{case['id']}.json")
        result['cases'].append({'id':case['id'],'candidates':{
            mapping[case['id']][c['label']]:[contextualize(i,case['answers'][mapping[case['id']][c['label']]]) for i in c['issues']]
            for c in raw['candidates']}})
    write(output,result)
    print(json.dumps({'cases':len(result['cases']),'output':str(output)}))


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    export_queue(parser.parse_args().output)
