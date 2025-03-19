import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

# Define the redirect URI (must match the one in Google Cloud Console)
REDIRECT_URI = 'https://ptpapp-qjxrob2c9ydjxeroncdq9z.streamlit.app/'

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    st.write("Starting authentication process...")  # Debugging output

    # Check if tokens are already stored in the session state
    if 'creds' in st.session_state and st.session_state.creds:
        st.write("Found existing credentials in session state.")  # Debugging output
        creds = Credentials.from_authorized_user_info(st.session_state.creds, SCOPES)
        if creds and creds.valid:
            st.write("Using existing valid credentials.")  # Debugging output
            return creds
        if creds and creds.expired and creds.refresh_token:
            st.write("Refreshing expired credentials.")  # Debugging output
            creds.refresh(Request())
            st.session_state.creds = creds.to_json()
            return creds

    # If no valid tokens, start the OAuth flow
    if not os.path.exists('credentials.json'):
        st.error("Error: 'credentials.json' file is missing. Please set up Google OAuth credentials.")
        return None

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
    # Generate the authorization URL
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.write("Please go to the following URL to authorize the application:")  # Debugging output
    st.write(auth_url)  # Debugging output
    st.write("After authorization, you will be redirected back to this app.")  # Debugging output

    # Check if the authorization code is in the URL
    query_params = st.experimental_get_query_params()
    st.write(f"Query parameters: {query_params}")  # Debugging output
    if 'code' in query_params:
        auth_code = query_params['code'][0]
        st.write(f"Authorization code: {auth_code}")  # Debugging output
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        st.write(f"Access token: {creds.token}")  # Debugging output
        st.write(f"Refresh token: {creds.refresh_token}")  # Debugging output
        # Store tokens in session state
        st.session_state.creds = creds.to_json()
        st.success("Logged in successfully!")
        return creds
    else:
        st.warning("Waiting for authorization code...")
        return None

def list_google_drive_folders(creds):
    """List the user's Google Drive folders."""
    st.write("Fetching Google Drive folders...")  # Debugging output
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
    """Clear session state and log out the user."""
    if 'creds' in st.session_state:
        del st.session_state.creds
    st.success("Logged out successfully!")

def main():
    st.title("Google Drive Folder Viewer")
    st.write("Session state:", st.session_state)  # Debugging output

    if st.button("Login with Google"):
        creds = authenticate_google()
        if creds:
            list_google_drive_folders(creds)
    if st.button("Logout"):
        logout()

if __name__ == '__main__':
    main()
