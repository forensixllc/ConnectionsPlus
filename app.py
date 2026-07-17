import streamlit as st
import pandas as pd
import sqlite3
import traceback
import os

# ------------------------------------------------------------
# Custom CSS: black background, white text
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background-color: black;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔍 Database Debug (Minimal)")
st.write("---")

# ------------------------------------------------------------
# Database path (edit this or use the text input below)
# ------------------------------------------------------------
db_path = st.text_input("Database file path", value="overlaps.db")
st.write(f"Using: `{db_path}`")

if not os.path.exists(db_path):
    st.error(f"❌ File not found: {db_path}")
    st.stop()
else:
    st.success(f"✅ File exists ({os.path.getsize(db_path)} bytes)")

# ------------------------------------------------------------
# Helper: run query with fresh connection
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
# 1. List tables
# ------------------------------------------------------------
st.subheader("📋 Tables in database")
tables_df, err = run_query("SELECT name FROM sqlite_master WHERE type='table';")
if err:
    st.error(f"Could not list tables:\n{err}")
else:
    st.dataframe(tables_df)
    if 'overlaps' in tables_df['name'].values:
        st.success("✅ Table 'overlaps' exists.")
    else:
        st.warning("⚠️ Table 'overlaps' not found.")

# ------------------------------------------------------------
# 2. Show schema of 'overlaps' if it exists
# ------------------------------------------------------------
if 'overlaps' in tables_df['name'].values:
    st.subheader("📋 Schema of 'overlaps'")
    schema_df, err = run_query("PRAGMA table_info(overlaps);")
    if err:
        st.error(f"Could not get schema:\n{err}")
    else:
        st.dataframe(schema_df)

# ------------------------------------------------------------
# 3. Run the original query
# ------------------------------------------------------------
st.subheader("🧪 Run Original Query")
if st.button("Execute SELECT DISTINCT Fraud_Risk_Tags FROM overlaps"):
    sql = """
        SELECT DISTINCT Fraud_Risk_Tags 
        FROM overlaps 
        WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''
    """
    with st.spinner("Running..."):
        df, err = run_query(sql)
        if err:
            st.error(f"❌ Query failed:\n\n{err}")
        else:
            st.success(f"✅ Success! Found {len(df)} distinct values.")
            st.dataframe(df)

# ------------------------------------------------------------
# 4. Custom query (optional)
# ------------------------------------------------------------
st.subheader("✏️ Custom SQL")
custom_sql = st.text_area("Enter SQL", "SELECT * FROM overlaps LIMIT 5")
if st.button("Run Custom Query"):
    df, err = run_query(custom_sql)
    if err:
        st.error(f"❌ Error:\n\n{err}")
    else:
        st.dataframe(df)