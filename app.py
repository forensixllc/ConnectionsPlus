# ============================================================
# Pulte + – Streamlit App (Pulte.com hub or JSON upload)
# ============================================================

import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
import json

# --- Database download from Dropbox ---
DB_URL = "https://www.dropbox.com/scl/fi/o5dzs9d5fjljv9ffb2esb/connections.db?rlkey=mn3eykkderzrrcebexilfvzvt&st=5vrtsi6z&dl=1"
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
    .stFileUploader label { color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.title("🔗 Pulte +")
st.caption("Search overlaps across all Pulte subdomains or a specific domain from a JSON file")

# --- Database connection ---
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_connection()

# --- Load Pulte hubs ---
@st.cache_data
def get_pulte_hubs():
    df = pd.read_sql_query("SELECT DISTINCT `Pulte subdomain` FROM hubs ORDER BY `Pulte subdomain`", conn)
    return df['Pulte subdomain'].tolist()

pulte_hubs = get_pulte_hubs()

# --- Load fraud flags ---
@st.cache_data
def get_fraud_flags():
    df = pd.read_sql_query("SELECT DISTINCT Fraud_Risk_Tags FROM overlaps WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''", conn)
    tags = set()
    for row in df['Fraud_Risk_Tags']:
        for tag in row.split(', '):
            tags.add(tag)
    return sorted(tags)

fraud_flags = get_fraud_flags()

# --- Layout ---
col1, col2 = st.columns(2)

with col1:
    hub_source = st.selectbox("Hub source", ["Pulte.com", "Upload JSON file"], index=0)
    hub = None

    if hub_source == "Pulte.com":
        hub_choice = st.selectbox("Select Pulte subdomain", options=["All"] + pulte_hubs, index=0)
        if hub_choice == "All":
            hub = "ALL"
        else:
            hub = hub_choice
    else:
        st.info("Upload a c99.nl JSON file (list of subdomains).")
        uploaded_file = st.file_uploader("Upload JSON", type=['json'])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                # Extract subdomains
                subdomains = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'subdomain' in item:
                            subdomains.append(item['subdomain'])
                        elif isinstance(item, str):
                            subdomains.append(item)
                elif isinstance(data, dict):
                    for key in ['subdomains', 'data', 'results']:
                        if key in data and isinstance(data[key], list):
                            for item in data[key]:
                                if isinstance(item, dict) and 'subdomain' in item:
                                    subdomains.append(item['subdomain'])
                                elif isinstance(item, str):
                                    subdomains.append(item)
                            break
                    else:
                        if 'subdomain' in data:
                            subdomains.append(data['subdomain'])
                if subdomains:
                    unique_subs = sorted(set(subdomains))
                    hub = st.selectbox("Choose subdomain from JSON", options=unique_subs, index=0)
                else:
                    st.warning("No subdomains found in the JSON file.")
            except Exception as e:
                st.error(f"Error parsing JSON: {e}")

with col2:
    fraud = st.selectbox("Fraud flag", options=['All'] + fraud_flags, index=0)
    show_cname_only = st.checkbox("Only show shared ultimate CNAME", value=False)

# --- Search ---
if st.button("🔍 Search", type="primary"):
    if hub_source == "Upload JSON file" and hub is None:
        st.warning("Please upload a valid JSON and select a subdomain.")
    else:
        conn_local = get_connection()
        # Build query
        if hub == "ALL":
            # All Pulte subdomains
            query = """
                SELECT IP, `Pulte subdomain`, `Overlapping subdomain`, Fraud_Risk_Tags, Ultimate_CNAME_Shared
                FROM overlaps
                WHERE `Pulte subdomain` IS NOT NULL
            """
            params = []
        else:
            # Specific subdomain (either as Pulte or overlap)
            query = """
                SELECT IP, `Pulte subdomain`, `Overlapping subdomain`, Fraud_Risk_Tags, Ultimate_CNAME_Shared
                FROM overlaps
                WHERE `Pulte subdomain` = ? OR `Overlapping subdomain` = ?
            """
            params = [hub, hub]

        if fraud != 'All':
            if hub == "ALL":
                query += " AND Fraud_Risk_Tags LIKE ?"
                params.append(f'%{fraud}%')
            else:
                query += " AND Fraud_Risk_Tags LIKE ?"
                params.append(f'%{fraud}%')

        if show_cname_only:
            if hub == "ALL":
                query += " AND Ultimate_CNAME_Shared = 1"
            else:
                query += " AND Ultimate_CNAME_Shared = 1"

        query += " LIMIT 1000"

        try:
            df_result = pd.read_sql_query(query, conn_local, params=params)
        except Exception as e:
            st.error(f"Query error: {e}")
            st.stop()

        if df_result.empty:
            st.info("No overlaps found.")
        else:
            st.success(f"Found {len(df_result)} overlaps")
            # Rename for display
            df_result.rename(columns={'Ultimate_CNAME_Shared': 'Shared CNAME'}, inplace=True)
            st.dataframe(df_result, use_container_width=True)

st.caption("Data from Pulte overlap analysis | Built with Streamlit")