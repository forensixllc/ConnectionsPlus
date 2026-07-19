import streamlit as st
import pandas as pd
import sqlite3
import json
import requests
import tempfile
import os
import traceback

# ------------------------------------------------------------
# Custom CSS – black background, white text
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: black; color: white; }
    .stSelectbox, .stButton, .stFileUploader { color: white; }
    .dataframe { color: white !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔗 Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. Database download
# ------------------------------------------------------------
LOCAL_DB = '/content/connections.db'
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/22x8qcw1iccd8eqa9wfjl/connections.db?rlkey=pxvj6ls63h066apfwlah3z1x5&st=iw8w9pyo&dl=1"

@st.cache_resource(ttl=3600)
def get_db_path():
    if os.path.exists(LOCAL_DB):
        return LOCAL_DB
    with st.spinner("📥 Downloading database from Dropbox..."):
        try:
            response = requests.get(DROPBOX_LINK, stream=True)
            if response.status_code == 200:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name
            else:
                st.error(f"Failed to download database (HTTP {response.status_code})")
                return None
        except Exception as e:
            st.error(f"Download error: {e}")
            return None

db_path = get_db_path()
if db_path is None:
    st.stop()

# ------------------------------------------------------------
# 2. Helper: run query
# ------------------------------------------------------------
def run_query(sql, params=None):
    conn = None
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        df = pd.read_sql_query(sql, conn, params=params)
        return df, None
    except Exception as e:
        return None, traceback.format_exc()
    finally:
        if conn:
            conn.close()

# ------------------------------------------------------------
# 2b. Helper: CSV download button
# ------------------------------------------------------------
@st.cache_data
def to_csv_bytes(df):
    return df.to_csv(index=False).encode('utf-8')

def download_button_for(df, filename, key):
    st.download_button(
        label=f"⬇️ Download {filename}",
        data=to_csv_bytes(df),
        file_name=filename,
        mime="text/csv",
        key=key,
    )

# ------------------------------------------------------------
# 3. Load dropdown data (cached)
# ------------------------------------------------------------
PULTE_COMPANIES = [
    "AmericanWestHomes.com",
    "Centex.com",
    "Divosta.com",
    "Icgbuilds.com",
    "Pulte.com",
    "Pultemortgage.com",
    "Pultegroup.com",
]

@st.cache_data(ttl=600)
def load_fraud_flags():
    sql = "SELECT DISTINCT Fraud_Risk_Tags FROM overlaps WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''"
    df, _ = run_query(sql)
    tags = set()
    if df is not None and not df.empty:
        for row in df['Fraud_Risk_Tags']:
            if row:
                for tag in row.split(', '):
                    tags.add(tag.strip())
    return sorted(tags)

@st.cache_data(ttl=600)
def load_overlapping_apex_list():
    sql = "SELECT DISTINCT Overlapping_Apex FROM overlaps WHERE Overlapping_Apex IS NOT NULL AND Overlapping_Apex != '' ORDER BY Overlapping_Apex"
    df, _ = run_query(sql)
    return df['Overlapping_Apex'].tolist() if df is not None and not df.empty else []

@st.cache_data(ttl=600)
def load_ip_list():
    sql = "SELECT DISTINCT IP FROM overlaps WHERE IP IS NOT NULL AND IP != '' ORDER BY IP"
    df, _ = run_query(sql)
    return df['IP'].tolist() if df is not None and not df.empty else []

fraud_flags = load_fraud_flags()
apex_domain_list = load_overlapping_apex_list()
ip_list = load_ip_list()

# ------------------------------------------------------------
# 4. UI Controls
# ------------------------------------------------------------
selected_company = st.selectbox("Pulte company", ["All Pulte Companies"] + PULTE_COMPANIES, index=0)
selected_fraud = st.selectbox("Fraud flag", ["All fraud tags"] + fraud_flags, index=0)
selected_domain = st.selectbox("Overlapping domain", ["All domains"] + apex_domain_list, index=0)
selected_ip = st.selectbox("IP address", ["All IPs"] + ip_list, index=0)

uploaded_domains = []
with st.expander("📤 Or upload a subdomainfinder.c99.nl file"):
    uploaded_file = st.file_uploader("Upload JSON file with subdomains", type=["json"])
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            if isinstance(data, list):
                uploaded_domains = [str(item) for item in data]
            elif isinstance(data, dict):
                for key in ['subdomains', 'domains', 'data', 'results']:
                    if key in data and isinstance(data[key], list):
                        uploaded_domains = [str(item) for item in data[key]]
                        break
                if not uploaded_domains:
                    uploaded_domains = [str(v) for v in data.values() if isinstance(v, str)]
            st.success(f"Loaded {len(uploaded_domains)} domains. This overrides the Pulte company dropdown above.")
        except Exception as e:
            st.error(f"JSON error: {e}")

search_text = st.text_input("🔎 Search domains / subdomains", "", placeholder="e.g. staging, .dev., kiosk")

# ------------------------------------------------------------
# 5. Search button – triggers query and stores state
# ------------------------------------------------------------
if st.button("🔍 Search", type="primary"):
    # Build WHERE clause. All active filters combine with AND.
    where_clauses = []
    params = []

    if uploaded_domains:
        # Uploaded c99.nl list takes precedence over the company dropdown
        placeholders = ','.join(['?'] * len(uploaded_domains))
        where_clauses.append(f"(Pulte_subdomain IN ({placeholders}) OR Overlapping_subdomain IN ({placeholders}))")
        params.extend(uploaded_domains + uploaded_domains)
    elif selected_company != "All Pulte Companies":
        # Match the exact apex or anything under it, e.g. Centex.com matches
        # both "centex.com" and "kioskk.dev.centex.com"
        where_clauses.append("(LOWER(Pulte_subdomain) = LOWER(?) OR LOWER(Pulte_subdomain) LIKE LOWER(?))")
        params.append(selected_company)
        params.append(f"%.{selected_company}")
    else:
        where_clauses.append("Pulte_subdomain IS NOT NULL")

    if selected_fraud != "All fraud tags":
        where_clauses.append("Fraud_Risk_Tags LIKE ?")
        params.append(f'%{selected_fraud}%')

    if selected_domain != "All domains":
        where_clauses.append("Overlapping_Apex = ?")
        params.append(selected_domain)

    if selected_ip != "All IPs":
        where_clauses.append("IP = ?")
        params.append(selected_ip)

    if search_text.strip():
        term = f"%{search_text.strip()}%"
        where_clauses.append(
            "(LOWER(Pulte_subdomain) LIKE LOWER(?) OR LOWER(Overlapping_subdomain) LIKE LOWER(?) OR LOWER(Overlapping_Apex) LIKE LOWER(?))"
        )
        params.extend([term, term, term])

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    st.session_state['where_sql'] = where_sql
    st.session_state['params'] = params
    st.session_state['search_done'] = True
    # Clear drill-down state
    st.session_state['selected_apex'] = None
    st.session_state.pop('apex_select_df', None)
    st.rerun()

# ------------------------------------------------------------
# 6. Display results (if search has been done)
# ------------------------------------------------------------
def render_selectable_dataframe(df, name_col, key_prefix, on_select_callback, state_key):
    """Render df as a native st.dataframe (search/download/expand toolbar built in).
    Clicking a row triggers on_select_callback(name) and reruns.
    Requires streamlit >= 1.35 for on_select support.

    st.dataframe selection is sticky across reruns, so we only fire the
    callback when the selection is actually new (compared against
    st.session_state[state_key]) to avoid an infinite rerun loop."""
    widget_key = f"{key_prefix}_select_df"
    event = st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=widget_key,
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        name = df.iloc[selected_rows[0]][name_col]
        if st.session_state.get(state_key) != name:
            on_select_callback(name)
            st.rerun()

if st.session_state.get('search_done', False):
    where_sql = st.session_state['where_sql']
    params = st.session_state['params']

    # Determine which single level to show
    level = 'detail' if st.session_state.get('selected_apex') else 'apex'

    # --- Breadcrumb ---
    if level == 'detail':
        if st.button("⬅ Apex list"):
            st.session_state['selected_apex'] = None
            st.session_state.pop('apex_select_df', None)
            st.rerun()

    breadcrumb = "**All Apex Domains**"
    if level == 'detail':
        breadcrumb += f" › **{st.session_state['selected_apex']}**"
    st.markdown(breadcrumb)

    results_box = st.container()

    # ================= Level 1: Apex summary =================
    if level == 'apex':
        apex_query = f"""
            SELECT Overlapping_Apex, COUNT(*) as count
            FROM overlaps
            WHERE {where_sql}
            GROUP BY Overlapping_Apex
            ORDER BY count DESC
        """
        df_apex, err = run_query(apex_query, params)
        with results_box:
            if err:
                st.error(f"Error loading summary: {err}")
            elif df_apex.empty:
                st.info("No overlaps found for the selected filters.")
            else:
                st.write(f"### 📊 Overlapping Apex Domains ({len(df_apex)} distinct)")
                st.caption("Click a row to view its overlap details")
                download_button_for(df_apex, "apex_summary.csv", key="dl_apex_summary")
                render_selectable_dataframe(
                    df_apex,
                    name_col='Overlapping_Apex',
                    key_prefix="apex",
                    state_key="selected_apex",
                    on_select_callback=lambda apex: (
                        st.session_state.update({'selected_apex': apex})
                    )
                )

    # ================= Level 2: Row detail for the selected apex =================
    elif level == 'detail':
        apex = st.session_state['selected_apex']

        count_query = f"""
            SELECT COUNT(*) as total
            FROM overlaps
            WHERE {where_sql} AND Overlapping_Apex = ?
        """
        params_count = params + [apex]
        df_count, err_count = run_query(count_query, params_count)
        total_rows = int(df_count['total'].iloc[0]) if df_count is not None and not df_count.empty else 0

        detail_query = f"""
            SELECT IP, Pulte_subdomain, Overlapping_subdomain, Fraud_Risk_Tags
            FROM overlaps
            WHERE {where_sql} AND Overlapping_Apex = ?
            LIMIT 1000
        """
        params_detail = params + [apex]
        df_detail, err_detail = run_query(detail_query, params_detail)

        with results_box:
            st.write(f"### 📋 Detailed overlaps for `{apex}` ({total_rows:,} total)")
            if err_detail:
                st.error(f"Error loading details: {err_detail}")
            else:
                safe_apex = apex.replace('/', '_').replace(':', '_')

                if total_rows > 1000:
                    st.info(
                        f"Showing first 1,000 of {total_rows:,} rows for this apex. "
                        f"Download the full CSV below to see everything."
                    )
                    full_query = f"""
                        SELECT IP, Pulte_subdomain, Overlapping_subdomain, Fraud_Risk_Tags
                        FROM overlaps
                        WHERE {where_sql} AND Overlapping_Apex = ?
                    """
                    df_full, err_full = run_query(full_query, params_detail)
                    if err_full:
                        st.error(f"Error preparing full export: {err_full}")
                    else:
                        download_button_for(df_full, f"details_{safe_apex}_full.csv", key="dl_detail_full")
                else:
                    download_button_for(df_detail, f"details_{safe_apex}.csv", key="dl_detail")

                st.dataframe(df_detail, width='stretch')
