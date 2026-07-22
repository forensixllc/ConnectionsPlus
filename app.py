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
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/79zid61a929pyz11pfif7/connections.db?rlkey=rlhcyfh8mafwq7x2aufaullll&st=tk0ul2pc&dl=1"

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
        
    with st.spinner("📥 Downloading optimized database from Dropbox..."):
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
                    st.error("❌ The downloaded file from Dropbox is not a valid SQLite database (it may be an HTML error/redirect page). Please verify your Dropbox sharing permissions.")
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
    evidence_type = st.selectbox("1. Select Overlap Evidence Type", ["IP overlaps (strong)", "SSL overlaps (cryptographic)"], index=0)

with col2:
    target_group = st.selectbox("2. Select Target Enterprise Group", ["Pulte group companies", "Foley group companies", "ICE Mortgage companies", "Apollo Group"], index=0)

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

search_text = st.text_input("🔎 Optional Keyword Search", "", placeholder="e.g. staging, dev, portal")

# ------------------------------------------------------------
# 3. Search Execution Engine (Dynamic SQL Joins)
# ------------------------------------------------------------
if st.button("🔍 Run Overlap Query", type="primary"):
    join_col = "ip_addresses" if "IP" in evidence_type else "ssl_serial_hex"
    is_json_mode = bool(uploaded_domains or uploaded_ips)
    
    st.session_state['join_col'] = join_col
    st.session_state['target_group'] = target_group
    st.session_state['is_json_mode'] = is_json_mode
    st.session_state['uploaded_domains'] = uploaded_domains
    st.session_state['uploaded_ips'] = uploaded_ips
    st.session_state['search_text'] = search_text
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
# 4. Display Results & Drill-Downs
# ------------------------------------------------------------
if st.session_state.get('search_done', False):
    join_col = st.session_state['join_col']
    target_group = st.session_state['target_group']
    is_json_mode = st.session_state['is_json_mode']
    search_txt = st.session_state['search_text'].strip()

    level = 'detail' if st.session_state.get('selected_apex') else 'apex'
    if level == 'detail' and st.button("⬅ Back to Summary"):
        st.session_state['selected_apex'] = None
        st.rerun()

    # --- SQL Query Construction ---
    if is_json_mode:
        sub_conditions = []
        params = []
        if st.session_state['uploaded_domains']:
            placeholders = ','.join(['?'] * len(st.session_state['uploaded_domains']))
            sub_conditions.append(f"subdomain IN ({placeholders})")
            params.extend(st.session_state['uploaded_domains'])
        if st.session_state['uploaded_ips']:
            placeholders = ','.join(['?'] * len(st.session_state['uploaded_ips']))
            sub_conditions.append(f"ip_addresses IN ({placeholders})")
            params.extend(st.session_state['uploaded_ips'])
        
        base_where = "(" + " OR ".join(sub_conditions) + ")"
        if search_txt:
            base_where += " AND (LOWER(subdomain) LIKE LOWER(?) OR LOWER(apex_domain) LIKE LOWER(?))"
            params.extend([f"%{search_txt}%", f"%{search_txt}%"])

        if level == 'apex':
            sql = f"SELECT apex_domain AS Overlapping_Apex, COUNT(*) as Overlap_Count FROM nodes WHERE {base_where} GROUP BY apex_domain ORDER BY Overlap_Count DESC"
        else:
            sql = f"SELECT ip_addresses AS IP, ssl_serial_hex AS SSL_Serial, 'JSON_Upload_Match' AS Target_Subdomain, subdomain AS Overlapping_subdomain FROM nodes WHERE {base_where} AND apex_domain = ?"
            params.append(st.session_state['selected_apex'])

    else:
        base_where = f"""
            n1.Group_Name = ? 
            AND n1.subdomain != n2.subdomain 
            AND n1.{join_col} IS NOT NULL 
            AND n1.{join_col} NOT IN ('Unknown', '', 'No Certificate / Timeout')
        """
        params = [target_group]
        
        if search_txt:
            base_where += " AND (LOWER(n2.subdomain) LIKE LOWER(?) OR LOWER(n2.apex_domain) LIKE LOWER(?))"
            params.extend([f"%{search_txt}%", f"%{search_txt}%"])

        if level == 'apex':
            sql = f"""
                SELECT n2.apex_domain AS Overlapping_Apex, COUNT(*) as Overlap_Count
                FROM nodes n1 JOIN nodes n2 ON n1.{join_col} = n2.{join_col}
                WHERE {base_where} GROUP BY n2.apex_domain ORDER BY Overlap_Count DESC
            """
        else:
            sql = f"""
                SELECT n1.{join_col} AS Shared_Artifact, n1.subdomain AS Target_Subdomain, n2.subdomain AS Overlapping_subdomain
                FROM nodes n1 JOIN nodes n2 ON n1.{join_col} = n2.{join_col}
                WHERE {base_where} AND n2.apex_domain = ? LIMIT 1000
            """
            params.append(st.session_state['selected_apex'])

    # --- Render Streamlit Dataframe Output ---
    df_res, err = run_query(sql, params)
    
    if err:
        st.error(f"Query execution error: {err}")
    elif df_res is None or df_res.empty:
        st.info("No overlaps discovered matching the selected criteria.")
    else:
        if level == 'apex':
            st.write(f"### 📊 Discovered Apex Overlaps ({len(df_res):,} unique entities)")
            download_button_for(df_res, "apex_summary.csv", "dl_apex")
            render_selectable_dataframe(df_res, 'Overlapping_Apex', 'apex', lambda x: st.session_state.update({'selected_apex': x}), 'selected_apex')
        else:
            st.write(f"### 📋 Detailed Overlap Entries for `{st.session_state['selected_apex']}`")
            download_button_for(df_res, f"details_{st.session_state['selected_apex']}.csv", "dl_detail")
            st.dataframe(df_res, width='stretch')
