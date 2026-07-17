import streamlit as st
import pandas as pd
import sqlite3
import traceback
import json
import os

# ------------------------------------------------------------
# Custom CSS: black background, white text, clean style
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background-color: black;
        color: white;
    }
    .stSelectbox, .stTextInput, .stButton, .stCheckbox {
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. Database setup – use connections.db
# ------------------------------------------------------------
DB_PATH = "connections.db"   # <-- your database file

if not os.path.exists(DB_PATH):
    st.error(f"❌ Database file '{DB_PATH}' not found. Please make sure it exists.")
    st.stop()

# ------------------------------------------------------------
# 2. Helper: run a query with a fresh connection
# ------------------------------------------------------------
def run_query(sql, params=None):
    """Execute SQL and return (DataFrame, error_message_or_None)."""
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
# 3. Cached function to get fraud flags (runs query once)
# ------------------------------------------------------------
@st.cache_data(ttl=600)   # cache for 10 minutes
def get_fraud_flags():
    sql = """
        SELECT DISTINCT Fraud_Risk_Tags 
        FROM overlaps 
        WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''
    """
    df, err = run_query(sql)
    if err:
        st.error(f"Error loading fraud flags:\n{err}")
        return pd.DataFrame(columns=['Fraud_Risk_Tags'])  # empty fallback
    return df

# ------------------------------------------------------------
# 4. Load fraud flags (with error handling)
# ------------------------------------------------------------
fraud_df = get_fraud_flags()
fraud_options = fraud_df['Fraud_Risk_Tags'].tolist() if not fraud_df.empty else []

# ------------------------------------------------------------
# 5. UI Controls
# ------------------------------------------------------------
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    search_term = st.text_input("Search", placeholder="Enter domain or company name...")

with col2:
    hub_choice = st.selectbox("Choose hub", ["All"] + ["Hub A", "Hub B", "Hub C"])  # adjust as needed

with col3:
    fraud_flag = st.selectbox("Fraud flag", ["All"] + fraud_options)

# Additional options (matching your old layout)
show_all_pulte = st.checkbox("All Pulte Companies", value=True)
show_only_shared_cname = st.checkbox("Only show shared ultimate CNAME", value=False)

# ------------------------------------------------------------
# 6. Query execution (example – adapt to your actual data)
# ------------------------------------------------------------
if st.button("Search"):
    # Build your query based on filters – this is a placeholder.
    # Replace with your actual table/columns.
    st.write("### Search Results")
    
    # Example: show a sample of the overlaps table
    sample_sql = "SELECT * FROM overlaps LIMIT 10"
    df, err = run_query(sample_sql)
    if err:
        st.error(f"Error running query:\n{err}")
    else:
        st.dataframe(df)

# ------------------------------------------------------------
# 7. Optional: Show current fraud flags list for reference
# ------------------------------------------------------------
with st.expander("📋 Available Fraud Flags"):
    if not fraud_df.empty:
        st.dataframe(fraud_df)
    else:
        st.warning("No fraud flags loaded.")