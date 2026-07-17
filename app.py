import streamlit as st
import pandas as pd
import sqlite3
import traceback
import os
import json

# ------------------------------------------------------------
# Custom CSS: black background, white text
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

# Validate that it's a real SQLite database
def is_valid_sqlite(filepath):
    try:
        conn = sqlite3.connect(filepath)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False

if not is_valid_sqlite(DB_PATH):
    st.error(f"❌ The file '{DB_PATH}' is not a valid SQLite database. Please replace it with a correct .db file.")
    with open(DB_PATH, "rb") as f:
        header = f.read(16)
    st.write(f"File header (first 16 bytes): {header.hex()} – expected SQLite magic: 53 51 4C 69 74 65 ...")
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
# 3. Load company names and fraud flags (cached)
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def load_companies():
    # Assumes a column 'company' or 'domain' – adjust if different.
    # Try common column names: 'Company', 'company_name', 'Domain', etc.
    # We'll try to find a suitable column from the 'overlaps' table.
    # First, get column names.
    sample_sql = "SELECT * FROM overlaps LIMIT 1"
    df_sample, err = run_query(sample_sql)
    if err or df_sample.empty:
        return [], []
    columns = df_sample.columns.tolist()
    # Look for a column that might contain company/domain names.
    possible_cols = ['company', 'Company', 'company_name', 'domain', 'Domain', 'source_domain']
    company_col = None
    for col in possible_cols:
        if col in columns:
            company_col = col
            break
    if company_col is None:
        # Fallback: use the first text column.
        for col in columns:
            if df_sample[col].dtype == object:
                company_col = col
                break
    if company_col is None:
        st.warning("Could not identify a company/domain column. Please check database schema.")
        return [], []
    
    # Get distinct company names
    sql = f"SELECT DISTINCT {company_col} FROM overlaps WHERE {company_col} IS NOT NULL AND {company_col} != ''"
    df_comp, err = run_query(sql)
    if err or df_comp.empty:
        return [], []
    companies = df_comp[company_col].tolist()
    return companies, company_col

companies, company_col = load_companies()

if not companies:
    st.warning("No companies found in the database. Please check the table 'overlaps'.")
    # Still allow JSON upload? Possibly, but we'll stop.
    # We'll continue and let the user upload JSON to work with.

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
# 4. UI Controls
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
        # Expect a list of domains/subdomains – could be a list of strings or dict with key 'domains'
        if isinstance(data, list):
            uploaded_domains = [str(item) for item in data]
        elif isinstance(data, dict):
            # Try common keys: 'domains', 'subdomains', 'data'
            for key in ['domains', 'subdomains', 'data']:
                if key in data and isinstance(data[key], list):
                    uploaded_domains = [str(item) for item in data[key]]
                    break
            if not uploaded_domains:
                # Fallback: take all string values from dict?
                pass
        st.success(f"Loaded {len(uploaded_domains)} domains from JSON.")
    except Exception as e:
        st.error(f"Error parsing JSON: {e}")

# ------------------------------------------------------------
# 5. Search button and query building
# ------------------------------------------------------------
if st.button("Search"):
    # Build the base query
    # We need to know the columns. Let's get all columns from overlaps.
    # We'll assume we want all rows that match company and fraud flag.
    # Also, if uploaded_domains is non-empty, we want to intersect: only rows where the domain (company_col) is in uploaded_domains.
    
    # To make it generic, we'll select all columns from overlaps.
    # We'll filter on company_col and fraud flag.
    
    # First, we need to know the company column name (already determined).
    if not company_col:
        st.error("Company column not identified. Cannot proceed.")
        st.stop()
    
    # Build WHERE clause
    where_clauses = []
    params = []
    
    if selected_company != "All Pulte Companies":
        where_clauses.append(f"{company_col} = ?")
        params.append(selected_company)
    
    if selected_fraud != "All":
        where_clauses.append("Fraud_Risk_Tags = ?")
        params.append(selected_fraud)
    
    # If uploaded_domains is not empty, add an IN clause on company_col
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
# 6. Optional: Show schema for debugging (can be hidden)
# ------------------------------------------------------------
with st.expander("ℹ️ Database Schema (debug)"):
    try:
        df_schema, _ = run_query("PRAGMA table_info(overlaps)")
        st.dataframe(df_schema)
    except Exception as e:
        st.error(f"Could not get schema: {e}")
        