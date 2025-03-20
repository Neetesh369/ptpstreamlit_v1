import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import uuid

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

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

def list_google_drive_folders(creds):
    """List the files within the 'nsetest' folder in Google Drive."""
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
        
        # List files within the 'nsetest' folder
        file_query = f"'{nsetest_folder_id}' in parents"
        file_results = service.files().list(q=file_query, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if not files:
            st.write('No files found in the "nsetest" folder.')
        else:
            st.write('Files in "nsetest":')
            for file in files:
                st.write(f"{file['name']} ({file['id']})")
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
