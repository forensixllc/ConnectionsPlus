import streamlit as st
import pandas as pd
import sqlite3
import traceback

# ------------------------------------------------------------
# 1. Database connection (cached as a resource)
# ------------------------------------------------------------
@st.cache_resource
def get_connection():
    """Return a SQLite connection (adjust for your DB type)."""
    # Change this to your actual database file or connection string
    # For PostgreSQL/MySQL, use sqlalchemy.create_engine()
    return sqlite3.connect("your_database.db")   # <-- UPDATE PATH

# ------------------------------------------------------------
# 2. Helper: run a query and catch any error
# ------------------------------------------------------------
def safe_query(conn, sql, params=None):
    """Execute a query and return (df, error) where error is None on success."""
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df, None
    except Exception as e:
        # Capture full traceback for display
        tb = traceback.format_exc()
        return None, f"{e}\n\nFull traceback:\n{tb}"

# ------------------------------------------------------------
# 3. Streamlit UI
# ------------------------------------------------------------
st.set_page_config(page_title="DB Debugger", layout="wide")
st.title("🔍 Database Diagnostic Tool")

# Get connection
try:
    conn = get_connection()
    st.success("✅ Connection established successfully.")
except Exception as e:
    st.error(f"❌ Failed to connect to database:\n\n{e}")
    st.stop()

# ------------------------------------------------------------
# 4. Inspect tables and schema
# ------------------------------------------------------------
with st.expander("📋 Database Schema", expanded=True):
    # List all tables
    tables_df, err = safe_query(conn, "SELECT name FROM sqlite_master WHERE type='table';")
    if err:
        st.error(f"Could not list tables: {err}")
    else:
        st.write("**Tables in database:**", tables_df)
        
        # Show schema of 'overlaps' if it exists
        if 'overlaps' in tables_df['name'].values:
            schema_df, err2 = safe_query(conn, "PRAGMA table_info(overlaps);")
            if err2:
                st.error(f"Could not get schema for 'overlaps': {err2}")
            else:
                st.write("**Schema of `overlaps`:**")
                st.dataframe(schema_df)
        else:
            st.warning("⚠️ Table 'overlaps' does not exist in the database!")

# ------------------------------------------------------------
# 5. Test the original query
# ------------------------------------------------------------
st.subheader("🧪 Run Your Original Query")

if st.button("▶️ Execute SELECT DISTINCT Fraud_Risk_Tags FROM overlaps"):
    sql = """
        SELECT DISTINCT Fraud_Risk_Tags 
        FROM overlaps 
        WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''
    """
    with st.spinner("Running query..."):
        df, err = safe_query(conn, sql)
        
        if err:
            st.error(f"❌ Query failed:\n\n{err}")
        else:
            st.success(f"✅ Query succeeded! Found {len(df)} distinct values.")
            st.dataframe(df)

# ------------------------------------------------------------
# 6. Additional diagnostic queries (optional)
# ------------------------------------------------------------
with st.expander("🔧 More Diagnostic Queries"):
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Check if column 'Fraud_Risk_Tags' exists"):
            # Try to select just that column with LIMIT 1
            sql = "SELECT Fraud_Risk_Tags FROM overlaps LIMIT 1"
            df, err = safe_query(conn, sql)
            if err:
                st.error(f"Column might not exist or other error:\n{err}")
            else:
                st.success("Column exists and query returned at least one row.")
                st.dataframe(df)
    
    with col2:
        if st.button("Show first 5 rows of 'overlaps'"):
            sql = "SELECT * FROM overlaps LIMIT 5"
            df, err = safe_query(conn, sql)
            if err:
                st.error(f"Could not fetch rows:\n{err}")
            else:
                st.dataframe(df)

# ------------------------------------------------------------
# 7. Custom query input (for advanced testing)
# ------------------------------------------------------------
with st.expander("✏️ Run Custom SQL"):
    custom_sql = st.text_area("Enter your SQL query:", "SELECT * FROM overlaps LIMIT 10")
    if st.button("Execute Custom Query"):
        df, err = safe_query(conn, custom_sql)
        if err:
            st.error(f"Query failed:\n\n{err}")
        else:
            st.success("Query executed successfully.")
            st.dataframe(df)

# ------------------------------------------------------------
# 8. Close connection (optional, Streamlit handles it)
# ------------------------------------------------------------
# conn.close()   # Not needed because of caching, but you can if you want