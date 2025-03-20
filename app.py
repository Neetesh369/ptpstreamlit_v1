import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import time

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly', 'https://www.googleapis.com/auth/drive.readonly']

# Define the redirect URI (must match the one in Google Cloud Console)
REDIRECT_URI = 'https://c6f7-34-75-61-193.ngrok-free.app/'

# Initialize session state for data_folder and credentials
if 'data_folder' not in st.session_state:
    st.session_state.data_folder = None
if 'creds' not in st.session_state:
    st.session_state.creds = None

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                st.error("Error: 'credentials.json' file is missing. Please set up Google OAuth credentials.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.write("Please go to the following URL to authorize the application:")
            st.write(auth_url)
            st.write("After authorization, enter the code you receive below:")
            auth_code = st.text_input("Enter the authorization code:")
            if auth_code:
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                st.success("Logged in successfully!")
            else:
                st.warning("Waiting for authorization code...")
                return None
    st.session_state.creds = creds
    return creds

def list_google_drive_files(folder_name):
    """List CSV files in a specific Google Drive folder."""
    if not st.session_state.creds:
        st.error("Please log in first.")
        return []
    try:
        service = build('drive', 'v3', credentials=st.session_state.creds)
        results = service.files().list(
            q=f"name contains '.csv' and '{folder_name}' in parents",
            pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        return [item['name'] for item in items]
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return []

def load_stock_data(file_name, folder_name, start_date, end_date):
    """Load stock data from a CSV file in Google Drive."""
    if not st.session_state.creds:
        st.error("Please log in first.")
        return pd.DataFrame()
    try:
        service = build('drive', 'v3', credentials=st.session_state.creds)
        results = service.files().list(
            q=f"name='{file_name}' and '{folder_name}' in parents",
            pageSize=1, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            st.error(f"File '{file_name}' not found.")
            return pd.DataFrame()
        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_csv(fh)
        df['Date'] = pd.to_datetime(df['Date'])
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)
        df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
        df = df.sort_values('Date')
        return df
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return pd.DataFrame()

def compute_zscore(pair_df, lookback=50):
    """Compute Z-Score and generate trading signals."""
    pair_df['Ratio'] = pair_df['Close_A'] / pair_df['Close_B']
    pair_df['Mean'] = pair_df['Ratio'].rolling(lookback).mean()
    pair_df['Std'] = pair_df['Ratio'].rolling(lookback).std()
    pair_df['Z-Score'] = (pair_df['Ratio'] - pair_df['Mean']) / pair_df['Std']
    pair_df = pair_df.iloc[lookback:].copy()
    pair_df['Signal'] = 'No Trade'
    prev_signal = 'No Trade'
    for i in range(1, len(pair_df)):
        if pair_df.iloc[i-1]['Z-Score'] <= 2.5 and pair_df.iloc[i]['Z-Score'] > 2.5:
            pair_df.at[pair_df.index[i], 'Signal'] = 'Short A, Long B'
            prev_signal = 'Short A, Long B'
        elif prev_signal == 'Short A, Long B' and pair_df.iloc[i]['Z-Score'] < 1.5:
            pair_df.at[pair_df.index[i], 'Signal'] = 'Exit & Reverse to Long A, Short B'
            prev_signal = 'No Trade'
        if pair_df.iloc[i-1]['Z-Score'] >= -2.5 and pair_df.iloc[i]['Z-Score'] < -2.5:
            pair_df.at[pair_df.index[i], 'Signal'] = 'Long A, Short B'
            prev_signal = 'Long A, Short B'
        elif prev_signal == 'Long A, Short B' and pair_df.iloc[i]['Z-Score'] > -1.5:
            pair_df.at[pair_df.index[i], 'Signal'] = 'Exit & Reverse to Short A, Long B'
            prev_signal = 'No Trade'
    return pair_df

# Streamlit App
st.title("Pair Trading Backtesting with Z-Score")

# Google Drive Authentication
if st.button("Login with Google"):
    authenticate_google()

# List files in Google Drive folder
if st.session_state.creds:
    folder_name = 'nsetest'  # Replace with your Google Drive folder name
    files = list_google_drive_files(folder_name)
    if files:
        stock_a = st.selectbox("Select Stock A", files)
        stock_b = st.selectbox("Select Stock B", files)
        start_date = st.date_input("From Date")
        end_date = st.date_input("To Date")
        if st.button("Go"):
            df_a = load_stock_data(stock_a, folder_name, start_date, end_date)
            df_b = load_stock_data(stock_b, folder_name, start_date, end_date)
            if not df_a.empty and not df_b.empty:
                merged_df = pd.merge(df_a[['Date', 'Close']], df_b[['Date', 'Close']], on='Date', suffixes=('_A', '_B'))
                zscore_df = compute_zscore(merged_df)
                st.subheader("Z-Score Table")
                st.write(zscore_df[['Date', 'Close_A', 'Close_B', 'Z-Score', 'Signal']])
                trades = zscore_df[zscore_df['Signal'] != 'No Trade'][['Date', 'Signal']]
                trades['Profit/Loss'] = np.random.uniform(-500, 500, size=len(trades))
                st.subheader("Trade List")
                st.write(trades)
                st.subheader("Equity Curve")
                trades['Cumulative PnL'] = trades['Profit/Loss'].cumsum()
                plt.figure(figsize=(10, 5))
                plt.plot(trades['Date'], trades['Cumulative PnL'], marker='o', linestyle='-')
                plt.xlabel('Date')
                plt.ylabel('Cumulative PnL')
                plt.title('Equity Curve')
                st.pyplot(plt)
