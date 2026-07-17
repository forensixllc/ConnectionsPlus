import streamlit as st
import pandas as pd
import sqlite3
import traceback
import os
import json
import io

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
# 1. Database setup: try connections.db, else upload
# ------------------------------------------------------------
DB_PATH = "connections.db"
VALID_DB = None   # path to the database file to use

def is_valid_sqlite(filepath):
    try:
        conn = sqlite3.connect(filepath)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False

# Check if default exists and is valid
if os.path.exists(DB_PATH) and is_valid_sqlite(DB_PATH):
    VALID_DB = DB_PATH
    st.success("✅ Using `connections.db`")
else:
    if os.path.exists(DB_PATH):
        st.warning(f"`{DB_PATH}` exists but is not a valid SQLite database. Please upload a data file (SQLite, CSV, or JSON).")
    else:
        st.info("No `connections.db` found. Upload a data file (SQLite, CSV, or JSON).")
    
    uploaded_data = st.file_uploader("Upload database file (SQLite .db, CSV, or JSON)", type=["db", "csv", "json"])
    
    if uploaded_data is not None:
        # Determine file type by extension or content
        file_ext = uploaded_data.name.split('.')[-1].lower()
        
        if file_ext == 'db':
            # Save to temporary file and validate
            with open("uploaded.db", "wb") as f:
                f.write(uploaded_data.getbuffer())
            if is_valid_sqlite("uploaded.db"):
                VALID_DB = "uploaded.db"
                st.success("✅ SQLite database uploaded and validated.")
            else:
                st.error("❌ Uploaded .db file is not a valid SQLite database.")
        
        elif file_ext == 'csv':
            # Read CSV into pandas, create an in‑memory SQLite DB
            try:
                df = pd.read_csv(uploaded_data)
                # Create a temporary file for SQLite
                temp_db = "temp_uploaded.db"
                conn = sqlite3.connect(temp_db)
                df.to_sql("overlaps", conn, if_exists="replace", index=False)
                conn.close()
                if is_valid_sqlite(temp_db):
                    VALID_DB = temp_db
                    st.success(f"✅ CSV loaded: {len(df)} rows, {len(df.columns)} columns.")
                else:
                    st.error("Failed to create SQLite from CSV.")
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
        
        elif file_ext == 'json':
            # Try to interpret as a list of rows (list of dicts) or a table
            try:
                data = json.load(uploaded_data)
                if isinstance(data, list) and len(data) > 0:
                    # Assume it's a list of dictionaries (rows)
                    df = pd.DataFrame(data)
                    temp_db = "temp_uploaded.json.db"
                    conn = sqlite3.connect(temp_db)
                    df.to_sql("overlaps", conn, if_exists="replace", index=False)
                    conn.close()
                    if is_valid_sqlite(temp_db):
                        VALID_DB = temp_db
                        st.success(f"✅ JSON loaded: {len(df)} rows, {len(df.columns)} columns.")
                    else:
                        st.error("Failed to create SQLite from JSON.")
                else:
                    st.error("JSON must be a list of objects (rows).")
            except Exception as e:
                st.error(f"Error parsing JSON: {e}")
        else:
            st.error("Unsupported file type. Please upload .db, .csv, or .json.")

if VALID_DB is None:
    st.stop()

# ------------------------------------------------------------
# 2. Helper: run query with fresh connection
# ------------------------------------------------------------
def run_query(sql, params=None):
    conn = None
    try:
        conn = sqlite3.connect(VALID_DB, check_same_thread=False)
        df = pd.read_sql_query(sql, conn, params=params)
        return df, None
    except Exception as e:
        return None, traceback.format_exc()
    finally:
        if conn:
            conn.close()

# ------------------------------------------------------------
# 3. Get schema and columns of 'overlaps'
# ------------------------------------------------------------
def get_schema():
    df_schema, err = run_query("PRAGMA table_info(overlaps)")
    if err:
        return None, err
    return df_schema, None

schema_df, schema_err = get_schema()
if schema_err:
    st.error(f"Table 'overlaps' not found or inaccessible:\n{schema_err}")
    st.stop()

columns = schema_df['name'].tolist()
st.write(f"📋 Columns in 'overlaps': {', '.join(columns)}")

# ------------------------------------------------------------
# 4. Identify company column (auto or manual)
# ------------------------------------------------------------
def auto_detect_company_col(columns):
    possible = ['company', 'Company', 'company_name', 'domain', 'Domain', 'source_domain', 'Source_Domain']
    for col in possible:
        if col in columns:
            return col
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

if auto_col is None:
    st.warning("Could not auto‑detect company column. Please select it manually.")
    company_col = st.selectbox("Select column containing company/domain names", columns, key="company_col")
else:
    company_col = auto_col
    st.info(f"Auto‑detected company column: `{company_col}`")

# ------------------------------------------------------------
# 5. Load distinct company names
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
company_options = ["All Pulte Companies"] + companies if companies else ["All Pulte Companies"]
selected_company = st.selectbox("Select Company", company_options, index=0)

fraud_options = ["All"] + fraud_flags if fraud_flags else ["All"]
selected_fraud = st.selectbox("Fraud Flag", fraud_options, index=0)

uploaded_json = st.file_uploader("Upload c99.nl JSON (optional) – list of domains", type=["json"])

uploaded_domains = []
if uploaded_json is not None:
    try:
        data = json.load(uploaded_json)
        if isinstance(data, list):
            uploaded_domains = [str(item) for item in data]
        elif isinstance(data, dict):
            for key in ['domains', 'subdomains', 'data']:
                if key in data and isinstance(data[key], list):
                    uploaded_domains = [str(item) for item in data[key]]
                    break
            if not uploaded_domains:
                # fallback: extract all string values from dict?
                pass
        st.success(f"Loaded {len(uploaded_domains)} domains from JSON.")
    except Exception as e:
        st.error(f"Error parsing JSON: {e}")

# ------------------------------------------------------------
# 8. Search
# ------------------------------------------------------------
if st.button("Search"):
    where_clauses = []
    params = []
    
    if selected_company != "All Pulte Companies":
        where_clauses.append(f"{company_col} = ?")
        params.append(selected_company)
    
    if selected_fraud != "All":
        where_clauses.append("Fraud_Risk_Tags = ?")
        params.append(selected_fraud)
    
    if uploaded_domains:
        placeholders = ','.join(['?'] * len(uploaded_domains))
        where_clauses.append(f"{company_col} IN ({placeholders})")
        params.extend(uploaded_domains)
    
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

# ------------------------------------------------------------
# 9. Schema reference
# ------------------------------------------------------------
with st.expander("📋 Database Schema"):
    st.dataframe(schema_df)