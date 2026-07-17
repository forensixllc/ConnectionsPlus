import streamlit as st
import pandas as pd
import sqlite3
import traceback
import json
import requests
import tempfile
import os

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

st.title("Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. Download database from Dropbox
# ------------------------------------------------------------
DROPBOX_LINK = "https://www.dropbox.com/scl/fi/hxnz1doh5cz73p9wuafqk/connections.db?rlkey=tq8jmfu23wvh1ldjp2zs933rs&dl=1"

@st.cache_resource(ttl=3600)
def download_db():
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

db_path = download_db()
if db_path is None:
    st.stop()

# ------------------------------------------------------------
# 2. Helper: run query with a fresh connection
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
# 3. Get columns and auto‑detect company column
# ------------------------------------------------------------
schema_df, err = run_query("PRAGMA table_info(overlaps)")
if err or schema_df.empty:
    st.error(f"Table 'overlaps' not found: {err}")
    st.stop()
columns = schema_df['name'].tolist()

# Auto‑detect company column (fallback to manual if needed)
def auto_detect_company_col(columns):
    possible = ['company', 'Company', 'company_name', 'domain', 'Domain', 'source_domain']
    for col in possible:
        if col in columns:
            return col
    # fallback: first text column from sample
    try:
        sample, _ = run_query("SELECT * FROM overlaps LIMIT 1")
        if sample is not None and not sample.empty:
            for col in columns:
                if sample[col].dtype == object:
                    return col
    except:
        pass
    return None

company_col = auto_detect_company_col(columns)
if company_col is None:
    # Manual selection – show only if auto fails
    company_col = st.selectbox("Select the column with company/domain names", columns, key="company_col")

# ------------------------------------------------------------
# 4. Load data for dropdowns
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def load_companies():
    sql = f"SELECT DISTINCT {company_col} FROM overlaps WHERE {company_col} IS NOT NULL AND {company_col} != ''"
    df, _ = run_query(sql)
    return df[company_col].tolist() if df is not None and not df.empty else []

@st.cache_data(ttl=600)
def load_fraud_flags():
    sql = "SELECT DISTINCT Fraud_Risk_Tags FROM overlaps WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''"
    df, _ = run_query(sql)
    return df['Fraud_Risk_Tags'].tolist() if df is not None and not df.empty else []

companies = load_companies()
fraud_flags = load_fraud_flags()

# ------------------------------------------------------------
# 5. UI: Two pulldown menus
# ------------------------------------------------------------
# Menu 1: Company or "Upload JSON"
menu1_options = ["All Pulte Companies"] + companies + ["Upload c99.nl JSON"]
selected_menu1 = st.selectbox("Select Company or Upload JSON", menu1_options, index=0)

# Menu 2: Fraud flags
menu2_options = ["All"] + fraud_flags if fraud_flags else ["All"]
selected_fraud = st.selectbox("Fraud Flag", menu2_options, index=0)

# If "Upload JSON" is chosen, show file uploader
uploaded_domains = []
if selected_menu1 == "Upload c99.nl JSON":
    uploaded_file = st.file_uploader("Upload JSON file with domain list", type=["json"])
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            if isinstance(data, list):
                uploaded_domains = [str(item) for item in data]
            elif isinstance(data, dict):
                for key in ['domains', 'subdomains', 'data']:
                    if key in data and isinstance(data[key], list):
                        uploaded_domains = [str(item) for item in data[key]]
                        break
                if not uploaded_domains:
                    uploaded_domains = [str(v) for v in data.values() if isinstance(v, str)]
            st.success(f"Loaded {len(uploaded_domains)} domains.")
        except Exception as e:
            st.error(f"JSON error: {e}")

# ------------------------------------------------------------
# 6. Submit button – run search
# ------------------------------------------------------------
if st.button("Submit"):
    where_clauses = []
    params = []

    # Company filter (only if not "Upload JSON" and not "All")
    if selected_menu1 != "All Pulte Companies" and selected_menu1 != "Upload c99.nl JSON":
        where_clauses.append(f"{company_col} = ?")
        params.append(selected_menu1)

    # If we have uploaded domains, add IN clause (overrides company selection? It should intersect)
    if uploaded_domains:
        placeholders = ','.join(['?'] * len(uploaded_domains))
        where_clauses.append(f"{company_col} IN ({placeholders})")
        params.extend(uploaded_domains)

    # Fraud flag filter
    if selected_fraud != "All":
        where_clauses.append("Fraud_Risk_Tags = ?")
        params.append(selected_fraud)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    query = f"SELECT * FROM overlaps WHERE {where_sql}"

    st.write("### Search Results")
    with st.spinner("Querying..."):
        df_result, err = run_query(query, params)
        if err:
            st.error(f"Query failed:\n{err}")
        else:
            st.success(f"Found {len(df_result)} rows.")
            st.dataframe(df_result)