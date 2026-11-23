"""Read-only, loopback-exposed capstone history API. No model credentials or write routes."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from runbook_copilot.history.collector import Collector
from runbook_copilot.history.store import NAMESPACES


@asynccontextmanager
async def lifespan(app):
    collector = Collector(os.environ['HISTORY_DB'], os.environ['CLUSTER_UID'])
    app.state.collector = collector
    collector.start()
    yield
    collector.stop.set()


app = FastAPI(lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'cluster': 'runbook-capstone', 'namespaces': NAMESPACES}


def run(method, *args):
    try:
        return getattr(app.state.collector.store, method)(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get('/coverage')
def coverage(namespace: str):
    return run('coverage', namespace)


@app.get('/history')
def history(namespace: str, since: str, kind: str | None = None, name: str | None = None, limit: int = 50):
    return run('query', namespace, since, kind, name, limit)


@app.get('/current')
def current(namespace: str, kind: str | None = None, name: str | None = None):
    return run('current', namespace, kind, name)
