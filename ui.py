import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:1234")

st.set_page_config(page_title="Support Ticket AI", layout="wide")
st.title("Support Ticket AI System")

tab_query, tab_anomalies = st.tabs(["Ask a question", "Anomalies"])

with tab_query:
    question = st.text_input("Ask a question about the support tickets:")
    if st.button("Ask") and question.strip():
        with st.spinner("Querying..."):
            try:
                resp = requests.post(f"{API_BASE}/query", json={"question": question}, timeout=60)
                if resp.ok:
                    st.write(resp.json()["answer"])
                else:
                    st.error(resp.json().get("detail", resp.text))
            except requests.RequestException as exc:
                st.error(f"Could not reach API: {exc}")

with tab_anomalies:
    if st.button("Run anomaly detection"):
        with st.spinner("Checking..."):
            try:
                resp = requests.get(f"{API_BASE}/anomalies", timeout=30)
                if resp.ok:
                    data = resp.json()
                    st.subheader("Stale high-priority tickets (unresolved > 24h)")
                    stale = data.get("stale_high_priority", [])
                    if stale:
                        st.dataframe(pd.DataFrame(stale))
                    else:
                        st.write("None found.")

                    st.subheader("Abnormally long resolution times (per-category z-score)")
                    long_res = data.get("long_resolution_times", [])
                    if long_res:
                        st.dataframe(pd.DataFrame(long_res))
                    else:
                        st.write("None found.")
                else:
                    st.error(resp.json().get("detail", resp.text))
            except requests.RequestException as exc:
                st.error(f"Could not reach API: {exc}")
