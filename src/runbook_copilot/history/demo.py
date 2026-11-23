"""Synthetic, fixed-clock history snapshots. No cluster access or answer keys."""
from __future__ import annotations

import copy
import json
from datetime import datetime

from ..config import ROOT
from ..retrieval.search import Retriever
from ..schemas import Chunk
from .store import Store


def cases():
    return json.loads((ROOT / 'data/history_demo/cases.json').read_text())


class DemoClient:
    data_origin = 'synthetic_history_snapshot'

    def __init__(self, case):
        self.case = copy.deepcopy(case)

    def get(self, route, **params):
        Store.scope(params.get('namespace'), params.get('kind'))
        if params['namespace'] != self.case['namespace']:
            raise ValueError('Demo namespace mismatch')
        if route == 'coverage':
            return copy.deepcopy(self.case['coverage'])
        if route not in ('history', 'current'):
            raise ValueError('Unsupported read route')
        items = self.case[route]
        items = [r for r in items if all(params.get(k) is None or r[k] == params[k] for k in ('kind', 'name'))]
        if route == 'history':
            since = datetime.fromisoformat(params['since'])
            items = sorted([r for r in items if datetime.fromisoformat(r['observed_at']) >= since],
                           key=lambda r: (r['observed_at'], r['id']), reverse=True)
            limit = max(1, min(100, params.get('limit', 50)))
            return copy.deepcopy({'records': items[:limit], 'total': len(items), 'truncated': len(items) > limit})
        return copy.deepcopy({'items': items, 'total': len(items)})


def retriever(case, public=()):
    """Filter fictional contracts by explicit scenario metadata, never by answer keys."""
    docs = json.loads((ROOT / 'data/history_demo/documents.json').read_text())
    scope, when = case['scope'], datetime.fromisoformat(case['as_of'])
    eligible = [d for d in docs if (d['service'] is None or
                (d['service'] == scope['service'] and d['version'] == scope['version'] and d['namespace'] == scope['namespace']))
                and datetime.fromisoformat(d['valid_from']) <= when
                and (not d['valid_until'] or when < datetime.fromisoformat(d['valid_until']))]
    chunks = [c for c in public if c.source_id in ('k8s-docs', 'k8s-runbooks')]
    chunks += [Chunk(chunk_id=d['id'], source_id='history-demo', doc_path=d['id'], url='',
                     title=d['title'], heading_path=d['title'], text=d['text'], license='Apache-2.0', commit_sha='synthetic-v1')
               for d in eligible]
    return Retriever(chunks)


def fixture_digest():
    import hashlib
    payload = (ROOT / 'data/history_demo/cases.json').read_bytes() + (ROOT / 'data/history_demo/documents.json').read_bytes()
    return hashlib.sha256(payload).hexdigest()
