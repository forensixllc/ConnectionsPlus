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
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔗 Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. Database download (with spinner)
# ------------------------------------------------------------
LOCAL_DB = '/content/connections.db'
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/sb8hkhj0mcakyavehh7xe/connections.db?rlkey=vn39nyf8v51a0vtj1qorzuf67&st=su0255ne&dl=1"

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
# 3. Load dropdown data (cached)
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def load_pulte_subdomains():
    sql = "SELECT DISTINCT Pulte_subdomain FROM hubs WHERE Pulte_subdomain IS NOT NULL AND Pulte_subdomain != '' ORDER BY Pulte_subdomain"
    df, _ = run_query(sql)
    return df['Pulte_subdomain'].tolist() if df is not None and not df.empty else []

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

pulte_list = load_pulte_subdomains()
fraud_flags = load_fraud_flags()
menu1_options = ["All Pulte Companies"] + pulte_list + ["Upload c99.nl JSON"]

# ------------------------------------------------------------
# 4. UI Controls
# ------------------------------------------------------------
selected_menu1 = st.selectbox("Select hub source", menu1_options, index=0)
selected_fraud = st.selectbox("Fraud flag", ["All"] + fraud_flags, index=0)

uploaded_domains = []
if selected_menu1 == "Upload c99.nl JSON":
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
            st.success(f"Loaded {len(uploaded_domains)} domains.")
        except Exception as e:
            st.error(f"JSON error: {e}")

# ------------------------------------------------------------
# 5. Search button – triggers query and stores state
# ------------------------------------------------------------
if st.button("🔍 Search", type="primary"):
    # Build WHERE clause
    where_clauses = []
    params = []

    if selected_menu1 == "All Pulte Companies":
        where_clauses.append("Pulte_subdomain IS NOT NULL")
    elif selected_menu1 == "Upload c99.nl JSON" and uploaded_domains:
        placeholders = ','.join(['?'] * len(uploaded_domains))
        where_clauses.append(f"(Pulte_subdomain IN ({placeholders}) OR Overlapping_subdomain IN ({placeholders}))")
        params.extend(uploaded_domains + uploaded_domains)
    elif selected_menu1 != "Upload c99.nl JSON":
        where_clauses.append("Pulte_subdomain = ?")
        params.append(selected_menu1)

    if selected_fraud != "All":
        where_clauses.append("Fraud_Risk_Tags LIKE ?")
        params.append(f'%{selected_fraud}%')

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Save the filter state
    st.session_state['where_sql'] = where_sql
    st.session_state['params'] = params
    st.session_state['search_done'] = True
    # Clear drill-down state
    st.session_state['show_details'] = False
    st.session_state['selected_apex'] = None
    st.session_state['show_subdomain_details'] = False
    st.session_state['selected_subdomain'] = None
    st.rerun()

# ------------------------------------------------------------
# 6. Display results (if search has been done)
# ------------------------------------------------------------
if st.session_state.get('search_done', False):
    where_sql = st.session_state['where_sql']
    params = st.session_state['params']

    # --- Level 1: Apex summary ---
    apex_query = f"""
        SELECT Overlapping_Apex, COUNT(*) as count
        FROM overlaps
        WHERE {where_sql}
        GROUP BY Overlapping_Apex
        ORDER BY count DESC
    """
    df_apex, err = run_query(apex_query, params)
    if err:
        st.error(f"Error loading summary: {err}")
    else:
        if df_apex.empty:
            st.info("No overlaps found for the selected filters.")
        else:
            st.write(f"### 📊 Overlapping Apex Domains ({len(df_apex)} distinct)")

            # Display as a table-like layout with View buttons
            for _, row in df_apex.iterrows():
                apex = row['Overlapping_Apex']
                count = row['count']
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**{apex}** — {count} overlapping subdomains")
                with col2:
                    if st.button("View", key=f"view_apex_{apex}"):
                        st.session_state['selected_apex'] = apex
                        st.session_state['show_details'] = True
                        st.session_state['show_subdomain_details'] = False
                        st.session_state['selected_subdomain'] = None
                        st.rerun()

            # --- Level 2: Subdomain summary (if an apex is selected) ---
            if st.session_state.get('show_details') and st.session_state.get('selected_apex'):
                apex = st.session_state['selected_apex']
                st.write(f"### 🔍 Subdomains under `{apex}`")
                sub_query = f"""
                    SELECT Overlapping_subdomain, COUNT(*) as cnt
                    FROM overlaps
                    WHERE {where_sql} AND Overlapping_Apex = ?
                    GROUP BY Overlapping_subdomain
                    ORDER BY cnt DESC
                """
                params_sub = params + [apex]
                df_sub, err_sub = run_query(sub_query, params_sub)
                if err_sub:
                    st.error(f"Error loading subdomains: {err_sub}")
                else:
                    if df_sub.empty:
                        st.info("No subdomains found for this apex.")
                    else:
                        for _, row_sub in df_sub.iterrows():
                            sub = row_sub['Overlapping_subdomain']
                            cnt = row_sub['cnt']
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.write(f"**{sub}** — {cnt} overlaps")
                            with col2:
                                if st.button("View", key=f"view_sub_{sub}"):
                                    st.session_state['selected_subdomain'] = sub
                                    st.session_state['show_subdomain_details'] = True
                                    st.rerun()

                    # Back button to apex summary
                    if st.button("← Back to apex summary"):
                        st.session_state['show_details'] = False
                        st.session_state['selected_apex'] = None
                        st.rerun()

                    # --- Level 3: Row details (if a subdomain is selected) ---
                    if st.session_state.get('show_subdomain_details') and st.session_state.get('selected_subdomain'):
                        sub = st.session_state['selected_subdomain']
                        st.write(f"### 📋 Detailed overlaps for `{sub}`")
                        detail_query = f"""
                            SELECT IP, Pulte_subdomain, Overlapping_subdomain, Fraud_Risk_Tags
                            FROM overlaps
                            WHERE {where_sql} AND Overlapping_subdomain = ?
                            LIMIT 1000
                        """
                        params_detail = params + [sub]
                        df_detail, err_detail = run_query(detail_query, params_detail)
                        if err_detail:
                            st.error(f"Error loading details: {err_detail}")
                        else:
                            st.dataframe(df_detail, use_container_width=True)
                            if len(df_detail) == 1000:
                                st.info("Showing first 1000 rows for this subdomain. Refine your filters to see more.")
                        # Back to subdomain list
                        if st.button("← Back to subdomains"):
                            st.session_state['show_subdomain_details'] = False
                            st.session_state['selected_subdomain'] = None
                            st.rerun()