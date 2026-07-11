# app.py
import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
import tempfile

# ---- Database URL (replace with your own public URL) ----
DB_URL = "https://your-public-url.com/connections.db"  # <-- CHANGE THIS
DB_FILE = "connections.db"

# ---- Download database if not present ----
@st.cache_resource
def load_database():
    if not os.path.exists(DB_FILE):
        st.info("Downloading database (315 MB) – this may take a few minutes...")
        try:
            response = requests.get(DB_URL, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            with open(DB_FILE, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            st.success("Database downloaded successfully.")
        except Exception as e:
            st.error(f"Failed to download database: {e}")
            st.stop()
    return sqlite3.connect(DB_FILE, check_same_thread=False)

conn = load_database()

# ---- Load options (cached) ----
@st.cache_data
def load_options():
    hubs = pd.read_sql_query("SELECT DISTINCT pulte_subdomain FROM connections WHERE pulte_subdomain IS NOT NULL ORDER BY pulte_subdomain LIMIT 500", conn)
    hubs_list = hubs['pulte_subdomain'].tolist()
    tags_df = pd.read_sql_query("SELECT DISTINCT fraud_risk_tags FROM connections WHERE fraud_risk_tags IS NOT NULL", conn)
    tags_set = set()
    for t in tags_df['fraud_risk_tags']:
        if t:
            for tag in t.split(', '):
                tags_set.add(tag)
    return hubs_list, sorted(tags_set)

hubs_list, categories = load_options()

# ---- Streamlit UI ----
st.set_page_config(page_title="Connections +", layout="wide")
st.title("🔗 Connections +")
st.markdown("Find IP + CNAME overlaps between a hub domain and other domains by risk category.")

col1, col2, col3 = st.columns(3)

with col1:
    hub_choice = st.selectbox("Hub Domain", options=[""] + hubs_list, index=0)
    custom_hub = st.text_input("Or type custom domain", placeholder="e.g. portal.pulte.com")

with col2:
    category_choice = st.selectbox("Risk Category", options=[""] + categories, index=0)

with col3:
    domain_search = st.text_input("Overlap Domain (optional)", placeholder="e.g. relativity.com")

search_clicked = st.button("🔍 Search", type="primary")

# ---- Search logic ----
if search_clicked:
    hub = custom_hub.strip() if custom_hub else hub_choice
    category = category_choice
    domain = domain_search.strip()

    if not hub and not category and not domain:
        st.warning("Please enter at least one search criterion.")
    else:
        query = """
            SELECT ip, pulte_subdomain, overlap_subdomain, fraud_risk_tags, cname_evidence, cname_shared
            FROM connections
            WHERE 1=1
        """
        params = []
        if hub:
            query += " AND pulte_subdomain = ?"
            params.append(hub)
        if category:
            query += " AND fraud_risk_tags LIKE ?"
            params.append(f'%{category}%')
        if domain:
            query += " AND overlap_subdomain LIKE ?"
            params.append(f'%{domain}%')
        query += " LIMIT 1000"

        try:
            df_result = pd.read_sql_query(query, conn, params=params)
            if df_result.empty:
                st.info("No results found.")
            else:
                st.success(f"Found {len(df_result)} rows")
                def highlight_risk(row):
                    tags = row['fraud_risk_tags'] or ''
                    if any(k in tags for k in ['Illegal', 'Identity', 'Money', 'Inmate']):
                        return ['background-color: #ffcccc'] * len(row)
                    return [''] * len(row)
                st.dataframe(df_result.style.apply(highlight_risk, axis=1), use_container_width=True)
        except Exception as e:
            st.error(f"Query error: {e}")

# ---- Stats ----
if st.checkbox("Show database stats"):
    total = pd.read_sql_query("SELECT COUNT(*) FROM connections", conn).iloc[0,0]
    st.write(f"Total rows: {total}")