import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json

# ------------------------- AUTH ------------------------- #
def authenticate():
    flow = Flow.from_client_secrets_file(
        'client_secret.json',
        scopes=['https://www.googleapis.com/auth/drive.file'],
        redirect_uri='http://localhost:8501/')

    auth_url, _ = flow.authorization_url(prompt='consent')
    st.markdown(f"[Authorize Google Drive]({auth_url})")

    query_params = st.query_params
    if 'code' in query_params:
        flow.fetch_token(code=query_params['code'])
        creds = flow.credentials
        return creds
    return None

# ------------------------- GOOGLE DRIVE UPLOAD ------------------------- #
def upload_to_drive(creds, file_path, file_name):
    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': file_name}
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        st.success(f"Uploaded: {file_name}")
    except Exception as e:
        st.error(f"Upload failed: {e}")

# ------------------------- DOWNLOAD SIMULATOR ------------------------- #
def simulate_download(symbols, start_date, end_date):
    os.makedirs("downloads", exist_ok=True)
    for symbol in symbols:
        df = pd.DataFrame({
            'Date': pd.date_range(start=start_date, end=end_date),
            'Close': pd.Series(range((end_date - start_date).days + 1))
        })
        path = f"downloads/{symbol}.csv"
        df.to_csv(path, index=False)
        st.success(f"Downloaded {symbol}")

# ------------------------- BACKTEST SIMULATOR ------------------------- #
def simulate_backtest():
    st.write("Simulating backtest...")
    data = {
        'Date': pd.date_range(end=datetime.today(), periods=5).strftime('%Y-%m-%d'),
        'Signal': ['Buy', 'Sell', 'Buy', 'Hold', 'Sell'],
        'Price': [100, 105, 102, 101, 107]
    }
    df = pd.DataFrame(data)
    st.dataframe(df)

# ------------------------- MAIN APP ------------------------- #
st.set_page_config(layout="wide")
st.title("Sentiment Sage 📈")

tabs = st.tabs(["🔐 Auth", "📅 Download", "🧠 Signals", "📊 Backtest"])

# Auth tab
with tabs[0]:
    st.subheader("Google Drive Authentication")
    creds = authenticate()
    if creds:
        st.success("Authenticated successfully!")

# Download tab
with tabs[1]:
    st.subheader("Download Stock Data")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")
    symbols_input = st.text_area("Enter symbols (comma-separated)", "RELIANCE, TCS")
    symbols = [s.strip() for s in symbols_input.split(',') if s.strip()]
    if st.button("Download"):
        simulate_download(symbols, start_date, end_date)
        if creds:
            for symbol in symbols:
                file_path = f"downloads/{symbol}.csv"
                if os.path.exists(file_path):
                    upload_to_drive(creds, file_path, f"{symbol}.csv")

# Signals tab
with tabs[2]:
    st.subheader("Select Signal Source")
    source = st.radio("Signal Source", ["Google", "Twitter", "News"])
    st.write(f"You selected: {source}")

# Backtest tab
with tabs[3]:
    st.subheader("Run Backtest")
    zscore = st.number_input("Z-Score Threshold", value=2.5, step=0.1)
    rsi = st.slider("RSI Threshold", 0, 100, 30)
    if st.button("Run Backtest"):
        simulate_backtest()
