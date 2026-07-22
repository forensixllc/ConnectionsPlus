import streamlit as st
import pandas as pd
import sqlite3
import json
import requests
import tempfile
import os
import traceback

st.markdown(
    """
    <style>
    .stApp { background-color: #0b0e14; color: #e6edf3; }
    .stSelectbox, .stButton, .stFileUploader, .stNumberInput { color: white; }
    .dataframe { color: #e6edf3 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔗 Enterprise Infrastructure Overlap Portal")
st.caption("Forensic correlation tool for IP routing, cryptographic SSL certificates, and C99 JSON reconnaissance.")

# ------------------------------------------------------------
# 1. Database Connection Setup
# ------------------------------------------------------------
LOCAL_DB = 'connections.db'
# REPLACE THIS WITH YOUR NEW DROPBOX LINK FOR THE 4MB FILE
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/4by6l2v7vgfkp1f91qroj/connections.db?rlkey=562uf1p3inkw1wvjmq2y3uel9&st=9idzx987&dl=1" 

def is_valid_sqlite(filepath):
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
                return None
            return None
        except Exception:
            return None

db_path = get_db_path()
if db_path is None:
    st.error("❌ Failed to load valid database. Check Dropbox link.")
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

def to_csv_bytes(df):
    return df.to_csv(index=False).encode('utf-8')

# ------------------------------------------------------------
# 2. Main UI Controls
# ------------------------------------------------------------
st.subheader("🎯 Primary Inquiry Controls")
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    evidence_type = st.selectbox("1. Select Overlap Evidence Type", ["IP overlaps (strong)", "SSL overlaps (cryptographic)"])
with col2:
    target_group = st.selectbox("2. Select Target Enterprise Group", ["Pulte group companies", "Foley group companies", "ICE Mortgage companies", "Apollo Group"])
with col3:
    min_overlaps = st.number_input("3. Min Overlap Threshold", min_value=1, value=1, help="Filter out small noise.")

uploaded_domains, uploaded_ips = [], []
with st.expander("📤 4. Upload JSON file from subdomainfinder.c99.nl (Overrides Group Selection)"):
    uploaded_file = st.file_uploader("Upload JSON export", type=["json"])
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                for item in data:
                    if item.get('subdomain'): uploaded_domains.append(str(item['subdomain']).strip())
                    if item.get('ip'): uploaded_ips.append(str(item['ip']).strip())
            st.success(f"Loaded {len(uploaded_domains)} subdomains and {len(set(uploaded_ips))} IPs.")
        except Exception as e:
            st.error(f"JSON error: {e}")

if st.button("🔍 Run Overlap Query", type="primary"):
    st.session_state.update({
        'join_col': "ip_addresses" if "IP" in evidence_type else "ssl_serial_hex",
        'target_group': target_group,
        'min_overlaps': min_overlaps,
        'is_json_mode': bool(uploaded_domains or uploaded_ips),
        'uploaded_domains': uploaded_domains,
        'uploaded_ips': uploaded_ips,
        'search_done': True,
        'selected_apex': None
    })
    st.rerun()

def render_selectable_dataframe(df, name_col, state_key):
    event = st.dataframe(df, width='stretch', hide_index=True, on_select="rerun", selection_mode="single-row")
    if event and event.selection and event.selection.rows:
        name = df.iloc[event.selection.rows[0]][name_col]
        if st.session_state.get(state_key) != name:
            st.session_state[state_key] = name
            st.rerun()

# ------------------------------------------------------------
# 3. Dynamic Engine (Eliminates Intra-Company Overlaps)
# ------------------------------------------------------------
if st.session_state.get('search_done', False):
    join_col = st.session_state['join_col']
    target_grp = st.session_state['target_group']
    level = 'detail' if st.session_state.get('selected_apex') else 'apex'
    
    if level == 'detail' and st.button("⬅ Back to Summary"):
        st.session_state['selected_apex'] = None
        st.rerun()

    if st.session_state['is_json_mode']:
        sub_conditions, params = [], []
        if st.session_state['uploaded_domains']:
            placeholders = ','.join(['?']*len(st.session_state['uploaded_domains']))
            sub_conditions.append(f"subdomain IN ({placeholders})")
            params.extend(st.session_state['uploaded_domains'])
        if st.session_state['uploaded_ips']:
            placeholders = ','.join(['?']*len(st.session_state['uploaded_ips']))
            sub_conditions.append(f"ip_addresses IN ({placeholders})")
            params.extend(st.session_state['uploaded_ips'])
            
        base_where = "(" + " OR ".join(sub_conditions) + ")"
        
        if level == 'apex':
            sql = f"SELECT apex_domain AS Overlapping_Apex, COUNT(*) as Overlap_Count FROM nodes WHERE {base_where} GROUP BY apex_domain HAVING Overlap_Count >= ? ORDER BY Overlap_Count DESC"
            params.append(st.session_state['min_overlaps'])
        else:
            sql = f"SELECT ip_addresses AS IP, ssl_serial_hex AS SSL_Serial, 'JSON Upload' AS Target_Subdomain, subdomain AS Overlapping_subdomain FROM nodes WHERE {base_where} AND apex_domain = ? LIMIT 1000"
            params.append(st.session_state['selected_apex'])

    else:
        # Strict rule: Target group matches anything EXCEPT its own group
        base_where = f"""
            n1.Group_Name = ? 
            AND n2.Group_Name != ? 
            AND n1.{join_col} IS NOT NULL 
            AND n1.{join_col} NOT IN ('Unknown', 'No Certificate / Timeout', '', 'nan', 'none')
        """
        params = [target_grp, target_grp]

        if level == 'apex':
            sql = f"""
                SELECT n2.apex_domain AS Overlapping_Apex, COUNT(*) as Overlap_Count
                FROM nodes n1 JOIN nodes n2 ON n1.{join_col} = n2.{join_col}
                WHERE {base_where}
                GROUP BY n2.apex_domain HAVING Overlap_Count >= ? ORDER BY Overlap_Count DESC
            """
            params.append(st.session_state['min_overlaps'])
        else:
            # Proper column order based on search type
            col_1 = "n1.ip_addresses AS IP, n1.ssl_serial_hex AS SSL_Serial" if join_col == "ip_addresses" else "n1.ssl_serial_hex AS SSL_Serial, n1.ip_addresses AS IP"
            sql = f"""
                SELECT {col_1}, n1.subdomain AS Target_Subdomain, n2.subdomain AS Overlapping_subdomain
                FROM nodes n1 JOIN nodes n2 ON n1.{join_col} = n2.{join_col}
                WHERE {base_where} AND n2.apex_domain = ? LIMIT 1000
            """
            params.append(st.session_state['selected_apex'])

    df_res, err = run_query(sql, params)
    
    if err:
        st.error(f"Error: {err}")
    elif df_res is None or df_res.empty:
        st.info("No external overlaps discovered matching the criteria.")
    else:
        if level == 'apex':
            st.write(f"### 📊 External Apex Overlaps ({len(df_res):,} unique entities)")
            st.download_button("⬇️ Export Summary", to_csv_bytes(df_res), "apex_summary.csv", "text/csv")
            render_selectable_dataframe(df_res, 'Overlapping_Apex', 'selected_apex')
        else:
            st.write(f"### 📋 Detailed Overlaps for `{st.session_state['selected_apex']}`")
            st.download_button("⬇️ Export Details", to_csv_bytes(df_res), f"details_{st.session_state['selected_apex']}.csv", "text/csv")
            st.dataframe(df_res, width='stretch')
