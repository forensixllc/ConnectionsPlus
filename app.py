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
    .stSelectbox, .stTextInput, .stButton, .stCheckbox { color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Pulte +")
st.caption("Search overlaps for Pulte companies or any domain list from a JSON file")

# ------------------------------------------------------------
# 1. List all .db files in the current directory
# ------------------------------------------------------------
current_dir = os.getcwd()
db_files = [f for f in os.listdir(current_dir) if f.endswith('.db')]

if not db_files:
    st.error("No .db files found in the current directory. Please upload a database file.")
    uploaded_db = st.file_uploader("Upload a SQLite database file", type=["db"])
    if uploaded_db:
        # Save the uploaded file to disk (optional)
        with open("uploaded.db", "wb") as f:
            f.write(uploaded_db.getbuffer())
        db_files = ["uploaded.db"]
        st.success("File uploaded successfully.")
    else:
        st.stop()
else:
    st.write(f"Found {len(db_files)} database file(s).")

# ------------------------------------------------------------
# 2. Database selection
# ------------------------------------------------------------
selected_db = st.selectbox("Choose a database file", db_files)
DB_PATH = selected_db

# ------------------------------------------------------------
# 3. Validate that it's a real SQLite database
# ------------------------------------------------------------
def is_valid_sqlite(filepath):
    """Return True if file is a readable SQLite database."""
    try:
        conn = sqlite3.connect(filepath)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False

if not is_valid_sqlite(DB_PATH):
    st.error(f"❌ The file `{DB_PATH}` is not a valid SQLite database. Please choose another file or upload a correct one.")
    # Show the first few bytes to help diagnose
    with open(DB_PATH, "rb") as f:
        header = f.read(16)
    st.write(f"File header (first 16 bytes): {header.hex()}")
    st.stop()

st.success(f"✅ Database `{DB_PATH}` is valid and ready.")

# ------------------------------------------------------------
# 4. Helper: run query with fresh connection
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
# 5. Cached function to get fraud flags
# ------------------------------------------------------------
@st.cache_data(ttl=600)
def get_fraud_flags():
    sql = """
        SELECT DISTINCT Fraud_Risk_Tags 
        FROM overlaps 
        WHERE Fraud_Risk_Tags IS NOT NULL AND Fraud_Risk_Tags != ''
    """
    df, err = run_query(sql)
    if err:
        st.error(f"Error loading fraud flags:\n{err}")
        return pd.DataFrame(columns=['Fraud_Risk_Tags'])
    return df

# ------------------------------------------------------------
# 6. Load fraud flags and show UI
# ------------------------------------------------------------
fraud_df = get_fraud_flags()
fraud_options = fraud_df['Fraud_Risk_Tags'].tolist() if not fraud_df.empty else []

# UI Controls (same as before)
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    search_term = st.text_input("Search", placeholder="Enter domain or company name...")

with col2:
    hub_choice = st.selectbox("Choose hub", ["All"] + ["Hub A", "Hub B", "Hub C"])  # adjust

with col3:
    fraud_flag = st.selectbox("Fraud flag", ["All"] + fraud_options)

show_all_pulte = st.checkbox("All Pulte Companies", value=True)
show_only_shared_cname = st.checkbox("Only show shared ultimate CNAME", value=False)

if st.button("Search"):
    # Example placeholder query – replace with your actual logic
    st.write("### Search Results")
    sample_sql = "SELECT * FROM overlaps LIMIT 10"
    df, err = run_query(sample_sql)
    if err:
        st.error(f"Error running query:\n{err}")
    else:
        st.dataframe(df)

# Optional: Show fraud flags list
with st.expander("📋 Available Fraud Flags"):
    if not fraud_df.empty:
        st.dataframe(fraud_df)
    else:
        st.warning("No fraud flags loaded.")