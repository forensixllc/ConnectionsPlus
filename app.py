# ============================================================
# Pulte + – Streamlit App
# Minimal dark theme, two dropdowns, search
# ============================================================

import streamlit as st
import sqlite3
import pandas as pd
import os
import requests

# --- Database setup: download from Dropbox if not present ---
DB_URL = "https://www.dropbox.com/scl/fi/o5dzs9d5fjljv9ffb2esb/connections.db?rlkey=mn3eykkderzrrcebexilfvzvt&st=5vrtsi6z&dl=1"  # direct download
DB_PATH = "connections.db"

def download_db():
    with st.spinner("Downloading database (315 MB) – this may take a few minutes..."):
        try:
            r = requests.get(DB_URL, stream=True)
            r.raise_for_status()
            with open(DB_PATH, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            st.success("Database downloaded successfully.")
        except Exception as e:
            st.error(f"Download failed: {e}")
            st.stop()

if not os.path.exists(DB_PATH):
    download_db()

# --- Page config ---
st.set_page_config(page_title="Pulte +", layout="wide")

# --- Dark theme CSS ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #ffffff; }
    .stSelectbox label, .stSelectbox div { color: #ffffff !important; }
    .stDataFrame { background-color: #111111; }
    th { background-color: #222222; color: #ffffff; }
    td { background-color: #111111; color: #dddddd; }
    .stButton button { background-color: #333333; color: #ffffff; border: 1px solid #555555; }
    .stButton button:hover { background-color: #444444; }
    .stSpinner > div { color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.title("🔗 Pulte +")
st.caption("Show overlaps where Pulte subdomains share the ultimate Azure CNAME with external domains")

# --- Database connection ---
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_connection()

# --- Load dropdown options (cached) ---
@st.cache_data
def get_hubs():
    df = pd.read_sql_query("SELECT DISTINCT `Pulte subdomain` FROM hubs ORDER BY `Pulte subdomain`", conn)
    return df['Pulte subdomain'].tolist()

@st.cache_data
def get_fraud_flags():
    df = pd.read_sql_query("SELECT DISTINCT Fraud_Risk_Tags FROM overlaps WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''", conn)
    tags = set()
    for row in df['Fraud_Risk_Tags']:
        for tag in row.split(', '):
            tags.add(tag)
    return sorted(tags)

hubs_list = get_hubs()
fraud_flags = get_fraud_flags()

# --- Dropdowns ---
col1, col2 = st.columns(2)
with col1:
    hub = st.selectbox("Pulte subdomain", options=hubs_list, index=0)
with col2:
    fraud = st.selectbox("Fraud flag", options=['All'] + fraud_flags, index=0)

# --- Search button ---
if st.button("🔍 Search", type="primary"):
    conn_local = get_connection()  # reuse connection
    query = """
        SELECT IP, `Pulte subdomain`, `Overlapping subdomain`, Fraud_Risk_Tags, Ultimate_CNAME_Shared
        FROM overlaps
        WHERE `Pulte subdomain` = ?
    """
    params = [hub]
    if fraud != 'All':
        query += " AND Fraud_Risk_Tags LIKE ?"
        params.append(f'%{fraud}%')
    query += " LIMIT 1000"
    try:
        df_result = pd.read_sql_query(query, conn_local, params=params)
    except Exception as e:
        st.error(f"Query error: {e}")
        st.stop()

    if df_result.empty:
        st.info("No overlaps found for the selected criteria.")
    else:
        st.success(f"Found {len(df_result)} overlaps")
        st.dataframe(df_result, use_container_width=True)

# --- Footer ---
st.caption("Data from Pulte overlap analysis | Built with Streamlit")