"""Loopback-only chat for one isolated capstone cluster; production never has write credentials."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import streamlit as st

from runbook_copilot.config import ROOT, get_settings
from runbook_copilot.history.chat import HistoryClient, investigate
from runbook_copilot.history.demo import DemoClient, cases, fixture_digest
from runbook_copilot.history.demo import retriever as demo_retriever
from runbook_copilot.history.repair import DevRepair
from runbook_copilot.history.ui_monitoring import feedback_form
from runbook_copilot.history.ui_monitoring import render as render_monitoring
from runbook_copilot.retrieval.search import Retriever

st.set_page_config(page_title='Cluster History Copilot', page_icon='☸️', layout='wide')
st.title('☸️ Cluster History Copilot')
st.caption('Ask what changed, inspect the evidence, and investigate with runbooks. Dedicated capstone lab.')
api = HistoryClient()


@st.cache_resource
def knowledge():
    return Retriever.load(get_settings())


with st.sidebar:
    st.header('Investigation scope')
    st.write('Cluster: **runbook-capstone**')
    source = st.radio('Evidence source', ['Live cluster history', 'Three capstone demos', 'Monitoring & feedback'], index=1)
    demo = None
    if source == 'Monitoring & feedback':
        demo = None
    elif source == 'Three capstone demos':
        demo = st.selectbox('Historical investigation', cases(), format_func=lambda c: c['title'])
        namespace, days = demo['namespace'], demo['days']
        api = DemoClient(demo)
    else:
        namespace = st.selectbox('Environment', ['prod-capstone', 'dev-capstone'])
        days = st.selectbox('Look back', [7, 30, 1], format_func=lambda n: f'Last {n} days')
    use_rag = st.toggle('Retrieve operational knowledge', value=True)
    st.caption('Turn retrieval off to compare an investigation using the same history tools.')
    st.caption('Production: read-only. Dev: one explicit, guarded Service-selector repair.')
    if source == 'Live cluster history':
        st.write(f'Knowledge base: {len(knowledge().chunks)} chunks')
    if st.button('Refresh collected history'):
        st.rerun()
    st.caption('Older rollout scenarios remain supporting regression tests; historical investigation is the main flow.')

if source == 'Monitoring & feedback':
    render_monitoring()
    st.stop()

scope = (namespace, days, demo['id'] if demo else None, use_rag)
if st.session_state.get('scope') != scope:
    st.session_state.scope = scope
    st.session_state.messages = []
    st.session_state.reports = []
try:
    coverage = api.get('coverage', namespace=namespace)
    clock = datetime.fromisoformat(demo['as_of']) if demo else datetime.now(timezone.utc)
    since = (clock - timedelta(days=days)).isoformat()
    history = api.get('history', namespace=namespace, since=since, limit=100)
except Exception:
    st.error('History service is unavailable. Start the dedicated capstone collector; no other cluster is used as a fallback.')
    st.stop()
if demo:
    st.warning('Synthetic history snapshot at '+demo['as_of']+'. This is not a live cluster incident. Repairs are disabled.')
    st.write(demo['question'])
    recorded = ROOT / 'docs/history-demo-results.json'
    if recorded.exists():
        saved = json.loads(recorded.read_text())
        with st.expander('Recorded model comparison — no API call'):
            st.caption('Recorded development runs, not a guarantee of correct diagnosis. Inspect evidence and review notes.')
            if saved.get('review_notes', {}).get(demo['id']):
                st.info(saved['review_notes'][demo['id']])
            if saved.get('fixture_sha256') != fixture_digest():
                st.warning('These recorded answers predate the current fixtures; rerun the comparison before using them as evidence.')
            left, right = st.columns(2)
            for column, arm in [(left, 'evidence'), (right, 'rag')]:
                with column:
                    st.subheader('History + RAG' if arm == 'rag' else 'History only')
                    r = saved['cases'][demo['id']][arm]
                    st.markdown(r.get('answer', 'Run failed; inspect evidence.'))
                    with st.expander('Tool trace and citations'):
                        st.json(r)
                    with st.expander('Review this answer'):
                        feedback_form(r, 'recorded-'+r['run_id'])
            reviewed = ROOT / 'docs/history-demo-adjudications.json'
            if reviewed.exists():
                audit = json.loads(reviewed.read_text())
                current_hash = hashlib.sha256(json.dumps(saved, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if audit.get('results_sha256') == current_hash:
                    with st.expander('Judge findings and developer review'):
                        st.caption('Raw model findings and explicit developer decisions. These are not independent human labels or accuracy scores.')
                        for arm, decision in audit['cases'][demo['id']].items():
                            st.write('History + RAG' if arm == 'rag' else 'History only')
                            st.write('Next check from the actual answer: '+decision['next_check_quote'])
                            for finding in decision['findings']:
                                st.write('Judge flagged: '+finding['quote'])
                                st.write('Review: '+finding['verdict'].replace('_',' ')+' — '+finding['review_reason'])
                            if not decision['findings']:
                                st.write('No automated finding; full answer also reviewed by the implementation assistant.')
                else:
                    st.warning('Saved review is stale for these answers; do not use its verdicts.')
st.info(f"History available since {coverage['history_available_since']}. Earlier changes are unknown. "
        'Times below are UTC observations, not audit timestamps.')
st.caption(coverage['limits'])
if not coverage.get('healthy'):
    st.error('Some collection streams are missing, stale or failing. Treat current evidence as incomplete.')
if coverage['gaps']:
    st.warning('Collection interruptions are recorded. Review coverage before relying on a complete timeline.')
with st.expander('Collector coverage and freshness'):
    st.json(coverage)
with st.expander(f"Recent timeline — {history['total']} records in selected window"):
    st.dataframe([{k: r[k] for k in ('id', 'observed_at', 'kind', 'name', 'operation')}
                  for r in history['records']], width='stretch')
    if history['truncated']:
        st.caption('Showing the most recent 100 records. Chat can narrow by resource kind and name.')
    st.caption('BASELINE = first observed state, not a change at that time.')

for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message['role']):
        st.markdown(message['content'])
        if message.get('report'):
            st.caption('Evidence IDs: ' + ', '.join(message['report'].get('citations', {})))
            st.caption(message['report'].get('verification_note', 'Past answer; check current observations before acting.'))
            with st.expander('Evidence, tool choices and limitations'):
                st.json(message['report'])
            feedback_form(message['report'], 'chat-'+message['report']['run_id'])
if not demo:
    st.caption('Try: “What changed for demo-web this week?” or '
               '“What deployments were observed last month, and what history is missing?”')
run_demo = st.button('Investigate this demo with the model', type='primary') if demo else False
question = st.chat_input('Ask about this cluster and time window')
if run_demo:
    question = demo['question']
if question:
    prior = list(st.session_state.messages)
    st.session_state.messages.append({'role': 'user', 'content': question})
    with st.chat_message('user'):
        st.write(question)
    with st.chat_message('assistant'):
        try:
            with st.spinner('Checking history, resource state and runbooks…'):
                report = investigate(question, namespace, days, demo_retriever(demo) if demo else knowledge(), prior,
                                     client=api, knowledge_enabled=use_rag, now=clock)
            st.markdown(report['answer'])
            st.caption('Evidence IDs: ' + ', '.join(report['citations']))
            st.caption(report['verification_note'])
            with st.expander('Evidence and tool choices'):
                st.json(report)
            st.session_state.messages.append({'role': 'assistant', 'content': report['answer'], 'report': report})
        except Exception as exc:
            st.error(f'Investigation could not finish ({type(exc).__name__}). No changes were made. '
                     'The timeline remains available; check model budget or collector status.')

if demo:
    st.caption('Demonstration snapshots have no repair controls or Kubernetes connection.')
    st.stop()
st.divider()
st.subheader('Reviewed dev repair')
if namespace == 'prod-capstone':
    st.write('Production is read-only. Chat can suggest a repair; no Apply control or production writer exists.')
else:
    changes = api.get('history', namespace=namespace, since=since, kind='Service', limit=100)['records']
    services = {x['uid']: x for x in api.get('current', namespace=namespace, kind='Service')['items']}
    pods = api.get('current', namespace=namespace, kind='Pod')['items']
    candidates = [r for r in changes if r.get('before') and r.get('after')
                  and r['before'].get('selector_complete') and r['before'].get('selector')
                  and r['before']['selector'] != r['after'].get('selector')
                  and services.get(r['uid'], {}).get('resource_version') == r['rv']
                  and any(all(p.get('labels', {}).get(k) == v for k, v in r['before']['selector'].items()) for p in pods)]
    if candidates:
        choice = st.selectbox('Recorded selector change to reverse', candidates,
                              format_func=lambda r: f"{r['id']} · {r['name']} · {r['observed_at']}")
        st.write({'current_recorded_selector': choice['after'].get('selector'),
                  'proposed_previous_selector': choice['before'].get('selector')})
        st.caption('Checks cluster identity, dev policy, matching pods and resource version; verifies ready endpoints. '
                   'If verification fails, attempts a guarded rollback. It does not test the application response.')
        if st.button('Restore previous selector in dev', type='secondary'):
            try:
                with st.spinner('Validating and applying the reviewed dev repair…'):
                    result = DevRepair(coverage['cluster_uid']).restore(namespace, choice)
                st.json(result)
            except Exception as exc:
                st.error(str(exc))
    else:
        st.write('No recorded Service-selector change is available to reverse.')
