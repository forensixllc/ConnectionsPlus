import streamlit as st
import pandas as pd
import sqlite3
import traceback
import os
import json

# ------------------------------------------------------------
# Custom CSS
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: black; color: white; }
    .stSelectbox, .stTextInput, .stButton, .stCheckbox, .stFileUploader { color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. Database – hardcoded to connections.db
# ------------------------------------------------------------
DB_PATH = "connections.db"

if not os.path.exists(DB_PATH):
    st.error(f"❌ Database file '{DB_PATH}' not found. Please upload a valid SQLite database or check the filename.")
    st.stop()

# Validate SQLite
def is_valid_sqlite(filepath):
    try:
        conn = sqlite3.connect(filepath)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False

if not is_valid_sqlite(DB_PATH):
    st.error(f"❌ The file '{DB_PATH}' is not a valid SQLite database. Please replace it.")
    with open(DB_PATH, "rb") as f:
        header = f.read(16)
    st.write(f"File header (first 16 bytes): {header.hex()}")
    st.stop()

st.success("✅ Database connected.")

# ------------------------------------------------------------
# 2. Helper: run query with a fresh connection
# ------------------------------------------------------------
def run_query(sql, params=None):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        df = pd.read_sql_query(sql, conn, params=params)
        return df, None
    except Exception as e:
        return None, traceback.format_exc()
    finally:
        if conn:
            conn.close()

# ------------------------------------------------------------
# 3. Get table schema and columns
# ------------------------------------------------------------
def get_schema():
    df_schema, err = run_query("PRAGMA table_info(overlaps)")
    if err:
        return None, err
    return df_schema, None

schema_df, schema_err = get_schema()
if schema_err:
    st.error(f"Table 'overlaps' not found or inaccessible: {schema_err}")
    st.stop()

# Get column names
columns = schema_df['name'].tolist()
st.write(f"Columns in 'overlaps': {', '.join(columns)}")  # helpful for debugging

# ------------------------------------------------------------
# 4. Identify company column (auto or manual)
# ------------------------------------------------------------
# Try to auto-detect
def auto_detect_company_col(columns):
    possible = ['company', 'Company', 'company_name', 'domain', 'Domain', 'source_domain', 'Source_Domain']
    for col in possible:
        if col in columns:
            return col
    # If no obvious, pick the first text-like column (we'll sample data)
    try:
        sample, err = run_query("SELECT * FROM overlaps LIMIT 1")
        if err or sample.empty:
            return None
        for col in columns:
            if sample[col].dtype == object:
                return col
    except:
        pass
    return None

auto_col = auto_detect_company_col(columns)

# If auto detection failed, let user choose from dropdown
if auto_col is None:
    st.warning("Could not automatically identify the company/domain column. Please select it manually.")
    company_col = st.selectbox("Select the column containing company/domain names", columns, key="company_col")
else:
    company_col = auto_col
    st.info(f"Auto-detected company column: `{company_col}`")

# Also allow manual override via a checkbox? Not necessary; we can show the selected.

# ------------------------------------------------------------
# 5. Load distinct company names (for dropdown)
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def load_companies(company_col):
    sql = f"SELECT DISTINCT {company_col} FROM overlaps WHERE {company_col} IS NOT NULL AND {company_col} != ''"
    df, err = run_query(sql)
    if err or df.empty:
        return []
    return df[company_col].tolist()

companies = load_companies(company_col)

# ------------------------------------------------------------
# 6. Load fraud flags
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def load_fraud_flags():
    sql = """
        SELECT DISTINCT Fraud_Risk_Tags 
        FROM overlaps 
        WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''
    """
    df, err = run_query(sql)
    if err or df.empty:
        return []
    return df['Fraud_Risk_Tags'].tolist()

fraud_flags = load_fraud_flags()

# ------------------------------------------------------------
# 7. UI Controls
# ------------------------------------------------------------
# First dropdown: Company
company_options = ["All Pulte Companies"] + companies if companies else ["All Pulte Companies"]
selected_company = st.selectbox("Select Company", company_options, index=0)

# Second dropdown: Fraud flag
fraud_options = ["All"] + fraud_flags if fraud_flags else ["All"]
selected_fraud = st.selectbox("Fraud Flag", fraud_options, index=0)

# File upload for JSON (c99.nl)
uploaded_file = st.file_uploader("Upload c99.nl JSON (optional)", type=["json"])

uploaded_domains = []
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
                # Fallback: take all values that are strings?
                pass
        st.success(f"Loaded {len(uploaded_domains)} domains from JSON.")
    except Exception as e:
        st.error(f"Error parsing JSON: {e}")

# ------------------------------------------------------------
# 8. Search button and query building
# ------------------------------------------------------------
if st.button("Search"):
    # Build WHERE clause
    where_clauses = []
    params = []
    
    if selected_company != "All Pulte Companies":
        where_clauses.append(f"{company_col} = ?")
        params.append(selected_company)
    
    if selected_fraud != "All":
        where_clauses.append("Fraud_Risk_Tags = ?")
        params.append(selected_fraud)
    
    # If uploaded_domains not empty, add IN clause on company_col
    if uploaded_domains:
        placeholders = ','.join(['?'] * len(uploaded_domains))
        where_clauses.append(f"{company_col} IN ({placeholders})")
        params.extend(uploaded_domains)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    query = f"SELECT * FROM overlaps WHERE {where_sql}"
    
    st.write("### Search Results")
    with st.spinner("Querying database..."):
        df_result, err = run_query(query, params)
        if err:
            st.error(f"Query failed:\n{err}")
        else:
            st.success(f"Found {len(df_result)} matching rows.")
            st.dataframe(df_result)

# ------------------------------------------------------------
# 9. Show schema (always visible for debug)
# ------------------------------------------------------------
with st.expander("📋 Database Schema (for reference)", expanded=True):
    st.dataframe(schema_df)