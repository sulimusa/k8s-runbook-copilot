"""Read-only list/watch collector. Watch checkpoints survive process restarts."""
from __future__ import annotations

import logging
import threading
import time

from kubernetes import client, config, watch
from kubernetes.client.exceptions import ApiException

from .store import KINDS, NAMESPACES, Store

log = logging.getLogger(__name__)


class Collector:
    def __init__(self, path, expected_uid):
        config.load_incluster_config()  # No host default context; mounted SA token refreshes automatically.
        self.api = client.ApiClient()
        core, apps, discovery = client.CoreV1Api(self.api), client.AppsV1Api(self.api), client.DiscoveryV1Api(self.api)
        uid = core.read_namespace('kube-system').metadata.uid
        if uid != expected_uid:
            raise ValueError('Cluster identity mismatch')
        self.store = Store(path, uid)
        self.methods = dict(zip(KINDS, (core.list_namespaced_pod, apps.list_namespaced_deployment,
                                        apps.list_namespaced_replica_set, core.list_namespaced_service,
                                        discovery.list_namespaced_endpoint_slice, core.list_namespaced_event)))
        self.stop = threading.Event()

    def start(self):
        for ns in NAMESPACES:
            for kind in KINDS:
                threading.Thread(target=self.collect, args=(ns, kind), daemon=True).start()

    def collect(self, ns, kind):
        method = self.methods[kind]
        previous = self.store.stream(ns, kind)
        rv = previous['rv'] if previous else None
        if previous:
            self.store.gap(ns, kind, 'Collector restarted; resumed watch may catch up. Downtime is not continuous observation.')
        while not self.stop.is_set():
            try:
                if not rv:
                    raw = self.api.sanitize_for_serialization(method(ns, _request_timeout=20))
                    items = [dict(x, kind=kind) for x in raw['items']]
                    self.store.reconcile(ns, kind, items, raw['metadata']['resourceVersion'], initial=previous is None)
                    rv = raw['metadata']['resourceVersion']
                    previous = True
                stream = watch.Watch()
                try:
                    for event in stream.stream(method, namespace=ns, resource_version=rv,
                                               timeout_seconds=25, allow_watch_bookmarks=True, _request_timeout=35):
                        if self.stop.is_set():
                            break
                        obj = event['raw_object']
                        if event['type'] == 'BOOKMARK':
                            rv = obj['metadata']['resourceVersion']
                            self.store.heartbeat(ns, kind, rv)
                        elif event['type'] in ('ADDED', 'MODIFIED', 'DELETED'):
                            obj['kind'] = kind
                            self.store.record(obj, event['type'])
                            rv = obj['metadata']['resourceVersion']
                finally:
                    stream.stop()
                self.store.heartbeat(ns, kind, rv)
                self.store.prune()
            except Exception as exc:
                # Exception text can contain server response bodies. Persist only the class/status.
                reason = f'{type(exc).__name__}:{getattr(exc, "status", "connection")}'
                self.store.heartbeat(ns, kind, error=reason)
                self.store.gap(ns, kind, reason)
                log.warning('Watch interrupted namespace=%s kind=%s error=%s', ns, kind, reason)
                if isinstance(exc, ApiException) and exc.status == 410:
                    rv = None
                self.stop.wait(5)
            time.sleep(0.05)
