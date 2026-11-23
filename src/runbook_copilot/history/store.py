"""Transactional watch checkpoints and semantic changes; never a Kubernetes audit log."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

KINDS = ('Pod', 'Deployment', 'ReplicaSet', 'Service', 'EndpointSlice', 'Event')
NAMESPACES = ('dev-capstone', 'prod-capstone')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def labels(value):
    # Values can be sensitive even in labels. Only retain this lab's explicit routing labels.
    return {k: v for k, v in (value or {}).items()
            if k in {'app', 'version', 'environment', 'kubernetes.io/service-name'}}



def normalize_times(value):
    """LIST serializer emits +00:00; WATCH JSON emits Z. Do not call that a change."""
    if isinstance(value, list):
        return [normalize_times(x) for x in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ('created_at', 'event_at', 'startedAt', 'finishedAt') and v:
                out[k] = datetime.fromisoformat(v.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
            else:
                out[k] = normalize_times(v)
        return out
    return value

def project(obj):
    """Positive allowlist. No raw objects, env values, annotations, messages, logs or secrets."""
    m, spec, status = obj['metadata'], obj.get('spec', {}), obj.get('status', {})
    kind = obj['kind']
    out = {'kind': kind, 'name': m['name'], 'namespace': m['namespace'], 'uid': m['uid'],
           'labels': labels(m.get('labels')), 'created_at': m.get('creationTimestamp'),
           'owners': [{k: r.get(k) for k in ('kind', 'name', 'uid', 'controller')}
                      for r in m.get('ownerReferences', [])]}
    if kind in ('Pod', 'Deployment', 'ReplicaSet'):
        ps = spec if kind == 'Pod' else spec.get('template', {}).get('spec', {})
        out['containers'] = [{'name': c['name'], 'image': c.get('image'),
                              'resources': c.get('resources', {})} for c in ps.get('containers', [])]
        out['replicas'] = spec.get('replicas')
        out['ready_replicas'] = status.get('readyReplicas')
        out['phase'] = status.get('phase')
        out['conditions'] = [{k: c.get(k) for k in ('type', 'status', 'reason')}
                             for c in status.get('conditions', [])]
        out['container_status'] = [{'name': c['name'], 'ready': c.get('ready'),
                                   'restart_count': c.get('restartCount'),
                                   'state': {t: {k: v.get(k) for k in ('reason', 'exitCode', 'startedAt', 'finishedAt')}
                                             for t, v in c.get('state', {}).items()},
                                   'last_termination': {k: c.get('lastState', {}).get('terminated', {}).get(k)
                                                        for k in ('reason', 'exitCode', 'finishedAt')}}
                                  for c in status.get('containerStatuses', [])]
        if kind != 'Pod':
            out['selector'] = labels(spec.get('selector', {}).get('matchLabels'))
            out['template_labels'] = labels(spec.get('template', {}).get('metadata', {}).get('labels'))
    elif kind == 'Service':
        # Unsupported selector keys are flagged: never use a partial selector for a fix.
        out['selector'] = labels(spec.get('selector'))
        out['selector_complete'] = out['selector'] == spec.get('selector', {})
        out['ports'] = [{k: p.get(k) for k in ('name', 'port', 'targetPort', 'protocol')}
                        for p in spec.get('ports', [])]
    elif kind == 'EndpointSlice':
        out['endpoints'] = [{'ready': e.get('conditions', {}).get('ready'),
                             'target': {k: e.get('targetRef', {}).get(k) for k in ('kind', 'name', 'uid')}}
                            for e in (obj.get('endpoints') or [])]
    elif kind == 'Event':
        out.update(reason=obj.get('reason'), event_type=obj.get('type'), count=obj.get('count'),
                   event_at=obj.get('eventTime') or obj.get('lastTimestamp') or obj.get('firstTimestamp'),
                   involved={k: obj.get('involvedObject', {}).get(k) for k in ('kind', 'name', 'uid')})
    return normalize_times(out)


class Store:
    def __init__(self, path, cluster_uid, cluster_name='runbook-capstone'):
        self.path, self.uid, self.name = str(path), cluster_uid, cluster_name
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS streams (
                    namespace TEXT, kind TEXT, rv TEXT, started TEXT, heartbeat TEXT, error TEXT,
                    PRIMARY KEY(namespace,kind));
                CREATE TABLE IF NOT EXISTS objects (
                    namespace TEXT, kind TEXT, uid TEXT PRIMARY KEY, rv TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, namespace TEXT, kind TEXT, uid TEXT, name TEXT,
                    rv TEXT, operation TEXT, observed_at TEXT, before_json TEXT, after_json TEXT,
                    UNIQUE(uid,rv,operation));
                CREATE INDEX IF NOT EXISTS history_scope ON history(namespace,observed_at);
                CREATE TABLE IF NOT EXISTS gaps (
                    id INTEGER PRIMARY KEY, namespace TEXT, kind TEXT, at TEXT, reason TEXT);
            ''')
            old = db.execute("SELECT value FROM meta WHERE key='cluster_uid'").fetchone()
            if old and old[0] != cluster_uid:
                raise ValueError('History database belongs to a different cluster; refusing to mix data')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('cluster_uid',?)", (cluster_uid,))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('started',?)", (now(),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def scope(namespace, kind=None):
        if namespace not in NAMESPACES or (kind is not None and kind not in KINDS):
            raise ValueError('Scope is outside the capstone allowlist')

    def stream(self, namespace, kind):
        self.scope(namespace, kind)
        with self.db() as db:
            row = db.execute('SELECT * FROM streams WHERE namespace=? AND kind=?', (namespace, kind)).fetchone()
            return dict(row) if row else None

    def heartbeat(self, namespace, kind, rv=None, error=None):
        self.scope(namespace, kind)
        at = now()
        with self.db() as db:
            db.execute('INSERT INTO streams VALUES (?,?,?,?,?,?) ON CONFLICT(namespace,kind) DO UPDATE '
                       'SET rv=COALESCE(excluded.rv,streams.rv),heartbeat=excluded.heartbeat,error=excluded.error',
                       (namespace, kind, rv, at, at, error))

    def gap(self, namespace, kind, reason):
        self.scope(namespace, kind)
        with self.db() as db:
            db.execute('INSERT INTO gaps(namespace,kind,at,reason) VALUES (?,?,?,?)', (namespace, kind, now(), reason))

    def record(self, obj, operation, checkpoint=True):
        body = project(obj)
        ns, kind, uid, rv = body['namespace'], body['kind'], body['uid'], obj['metadata']['resourceVersion']
        self.scope(ns, kind)
        at = now()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT body FROM objects WHERE uid=?', (uid,)).fetchone()
            before = json.dumps(normalize_times(json.loads(old[0])), sort_keys=True) if old else None
            after = None if operation == 'DELETED' else json.dumps(body, sort_keys=True)
            if before != after:
                db.execute('INSERT OR IGNORE INTO history(namespace,kind,uid,name,rv,operation,observed_at,before_json,after_json) '
                           'VALUES (?,?,?,?,?,?,?,?,?)', (ns, kind, uid, body['name'], rv, operation, at, before, after))
            if after is None:
                db.execute('DELETE FROM objects WHERE uid=?', (uid,))
            else:
                db.execute('INSERT INTO objects VALUES (?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET rv=excluded.rv,body=excluded.body',
                           (ns, kind, uid, rv, after))
            if checkpoint:
                db.execute('INSERT INTO streams VALUES (?,?,?,?,?,NULL) ON CONFLICT(namespace,kind) DO UPDATE '
                           'SET rv=excluded.rv,heartbeat=excluded.heartbeat,error=NULL', (ns, kind, rv, at, at))

    def reconcile(self, namespace, kind, items, rv, initial=False):
        self.scope(namespace, kind)
        with self.db() as db:
            old = db.execute('SELECT uid,body FROM objects WHERE namespace=? AND kind=?', (namespace, kind)).fetchall()
        seen = {x['metadata']['uid'] for x in items}
        for item in items:
            self.record(item, 'BASELINE' if initial else 'RECONCILED', checkpoint=False)
        for item in old:
            if item['uid'] not in seen:
                body = json.loads(item['body'])
                self.record({'kind': kind, 'metadata': {'namespace': namespace, 'name': body['name'],
                            'uid': item['uid'], 'resourceVersion': rv}}, 'DELETED', checkpoint=False)
        # Only advance list checkpoint after all items. A crash before this safely replays the list.
        self.heartbeat(namespace, kind, rv)

    def coverage(self, namespace):
        self.scope(namespace)
        with self.db() as db:
            streams = [dict(r) for r in db.execute('SELECT * FROM streams WHERE namespace=?', (namespace,))]
            gaps = [dict(r) for r in db.execute('SELECT * FROM gaps WHERE namespace=? ORDER BY id DESC LIMIT 50', (namespace,))]
            start = db.execute("SELECT value FROM meta WHERE key='started'").fetchone()[0]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        healthy = len(streams) == len(KINDS) and all(not s['error'] and s['rv'] and
            (datetime.now(timezone.utc) - datetime.fromisoformat(s['heartbeat'])).total_seconds() < 75
            for s in streams)
        return {'healthy': bool(healthy), 'cluster': self.name, 'cluster_uid': self.uid, 'namespace': namespace,
                'collection_started': start, 'history_available_since': max(start, cutoff),
                'retention_days': 30, 'streams': streams, 'gaps': gaps,
                'limits': 'Observation times are not audit times. No pre-collection history; gaps may miss intermediate changes. '
                          'Only listed resource kinds and allowlisted fields are collected. No logs, metrics, secrets, env values or actor identities.'}

    def query(self, namespace, since, kind=None, name=None, limit=50):
        self.scope(namespace, kind)
        parsed = datetime.fromisoformat(since)
        if parsed.tzinfo is None:
            raise ValueError('Timezone required')
        since = parsed.astimezone(timezone.utc).isoformat()
        limit = max(1, min(200, limit))
        args = [namespace, since, kind, kind, name, name]
        with self.db() as db:
            total = db.execute('SELECT COUNT(*) FROM history WHERE namespace=? AND observed_at>=? '
                               'AND (? IS NULL OR kind=?) AND (? IS NULL OR name=?)', args).fetchone()[0]
            rows = db.execute('SELECT * FROM history WHERE namespace=? AND observed_at>=? '
                              'AND (? IS NULL OR kind=?) AND (? IS NULL OR name=?) '
                              'ORDER BY id DESC LIMIT ?', [*args, limit]).fetchall()
        records = []
        for row in rows:
            r = dict(row)
            r['id'] = f"H{r['id']}"
            r['before'] = json.loads(r.pop('before_json') or 'null')
            r['after'] = json.loads(r.pop('after_json') or 'null')
            records.append(r)
        return {'records': records, 'total': total, 'truncated': total > limit, 'coverage': self.coverage(namespace)}

    def current(self, namespace, kind=None, name=None):
        self.scope(namespace, kind)
        with self.db() as db:
            rows = db.execute('SELECT body,rv FROM objects WHERE namespace=?', (namespace,)).fetchall()
        items = [dict(json.loads(r['body']), resource_version=r['rv']) for r in rows]
        items = [x for x in items if (not kind or x['kind'] == kind) and (not name or x['name'] == name)]
        return {'items': items[:200], 'total': len(items), 'truncated': len(items) > 200,
                'coverage': self.coverage(namespace)}

    def prune(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        with self.db() as db:
            db.execute('DELETE FROM history WHERE observed_at<?', (cutoff,))
            db.execute('DELETE FROM gaps WHERE at<?', (cutoff,))
