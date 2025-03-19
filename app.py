import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs

# If modifying these SCOPES, delete the token from session state.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

# Define the redirect URI (must match the one in Google Cloud Console)
REDIRECT_URI = 'https://ptpapp-qjxrob2c9ydjxeroncdq9z.streamlit.app/'

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    creds = None
    if 'google_creds' in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state.google_creds, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                st.error("Error: 'credentials.json' file is missing. Please set up Google OAuth credentials.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
            # Generate the authorization URL
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.write("Please go to the following URL to authorize the application:")
            st.write(auth_url)
            st.write("After authorization, you will be redirected back to this app.")

            # Check if the authorization code is in the URL
            query_params = st.experimental_get_query_params()
            if 'code' in query_params:
                auth_code = query_params['code'][0]
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                # Store credentials in session state
                st.session_state.google_creds = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
                st.success("Logged in successfully!")
            else:
                st.warning("Waiting for authorization code...")
                return None
    return creds

def list_google_drive_folders(creds):
    """List the user's Google Drive folders."""
    try:
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.folder'",
            pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            st.write('No folders found.')
        else:
            st.write('Folders:')
            for item in items:
                st.write(f"{item['name']} ({item['id']})")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def logout():
    """Log out the user by clearing their session state."""
    if 'google_creds' in st.session_state:
        del st.session_state.google_creds
    st.success("Logged out successfully!")

def main():
    st.title("Google Drive Folder Viewer")

    # Initialize session state
    if 'google_creds' not in st.session_state:
        st.session_state.google_creds = None

    # Login/Logout buttons
    if st.session_state.google_creds is None:
        if st.button("Login with Google"):
            st.experimental_rerun()
    else:
        if st.button("Logout"):
            logout()
            st.experimental_rerun()

    # Authenticate and list folders
    if st.session_state.google_creds is not None:
        creds = authenticate_google()
        if creds:
            list_google_drive_folders(creds)

if __name__ == '__main__':
    main()
