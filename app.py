import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# ---------------------- CUSTOM FONT AND STYLE ----------------------
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📈 Pair Trading Setup")

# ---------------------- GOOGLE AUTH ----------------------
def google_authenticate():
    creds = None
    if 'tokens' not in st.session_state:
        st.session_state['tokens'] = {}

    session_id = st.query_params.get("session_id", None)
    if not session_id:
        st.warning("Missing session_id in query parameters.")
        return None

    if session_id in st.session_state['tokens']:
        creds = st.session_state['tokens'][session_id]
    else:
        if os.path.exists("credentials.json"):
            flow = Flow.from_client_secrets_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/drive.readonly'],
                redirect_uri="http://localhost:8501"
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.markdown(f"[Click here to authenticate]({auth_url})")
        else:
            st.error("credentials.json file not found.")
        return None

    creds = Credentials.from_authorized_user_info(creds)
    return creds

# ---------------------- LOAD FILES FROM GOOGLE DRIVE ----------------------
@st.cache_data
def fetch_csvs_from_drive(creds):
    service = build('drive', 'v3', credentials=creds)

    # Find folder named 'nsetest'
    folder_results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and name='nsetest'",
        spaces='drive'
    ).execute()

    folders = folder_results.get('files', [])
    if not folders:
        st.error("Folder 'nsetest' not found.")
        return []

    folder_id = folders[0]['id']

    # Get CSV files from the folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='text/csv'",
        spaces='drive'
    ).execute()

    items = results.get('files', [])
    dfs = {}
    for item in items:
        file_id = item['id']
        file_name = item['name']
        request = service.files().get_media(fileId=file_id)
        file_data = request.execute()
        df = pd.read_csv(pd.compat.StringIO(file_data.decode()))
        dfs[file_name] = df

    return dfs

# ---------------------- Z-SCORE & RSI FUNCTIONS ----------------------
def calculate_zscore(series, window=50):
    mean = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (series - mean) / std

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ---------------------- USER AUTH + LOAD CSV ----------------------
creds = google_authenticate()
if creds:
    st.success("✅ Successfully authenticated.")
    dataframes = fetch_csvs_from_drive(creds)

    if dataframes:
        st.write("Files found in 'nsetest' folder:")
        for name in dataframes:
            st.write(f"📄 {name}")
    else:
        st.warning("No CSV files found.")

# ---------------------- Z-SCORE INPUT SECTION ----------------------
st.subheader("⚙️ Strategy Parameters")

col1, col2 = st.columns(2)

with col1:
    long_entry_z = st.number_input(
        "📉 Long Entry Z-Score", value=-2.5, step=0.1, format="%.1f",
        max_value=0.0
    )

    long_exit_z = st.number_input(
        "📈 Long Exit Z-Score", value=-1.5, step=0.1, format="%.1f",
        min_value=long_entry_z + 0.1, max_value=0.0
    )

with col2:
    short_entry_z = st.number_input(
        "📈 Short Entry Z-Score", value=2.5, step=0.1, format="%.1f",
        min_value=0.0
    )

    short_exit_z = st.number_input(
        "📉 Short Exit Z-Score", value=1.5, step=0.1, format="%.1f",
        min_value=0.0, max_value=short_entry_z - 0.1
    )

# ---------------------- VALIDATION MESSAGES ----------------------
if long_exit_z <= long_entry_z:
    st.warning("⚠️ Long Exit Z-Score must be greater than Long Entry Z-Score.")

if short_exit_z >= short_entry_z:
    st.warning("⚠️ Short Exit Z-Score must be less than Short Entry Z-Score.")

# ---------------------- OPTIONAL: HISTORICAL DATA FETCH ----------------------
def download_historical_data(symbols, start_date, end_date):
    data = {}
    for symbol in symbols:
        try:
            df = yf.download(symbol, start=start_date, end=end_date)
            data[symbol] = df
        except Exception as e:
            st.error(f"Error downloading {symbol}: {e}")
    return data

# ---------------------- DONE ----------------------
st.markdown("---")
st.info("🎯 Now ready to run your pair trading backtest or signal logic using the configured Z-scores.")

