import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import uuid

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly', 'https://www.googleapis.com/auth/drive.readonly']

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

def find_folder_by_name(service, folder_name):
    """Find a folder by its name in Google Drive."""
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get('files', [])
    if not folders:
        return None
    return folders[0]  # Return the first matching folder

def list_csv_files_in_folder(service, folder_id):
    """List CSV files in a specific folder in Google Drive."""
    query = f"'{folder_id}' in parents and mimeType='text/csv'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    return files

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
            service = build('drive', 'v3', credentials=creds)
            folder_name = st.text_input("Enter the folder name to search for:")
            if folder_name:
                folder = find_folder_by_name(service, folder_name)
                if folder:
                    st.success(f"Found folder: {folder['name']} (ID: {folder['id']})")
                    csv_files = list_csv_files_in_folder(service, folder['id'])
                    if csv_files:
                        st.write("CSV files in the folder:")
                        for file in csv_files:
                            st.write(f"- {file['name']} (ID: {file['id']})")
                    else:
                        st.warning("No CSV files found in the folder.")
                else:
                    st.error(f"Folder '{folder_name}' not found.")

    if st.button("Logout"):
        logout()

if __name__ == '__main__':
    main()
