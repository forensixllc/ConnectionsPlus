import streamlit as st
import pandas as pd
import sqlite3
import json
import requests
import tempfile
import os
import traceback

# ------------------------------------------------------------
# Custom CSS – Dark Forensic Theme
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #0b0e14; color: #e6edf3; }
    .stSelectbox, .stButton, .stFileUploader { color: white; }
    .dataframe { color: #e6edf3 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔗 Enterprise Infrastructure Overlap Portal")
st.caption("Forensic correlation tool for IP routing, cryptographic SSL certificates, and C99 JSON reconnaissance.")

# ------------------------------------------------------------
# 1. Database Connection Setup with SQLite Validation
# ------------------------------------------------------------
LOCAL_DB = 'connections.db'
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/w9m2pzokl9mmlbgb1op6v/connections.db?rlkey=ot4fkl7ha577fchvfhfebi3zc&st=ilqem04y&dl=1"

def is_valid_sqlite(filepath):
    """Check if file starts with the SQLite binary header bytes."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(100)
            return header.startswith(b'SQLite format 3')
    except Exception:
        return False

@st.cache_resource(ttl=3600)
def get_db_path():
    if os.path.exists(LOCAL_DB) and is_valid_sqlite(LOCAL_DB):
        return LOCAL_DB
        
    with st.spinner("📥 Downloading database from Dropbox..."):
        try:
            response = requests.get(DROPBOX_LINK, stream=True)
            if response.status_code == 200:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_file.close()
                
                if is_valid_sqlite(temp_file.name):
                    return temp_file.name
                else:
                    st.error("❌ The downloaded file from Dropbox is not a valid SQLite database. Please verify your Dropbox sharing permissions.")
                    return None
            else:
                st.error(f"Failed to download database (HTTP {response.status_code})")
                return None
        except Exception as e:
            st.error(f"Download error: {e}")
            return None

db_path = get_db_path()
if db_path is None:
    st.stop()

def run_query(sql, params=None):
    conn = None
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        df = pd.read_sql_query(sql, conn, params=params or [])
        return df, None
    except Exception as e:
        return None, traceback.format_exc()
    finally:
        if conn:
            conn.close()

@st.cache_data
def to_csv_bytes(df):
    return df.to_csv(index=False).encode('utf-8')

def download_button_for(df, filename, key):
    st.download_button(label=f"⬇️ Export {filename}", data=to_csv_bytes(df), file_name=filename, mime="text/csv", key=key)

# ------------------------------------------------------------
# 2. Main UI Controls
# ------------------------------------------------------------
st.subheader("🎯 Primary Inquiry Controls")
col1, col2 = st.columns(2)

with col1:
    evidence_type = st.selectbox(
        "1. Select Overlap Evidence Type",
        ["IP overlaps (strong)", "SSL overlaps (cryptographic)"],
        index=0
    )

with col2:
    target_group = st.selectbox(
        "2. Select Target Enterprise Group",
        [
            "Pulte group companies",
            "Foley group companies",
            "ICE Mortgage companies",
            "Apollo Group"
        ],
        index=0
    )

uploaded_domains = []
uploaded_ips = []
with st.expander("📤 3. Upload JSON file from subdomainfinder.c99.nl (Overrides Group Selection)"):
    uploaded_file = st.file_uploader("Upload JSON export", type=["json"])
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                for item in data:
                    sub = str(item.get('subdomain', '')).strip()
                    ip = str(item.get('ip', '')).strip()
                    if sub: uploaded_domains.append(sub)
                    if ip: uploaded_ips.append(ip)
            elif isinstance(data, list):
                uploaded_domains = [str(item) for item in data]
            uploaded_ips = sorted(set(uploaded_ips))
            st.success(f"Loaded {len(uploaded_domains)} subdomains across {len(uploaded_ips)} unique IPs.")
        except Exception as e:
            st.error(f"JSON parsing error: {e}")

# ------------------------------------------------------------
# 3. Search Execution Engine
# ------------------------------------------------------------
if st.button("🔍 Run Overlap Query", type="primary"):
    is_json_mode = bool(uploaded_domains or uploaded_ips)
    
    st.session_state['evidence_type'] = evidence_type
    st.session_state['target_group'] = target_group
    st.session_state['is_json_mode'] = is_json_mode
    st.session_state['uploaded_domains'] = uploaded_domains
    st.session_state['uploaded_ips'] = uploaded_ips
    st.session_state['search_done'] = True
    st.session_state['selected_apex'] = None
    st.rerun()

def render_selectable_dataframe(df, name_col, key_prefix, on_select_callback, state_key):
    widget_key = f"{key_prefix}_select_df"
    event = st.dataframe(df, width='stretch', hide_index=True, on_select="rerun", selection_mode="single-row", key=widget_key)
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        name = df.iloc[selected_rows[0]][name_col]
        if st.session_state.get(state_key) != name:
            on_select_callback(name)
            st.rerun()

# ------------------------------------------------------------
# 4. Display Results & Drill-Downs (Threshold > 500 for Folders)
# ------------------------------------------------------------
if st.session_state.get('search_done', False):
    evidence_type = st.session_state['evidence_type']
    target_group = st.session_state['target_group']
    is_json_mode = st.session_state['is_json_mode']

    level = 'detail' if st.session_state.get('selected_apex') else 'apex'
    if level == 'detail' and st.button("⬅ Back to Summary"):
        st.session_state['selected_apex'] = None
        st.rerun()

    where_clauses = ["Overlap_Type = ?"]
    params = [evidence_type]

    if is_json_mode:
        sub_conditions = []
        if st.session_state['uploaded_domains']:
            placeholders = ','.join(['?'] * len(st.session_state['uploaded_domains']))
            sub_conditions.append(f"Pulte_subdomain IN ({placeholders})")
            params.extend(st.session_state['uploaded_domains'])
            sub_conditions.append(f"Overlapping_subdomain IN ({placeholders})")
            params.extend(st.session_state['uploaded_domains'])
        if st.session_state['uploaded_ips']:
            placeholders = ','.join(['?'] * len(st.session_state['uploaded_ips']))
            sub_conditions.append(f"IP IN ({placeholders})")
            params.extend(st.session_state['uploaded_ips'])
        if sub_conditions:
            where_clauses.append("(" + " OR ".join(sub_conditions) + ")")
    else:
        where_clauses.append("Group_Name = ?")
        params.append(target_group)

    where_sql = " AND ".join(where_clauses)

    if level == 'apex':
        # Only show domains with > 500 results in the folder summary view
        sql = f"""
            SELECT Overlapping_Apex, COUNT(*) as Overlap_Count
            FROM overlaps
            WHERE {where_sql}
            GROUP BY Overlapping_Apex
            HAVING Overlap_Count > 500
            ORDER BY Overlap_Count DESC
        """
    else:
        # Format columns dynamically based on whether IP or SSL search was chosen
        if "IP" in evidence_type:
            sql = f"""
                SELECT IP, SSL_Serial, Pulte_subdomain AS Target_Subdomain, Overlapping_subdomain
                FROM overlaps
                WHERE {where_sql} AND Overlapping_Apex = ?
                LIMIT 1000
            """
        else:
            sql = f"""
                SELECT SSL_Serial, IP, Pulte_subdomain AS Target_Subdomain, Overlapping_subdomain
                FROM overlaps
                WHERE {where_sql} AND Overlapping_Apex = ?
                LIMIT 1000
            """
        params.append(st.session_state['selected_apex'])

    df_res, err = run_query(sql, params)
    
    if err:
        st.error(f"Query execution error: {err}")
    elif df_res is None or df_res.empty:
        st.info("No overlaps discovered exceeding 500 results matching the selected criteria.")
    else:
        if level == 'apex':
            st.write(f"### 📊 High-Volume Apex Overlaps (> 500 results) ({len(df_res):,} entities)")
            st.caption("Click any row below to view detailed subdomain correlations.")
            download_button_for(df_res, "apex_summary_over_500.csv", "dl_apex")
            render_selectable_dataframe(df_res, 'Overlapping_Apex', 'apex', lambda x: st.session_state.update({'selected_apex': x}), 'selected_apex')
        else:
            st.write(f"### 📋 Detailed Overlap Entries for `{st.session_state['selected_apex']}`")
            download_button_for(df_res, f"details_{st.session_state['selected_apex']}.csv", "dl_detail")
            st.dataframe(df_res, width='stretch')
