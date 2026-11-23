"""Independent-context factual review of the six demonstration answers."""
import argparse
import json
from pathlib import Path

from eval.knowledge_value.factual_review import SYSTEM, FactualReview, validate
from eval.knowledge_value.study import digest
from runbook_copilot.atlas_runtime import configured_model


def review(directory):
    results=json.loads((directory/'results.json').read_text())
    target=directory/'factual-review.json'
    if target.exists():
        raise FileExistsError(target)
    model=configured_model(FactualReview,judge=True,max_output=1400)
    output={'system_sha256':digest(SYSTEM),'results_sha256':digest(results),'cases':{}}
    for ident,arms in results['cases'].items():
        output['cases'][ident]={}
        for arm,r in arms.items():
            candidate={'available_context':{'coverage':r['coverage'],'evidence':r['citations'],'tools':[t['result'] for t in r['trace']]},
                       'answer':r['structured'],'generation_failed':r['status']!='completed'}
            messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(candidate)}]
            reply=model(messages)
            raw=json.loads(reply.text)
            output['cases'][ident][arm]={'issues':validate(raw,candidate)['issues'],'provider':model.calls[-1],
                                         'packet_sha256':digest(candidate)}
            print(json.dumps({'case':ident,'arm':arm,'issues':output['cases'][ident][arm]['issues']}),flush=True)
    target.write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    review(p.parse_args().directory)
