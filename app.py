import streamlit as st
import os
import pandas as pd
import io
import numpy as np
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import uuid

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Define the redirect URI (must match the one in Google Cloud Console)
REDIRECT_URI = 'https://ptpapp-qjxrob2c9ydjxeroncdq9z.streamlit.app/'

# Dictionary to store tokens per session
if 'tokens' not in st.session_state:
    st.session_state['tokens'] = {}

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    # Get the session ID (unique for each user)
    session_id = st.query_params.get('session_id', None)
    if not session_id:
        st.error("Session ID not found. Please reload the page.")
        return None

    # Check if tokens exist for this session
    if session_id in st.session_state['tokens']:
        creds = Credentials.from_authorized_user_info(st.session_state['tokens'][session_id])
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            st.session_state['tokens'][session_id] = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            return creds

    # If no valid tokens, start the OAuth flow
    if not os.path.exists('credentials.json'):
        st.error("Error: 'credentials.json' file is missing. Please set up Google OAuth credentials.")
        return None

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.write("Please go to the following URL to authorize the application:")
    st.write(auth_url)
    st.write("After authorization, you will be redirected back to this app.")

    # Check if the authorization code is in the URL
    query_params = st.query_params
    if 'code' in query_params:
        auth_code = query_params['code']
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        # Store tokens in session state
        st.session_state['tokens'][session_id] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        st.success("Logged in successfully!")
        return creds
    else:
        st.warning("Waiting for authorization code...")
        return None

def calculate_zscore(series, window=50):
    """Calculate the Z-score for a given series using a rolling window."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    zscore = (series - rolling_mean) / rolling_std
    return zscore

def calculate_rsi(series, window=14):
    """Calculate the Relative Strength Index (RSI) for a given series using a rolling window."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def list_google_drive_folders(creds):
    """Read and compare stock price data from CSV files in the 'nsetest' folder."""
    try:
        service = build('drive', 'v3', credentials=creds)
        
        # Find the folder ID of 'nsetest'
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='nsetest'"
        folder_results = service.files().list(q=folder_query, fields="files(id, name)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            st.write("Folder 'nsetest' not found.")
            return
        
        nsetest_folder_id = folders[0]['id']
        
        # Find the CSV files in the 'nsetest' folder
        file_query = f"'{nsetest_folder_id}' in parents and (name='A2ZINFRA.NS_historical_data.csv' or name='AARTIIND.NS_historical_data.csv')"
        file_results = service.files().list(q=file_query, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if len(files) != 2:
            st.write("Required CSV files not found in the 'nsetest' folder.")
            return
        
        # Download and read the CSV files
        dataframes = {}
        for file in files:
            try:
                file_id = file['id']
                request = service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                
                # Read the CSV file with explicit delimiter and error handling
                df = pd.read_csv(fh, delimiter=',', encoding='utf-8')
                dataframes[file['name']] = df
                st.write(f"Debug: Successfully read {file['name']} with {len(df)} rows.")
            except Exception as e:
                st.error(f"Error reading {file['name']}: {e}")
                return
        
        # Debug: Print the raw data from the CSV files
        st.write("Debug: Raw data from CSV files:")
        for file_name, df in dataframes.items():
            st.write(f"File: {file_name}")
            st.write(df.head())  # Show the first 5 rows of each file
        
        # Extract Date and Close columns
        try:
            a2zinfra_df = dataframes['A2ZINFRA.NS_historical_data.csv'][['Date', 'Close']]
            aartiind_df = dataframes['AARTIIND.NS_historical_data.csv'][['Date', 'Close']]
            st.write("Debug: Successfully extracted 'Date' and 'Close' columns.")
        except KeyError as e:
            st.error(f"Error extracting columns: {e}. Ensure the CSV files have 'Date' and 'Close' columns.")
            return
        
        # Debug: Print the extracted columns
        st.write("Debug: Extracted columns:")
        st.write("A2ZINFRA Data:")
        st.write(a2zinfra_df.head())
        st.write("AARTIIND Data:")
        st.write(aartiind_df.head())
        
        # Merge the data on Date
        try:
            comparison_df = pd.merge(a2zinfra_df, aartiind_df, on='Date', how='outer', suffixes=('_A2ZINFRA', '_AARTIIND'))
            st.write("Debug: Successfully merged DataFrames.")
        except Exception as e:
            st.error(f"Error merging DataFrames: {e}")
            return
        
        # Debug: Print the merged DataFrame
        st.write("Debug: Merged DataFrame:")
        st.write(comparison_df.head())
        
        # Rename columns for clarity
        comparison_df.rename(columns={
            'Close_A2ZINFRA': 'A2ZINFRA',
            'Close_AARTIIND': 'AARTIIND'
        }, inplace=True)
        
        # Calculate Ratio
        comparison_df['Ratio'] = comparison_df['A2ZINFRA'] / comparison_df['AARTIIND']
        
        # Add input boxes for Z-Score lookback and RSI period
        st.write("### Adjust Parameters")
        zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50)
        rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14)
        
        # Add a "Go" button
        if st.button("Go"):
            # Calculate Z-Score of Ratio
            comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
            
            # Calculate RSI of Ratio
            comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
            
            # Sort by Date (most recent first) and limit to 300 rows
            comparison_df = comparison_df.sort_values(by='Date', ascending=False).head(300)
            
            # Display the comparison table
            st.write("### Stock Price Comparison (Last 300 Rows)")
            st.dataframe(comparison_df)
        
    except Exception as e:
        st.error(f"An error occurred: {e}")

def logout():
    """Clear the session state and log out the user."""
    session_id = st.query_params.get('session_id', None)
    if session_id and session_id in st.session_state['tokens']:
        del st.session_state['tokens'][session_id]
    st.success("Logged out successfully!")

def main():
    st.title("Google Drive Folder Viewer")

    # Generate a unique session ID
    session_id = st.query_params.get('session_id', None)
    if not session_id:
        session_id = str(uuid.uuid4())
        st.query_params['session_id'] = session_id

    if st.button("Login with Google"):
        creds = authenticate_google()
        if creds:
            list_google_drive_folders(creds)

    if st.button("Logout"):
        logout()

if __name__ == '__main__':
    main()
