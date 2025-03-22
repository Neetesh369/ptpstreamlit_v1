import streamlit as st
import pandas as pd
import io
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    creds = None
    if 'creds' in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state['creds'])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        st.session_state['creds'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
    return creds

def load_data(creds):
    """Load data from Google Drive."""
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
                df = pd.read_csv(fh)
                dataframes[file['name']] = df
                st.write(f"Debug: Successfully read {file['name']} with {len(df)} rows.")
            except Exception as e:
                st.error(f"Error reading {file['name']}: {e}")
                return
        
        # Extract Date and Close columns
        try:
            a2zinfra_df = dataframes['A2ZINFRA.NS_historical_data.csv'][['Date', 'Close']]
            aartiind_df = dataframes['AARTIIND.NS_historical_data.csv'][['Date', 'Close']]
        except KeyError as e:
            st.error(f"Error extracting columns: {e}. Ensure the CSV files have 'Date' and 'Close' columns.")
            return
        
        # Merge the data on Date
        comparison_df = pd.merge(a2zinfra_df, aartiind_df, on='Date', how='outer', suffixes=('_A2ZINFRA', '_AARTIIND'))
        
        # Rename columns for clarity
        comparison_df.rename(columns={
            'Close_A2ZINFRA': 'A2ZINFRA',
            'Close_AARTIIND': 'AARTIIND'
        }, inplace=True)
        
        # Calculate Ratio
        comparison_df['Ratio'] = comparison_df['A2ZINFRA'] / comparison_df['AARTIIND']
        
        # Store the merged DataFrame in session_state
        st.session_state['comparison_df'] = comparison_df
        st.success("Data loaded successfully! Navigate to the Backtesting page.")
        
    except Exception as e:
        st.error(f"An error occurred: {e}")

def main():
    st.title("Google Drive Data Loader")
    
    # Authenticate and load data
    if 'creds' not in st.session_state:
        st.write("Please log in to Google Drive to load data.")
        if st.button("Login with Google"):
            creds = authenticate_google()
            if creds:
                load_data(creds)
    else:
        if st.button("Reload Data"):
            creds = Credentials.from_authorized_user_info(st.session_state['creds'])
            load_data(creds)
        
        if 'comparison_df' in st.session_state:
            st.write("Data is ready! Navigate to the Backtesting page.")

if __name__ == '__main__':
    main()
