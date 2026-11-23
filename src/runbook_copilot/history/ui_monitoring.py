"""Dashboard for the same historical investigation flow used in chat."""
import json

import streamlit as st

from runbook_copilot.history.monitoring import (
    load_runs,
    read_feedback,
    regression_candidate,
    save_feedback,
    summarize,
)


def feedback_form(report, key):
    if report.get('status') != 'completed':
        return
    with st.form('feedback-'+key):
        st.caption('Your review is stored locally and linked to this exact answer. No rating is recorded until you submit.')
        rating=st.radio('Was this investigation useful?', ['Useful','Not useful','Needs review'], index=2, key='rating-'+key)
        correction=st.text_area('What helped, or what should change?', max_chars=2000, key='correction-'+key)
        if st.form_submit_button('Save my feedback'):
            save_feedback(report,rating,correction)
            st.success('Feedback saved locally.')


def render():
    st.subheader('History investigations — monitoring and feedback')
    bundled=st.radio('Run collection',['Bundled six model runs','Local recorded runs'])=='Bundled six model runs'
    reports=load_runs(bundled=bundled)
    data=summarize(reports)
    st.caption('Bundled runs are genuine recorded model calls on synthetic cases. Local runs include failures and live-history use; these are different populations.')
    a,b,c=st.columns(3)
    a.metric('Investigations',data['runs'])
    b.metric('Incomplete / failed',data['failures'])
    c.metric('Known investigation cost',f"${data['known_cost_usd']:.4f}")
    st.caption(data['scope']+f" Unknown-cost runs: {data['unknown_cost_runs']}.")
    if not reports:
        st.info('No local history runs yet. Use the bundled collection or complete an investigation.')
        return
    st.dataframe(data['rows'],width='stretch')
    report=st.selectbox('Inspect an investigation',reports,format_func=lambda r:f"{r['run_id'][:8]} · {r['status']} · {'RAG' if r['knowledge_enabled'] else 'history only'} · {r['question'][:75]}")
    st.markdown(report.get('answer','No final answer; inspect the failure trace.'))
    with st.expander('Run trace, citations and provider usage'):
        st.json(report)
    feedback_form(report,'monitor-'+report['run_id'])
    matches=[f for f in read_feedback() if f['run_id']==report['run_id']]
    if matches:
        st.write('Recorded user feedback',matches)
        candidate=regression_candidate(report,matches[0])
        st.download_button('Download for ground-truth review',json.dumps(candidate,indent=2),
                           file_name='review-candidate.json',mime='application/json')
        st.caption('A feedback item is not automatically ground truth. Review the exported candidate before adding it to evaluation.')
